import sys
import yaml
from PIL import Image
import numpy as np
from numpy import pad
import pandas as pd
from skimage.io import imread

import torch
from torchvision.transforms import Compose, Resize, ToTensor, Normalize

from feedback.mot_graph_dataset import MOTGraphDataset

sys.path.append("external/mot_neural_solver/src")
from mot_neural_solver.data.preprocessing import FRCNNPreprocessor
from mot_neural_solver.pl_module.pl_module import MOTNeuralSolver
from mot_neural_solver.models.mpn import MOTMPNet
from mot_neural_solver.tracker.mpn_tracker import MPNTracker
from mot_neural_solver.models.resnet import resnet50_fc256, load_pretrained_weights
from mot_neural_solver.data.seq_processing.MOT17loader import (
    MOV_CAMERA_DICT as MOT17_MOV_CAMERA_DICT,
)
from mot_neural_solver.data.seq_processing.MOT15loader import (
    MOV_CAMERA_DICT as MOT15_MOV_CAMERA_DICT,
)
from mot_neural_solver.utils.misc import make_deterministic

sys.path.append("external/mot_neural_solver/tracking_wo_bnw/src")
from tracktor.frcnn_fpn import FRCNN_FPN
from tracktor.tracker import Tracker

MOV_CAMERA_DICT = {**MOT15_MOV_CAMERA_DICT, **MOT17_MOV_CAMERA_DICT}
TRACKING_OUT_COLS = [
    "frame",
    "ped_id",
    "bb_left",
    "bb_top",
    "bb_width",
    "bb_height",
    "conf",
    "x",
    "y",
    "z",
]

import warnings

warnings.simplefilter("ignore", pd.core.common.SettingWithCopyWarning)


def extract(frame_img, bbox, frame_height, frame_width, transforms):
    bb_left = bbox[0]
    bb_top = bbox[1]
    bb_right = bbox[2]
    bb_bot = bbox[3]
    # Crop the bounding box, and pad it if necessary to
    bb_img = frame_img[
        int(max(0, bb_top)) : int(max(0, bb_bot)),
        int(max(0, bb_left)) : int(max(0, bb_right)),
    ]
    x_height_pad = np.abs(bb_top - max(bb_top, 0)).astype(int)
    y_height_pad = np.abs(bb_bot - min(bb_bot, frame_height)).astype(int)

    x_width_pad = np.abs(bb_left - max(bb_left, 0)).astype(int)
    y_width_pad = np.abs(bb_right - min(bb_right, frame_width)).astype(int)

    bb_img = pad(
        bb_img,
        ((x_height_pad, y_height_pad), (x_width_pad, y_width_pad), (0, 0)),
        mode="mean",
    )

    bb_img = Image.fromarray(bb_img)
    if transforms is not None:
        bb_img = transforms(bb_img)

    return bb_img


class CustomMPNTracker(MPNTracker):
    def __init__(self, *args, **kwargs):
        super(CustomMPNTracker, self).__init__(*args, **kwargs)

    def _load_full_seq_graph_object(self, seq_name):
        """
        Loads a MOTGraph (see data/mot_graph.py) object corresponding to the entire sequence.
        """
        step_size = self.dataset.seq_info_dicts[seq_name]["step_size"]
        frames_per_graph = self._estimate_frames_per_graph(seq_name)
        start_frame = self.dataset.seq_det_dfs[seq_name].frame.min()
        end_frame = self.dataset.seq_det_dfs[seq_name].frame.max()

        # TODO: Should use seconds as unit, and not number of frames
        if self.dataset.dataset_params["max_frame_dist"] == "max":
            max_frame_dist = step_size * (frames_per_graph - 1)

        else:
            max_frame_dist = self.dataset.dataset_params["max_frame_dist"]

        full_graph = self.dataset.get_from_frame_and_seq(
            seq_name=seq_name,
            start_frame=start_frame,
            end_frame=end_frame,
            return_full_object=True,
            ensure_end_is_in=False,
            max_frame_dist=max_frame_dist,
            inference_mode=True,
        )
        full_graph.frames_per_graph = frames_per_graph
        return full_graph


