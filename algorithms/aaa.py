import sys

import numpy as np
import pandas as pd
import scipy.special as sc
import motmetrics as mm

from algorithms.anchor_detector import FixedDetector
from algorithms.id_matcher import IDMatcher
from feedback.neural_solver import NeuralSolver
from algorithms.aaa_util import (
    convert_df,
    weighted_random_choice,
    loss_function,
    minmax,
)


class WAADelayed:
    def __init__(self):
        pass

    def initialize(self, n):
        self.w = np.ones(n) / n
        self.est_D = 1
        self.real_D = 0

    """
    gradient_losses should be n
    """

    def update(self, gradient_losses, dt, norm):
        # check the number of element
        assert len(gradient_losses) == len(self.w)

        if norm:
            losses = minmax(gradient_losses) * dt
        else:
            losses = gradient_losses * dt

        for i in range(1, dt + 1):
            self.real_D += i
            if self.est_D < self.real_D:
                self.est_D *= 2

        lr = np.sqrt(self.est_D * np.log(len(self.w)))

        changes = lr * losses
        temp = np.log(self.w + sys.float_info.min) - changes
        self.w = np.exp(temp - sc.logsumexp(temp))


class AAA:
    def __init__(self, config):
        self.name = f"{config['MATCHING']}, {config['DETECTOR']}, {config['OFFLINE']}, {config['LOSS']}"
        self.n_experts = len(config["EXPERTS"])
        self.config = config

        if self.config["DETECTOR"]["type"] == "fixed":
            self.detector = FixedDetector(self.config["DETECTOR"]["duration"])

        self.learner = WAADelayed()
        self.matcher = IDMatcher(config)

        if not self.config["OFFLINE"]["use_gt"]:
            self.offline = NeuralSolver(
                self.config["FEEDBACK"]["ckpt_path"],
                self.config["FEEDBACK"]["frcnn_weights_path"],
                self.config["FEEDBACK"]["reid_weights_path"],
                self.config["FEEDBACK"]["tracking_cfg_path"],
                self.config["FEEDBACK"]["preprocessing_cfg_path"],
                self.config["FEEDBACK"]["prepr_w_tracktor"],
            )
        self.is_reset_offline = self.config["OFFLINE"]["reset"]

        self.acc = mm.MOTAccumulator(auto_id=True)

    def initialize(self, seq_info):
        self.frame_idx = -1

        self.seq_info = seq_info
        self.detector.initialize(seq_info)
        self.learner.initialize(self.n_experts)
        self.matcher.initialize(self.n_experts)

        self.reset_offline()
        self.reset_history()

    def reset_offline(self):
        self.img_paths = []
        self.dets = []
        self.gts = []

    def reset_history(self):
        self.timer = -1
        self.experts_results = [[] for _ in range(self.n_experts)]

    def track(self, img_path, dets, gts, results):
        self.frame_idx += 1
        self.timer += 1

        self.img_paths.append(img_path)
        self.dets.append(dets)
        self.gts.append(gts)

        # save experts' result
        for i, result in enumerate(results):
            if len(result) > 0:
                frame_result = np.zeros((result.shape[0], result.shape[1] + 1))
                frame_result[:, 1:] = result
                frame_result[:, 0] = self.timer + 1
                if len(self.experts_results[i]) > 0:
                    self.experts_results[i] = np.concatenate(
                        [self.experts_results[i], frame_result], axis=0
                    )
                else:
                    self.experts_results[i] = frame_result

        # detect anchor frame
        is_anchor = self.detector.detect(img_path, dets, results)

        # update weight
        if is_anchor:
            # try to receive feedback
            if not self.config["OFFLINE"]["use_gt"]:
                try:
                    feedback = self.offline.track(
                        self.seq_info, self.img_paths, self.dets
                    )
                except Exception:
                    feedback = None
            else:
                feedback = []
                for i, gt in enumerate(self.gts):
                    for t in gt:
                        feedback.append([i + 1, t[1], t[2], t[3], t[4], t[5]])
                feedback = np.array(feedback)

            # update weight
            if feedback is not None:
                df_feedback = convert_df(feedback, is_offline=True)

                smallest_frame = len(self.dets) - self.timer - 1
                df_cond = df_feedback.index.get_level_values(0) > smallest_frame
                df_feedback = df_feedback[df_cond]

                df_feedback.index = pd.MultiIndex.from_tuples(
                    [(x[0] - smallest_frame, x[1]) for x in df_feedback.index]
                )

                # calculate loss
                gradient_losses = np.zeros((self.n_experts))
                for i, expert_results in enumerate(self.experts_results):
                    df_expert_results = convert_df(expert_results)

                    if (
                        self.seq_info["dataset_name"] == "MOT16"
                        or self.seq_info["dataset_name"] == "MOT17"
                    ):
                        acc, ana = mm.utils.CLEAR_MOT_M(
                            df_feedback,
                            df_expert_results,
                            self.seq_info["ini_path"],
                            "iou",
                            distth=0.5,
                            vflag="",
                        )
                    else:
                        acc = mm.utils.compare_to_groundtruth(
                            df_feedback, df_expert_results, "iou", distth=0.5
                        )
                        ana = None
                    mh = mm.metrics.create()
                    loss = loss_function(self.config["LOSS"]["type"], mh, acc, ana)
                    gradient_losses[i] = loss

                if self.config["LOSS"]["delayed"]:
                    dt = self.timer + 1
                else:
                    dt = 1
                self.learner.update(gradient_losses, dt, self.config["LOSS"]["norm"])

                self.reset_history()
                if self.is_reset_offline:
                    self.reset_offline()

            else:
                gradient_losses = None

        else:
            feedback = None
            gradient_losses = None

        if self.frame_idx > 0:
            prev_selected_expert = self.selected_expert
        else:
            prev_selected_expert = None

        # select expert
        if self.frame_idx == 0 or is_anchor or self.config["LOSS"]["delayed"]:
            self.selected_expert = weighted_random_choice(self.learner.w)

        # match id
        if self.config["MATCHING"]["method"] == "anchor":
            curr_expert_bboxes = self.matcher.anchor_match(
                prev_selected_expert, self.selected_expert, results
            )
        elif self.config["MATCHING"]["method"] == "kmeans":
            curr_expert_bboxes = self.matcher.kmeans_match(
                self.learner.w, self.selected_expert, results
            )
        else:
            raise NameError("Please enter a valid matching method")

        if len(curr_expert_bboxes) > 0:
            u, c = np.unique(curr_expert_bboxes[:, 0], return_counts=True)
            assert (c == 1).all(), f"Duplicated ID in frame {self.frame_idx}"

        return (
            curr_expert_bboxes,
            self.learner.w,
            gradient_losses,
            feedback,
            self.selected_expert,
        )