class CustomMOTNeuralSolver(MOTNeuralSolver):
    def __init__(self, *args, **kwargs):
        super(CustomMOTNeuralSolver, self).__init__(*args, **kwargs)

    def load_model(self):
        model = MOTMPNet(self.hparams["graph_model_params"]).cuda()

        cnn_model = resnet50_fc256(10, loss="xent", pretrained=True).cuda()
        load_pretrained_weights(
            cnn_model, self.reid_weights_path,
        )
        cnn_model.return_embeddings = True

        return model, cnn_model

    def track_seq(self, dataset):
        tracker = CustomMPNTracker(
            dataset=dataset,
            graph_model=self.model,
            use_gt=False,
            eval_params=self.hparams["eval_params"],
            dataset_params=self.hparams["dataset_params"],
        )

        seq_name = dataset.seq_names[0]

        tracker.track(seq_name)
        tracker.tracking_out["conf"] = 1
        tracker.tracking_out["x"] = -1
        tracker.tracking_out["y"] = -1
        tracker.tracking_out["z"] = -1

        tracker.tracking_out["bb_left"] += 1  # Indexing is 1-based in the ground truth
        tracker.tracking_out["bb_top"] += 1

        final_out = tracker.tracking_out[TRACKING_OUT_COLS].sort_values(
            by=["frame", "ped_id"]
        )

        return final_out


class NeuralSolver:
    def __init__(
        self,
        ckpt_path,
        frcnn_weights_path,
        reid_weights_path,
        tracking_cfg_path,
        preprocessing_cfg_path,
        prepr_w_tracktor,
        use_gt,
        pre_cnn,
    ):
        self.name = "MPNTracker"
        with open(tracking_cfg_path) as config_file:
            config = yaml.load(config_file)

        with open(preprocessing_cfg_path) as config_file:
            pre_config = yaml.load(config_file)
            frcnn_prepr_params = pre_config["frcnn_prepr_params"]
            tracktor_params = pre_config["tracktor_params"]

        CustomMOTNeuralSolver.reid_weights_path = reid_weights_path

        # Load model from checkpoint and update config entries that may vary from the ones used in training
        self.model = CustomMOTNeuralSolver.load_from_checkpoint(
            checkpoint_path=ckpt_path
        )
        self.model.cnn_model.eval()
        self.model.hparams.update(
            {
                "eval_params": config["eval_params"],
                "data_splits": config["data_splits"],
            }
        )
        self.model.hparams["dataset_params"]["precomputed_embeddings"] = False
        self.model.hparams["dataset_params"]["img_batch_size"] = 2500

        # preprocessor
        obj_detect = FRCNN_FPN(num_classes=2)

        obj_detect.load_state_dict(
            torch.load(frcnn_weights_path, map_location=lambda storage, loc: storage,)
        )
        obj_detect.eval()
        obj_detect.cuda()

        self.prepr_w_tracktor = prepr_w_tracktor
        if self.prepr_w_tracktor:
            self.prepr_params = tracktor_params
        else:
            self.prepr_params = frcnn_prepr_params
        make_deterministic(self.prepr_params["seed"])

        if self.prepr_w_tracktor:
            self.preprocessor = Tracker(obj_detect, None, self.prepr_params["tracker"])
        else:
            self.preprocessor = FRCNNPreprocessor(obj_detect, self.prepr_params)

        self.transforms = ToTensor()
        self.extract_transforms = Compose(
            (
                Resize(self.model.hparams["dataset_params"]["img_size"]),
                ToTensor(),
                Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            )
        )

        self.use_gt = use_gt
        self.pre_cnn = pre_cnn

    def initialize(self, seq_info):
        self.preprocessor.reset()
        if self.prepr_w_tracktor:
            if seq_info["seq_name"] in MOV_CAMERA_DICT.keys():
                self.preprocessor.do_align = (
                    self.prepr_params["tracker"]["do_align"]
                    and MOV_CAMERA_DICT[seq_info["seq_name"]]
                )
        self.seq_info = seq_info
        self.img_paths = []
        self.gts = []

        self.node_embeds = {}
        self.reid_embeds = {}

    def track(self, start_frame, end_frame):
        if self.use_gt:
            feedback = []
            for frame in range(start_frame, end_frame + 1):
                for t in self.gts[frame]:
                    feedback.append(
                        [frame + 1 - start_frame, t[1], t[2], t[3], t[4], t[5]]
                    )
            feedback = np.array(feedback)
        else:
            if self.prepr_w_tracktor:
                all_tracks = self.preprocessor.get_results()
                rows = []
                for i, track in all_tracks.items():
                    for frame, bb in track.items():
                        if frame < start_frame or frame > end_frame:
                            continue

                        x1 = bb[0]
                        y1 = bb[1]
                        x2 = bb[2]
                        y2 = bb[3]
                        rows.append(
                            [
                                frame + 1 - start_frame,
                                i + 1,
                                x1 + 1,
                                y1 + 1,
                                x2 - x1 + 1,
                                y2 - y1 + 1,
                                -1,
                                -1,
                                -1,
                                -1,
                            ]
                        )
                det_df = pd.DataFrame(np.array(rows))
            else:
                raise ValueError("Please make prepr_w_tracktor True")

            if self.pre_cnn:
                reid_embeds = self.reid_embeds
                node_embeds = self.node_embeds
            else:
                reid_embeds = None
                node_embeds = None
            dataset = MOTGraphDataset(
                self.model.hparams["dataset_params"],
                self.img_paths,
                det_df,
                self.seq_info,
                cnn_model=self.model.cnn_model,
                reid_embeddings=reid_embeds,
                node_feats=node_embeds,
                start_frame=start_frame,
            )
            final_out = self.model.track_seq(dataset)
            feedback = final_out.to_numpy()[:, :6]

        return feedback

    def step(self, img_path, det, gt):
        if self.prepr_w_tracktor:
            seq_name = self.seq_info["seq_name"]
            if seq_name in MOV_CAMERA_DICT.keys():
                self.preprocessor.do_align = (
                    self.prepr_params["tracker"]["do_align"]
                    and MOV_CAMERA_DICT[seq_name]
                )

        img = Image.open(img_path).convert("RGB")
        w, h = img.size
        self.seq_info["frame_height"] = h
        self.seq_info["frame_width"] = w
        img = self.transforms(img)

        sample = {}
        sample["img"] = img.unsqueeze(0)
        if det is not None and len(det) > 0:
            bb = np.zeros((len(det), 5), dtype=np.float32)
            bb[:, 0:2] = det[:, 2:4] - 1
            bb[:, 2:4] = det[:, 2:4] + det[:, 4:6] - 1
            sample["dets"] = torch.FloatTensor([d[:4] for d in bb]).unsqueeze(0)
        else:
            sample["dets"] = torch.FloatTensor([]).unsqueeze(0)
        sample["img_path"] = img_path

        with torch.no_grad():
            self.preprocessor.step(sample)

        if self.pre_cnn:
            frame_img = imread(img_path)
            bb_imgs = []
            idx = []
            all_tracks = self.preprocessor.get_results()
            for i, track in all_tracks.items():
                for frame, bb in track.items():
                    if frame == len(self.img_paths):
                        bb_img = extract(frame_img, bb, h, w, self.extract_transforms)
                        bb_imgs.append(bb_img)
                        idx.append((i + 1, frame + 1))
            if len(bb_imgs) > 0:
                with torch.no_grad():
                    bb_imgs = torch.stack(bb_imgs)
                    node_out, reid_out = self.model.cnn_model(bb_imgs.cuda())
                    node_out = node_out.cpu()
                    reid_out = reid_out.cpu()
                    for n, (i, frame) in enumerate(idx):
                        node_embed = self.node_embeds.get(i, dict())
                        node_embed[frame] = node_out[n]
                        self.node_embeds[i] = node_embed

                        reid_embed = self.reid_embeds.get(i, dict())
                        reid_embed[frame] = reid_out[n]
                        self.reid_embeds[i] = reid_embed

        self.img_paths.append(img_path)
        self.gts.append(gt)
