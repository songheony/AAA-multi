# Adaptive Aggregation of Arbitrary Online Trackers <br/> with a Regret Bound for Multiple Object Tracking

## Experts

* [DAN](https://arxiv.org/abs/1810.11780)[<https://github.com/shijieS/SST>]
* [DeepMOT](https://arxiv.org/abs/1906.06618)[<https://github.com/yihongXU/deepMOT/>]
* [DeepSORT](https://arxiv.org/abs/1812.00442)[<https://github.com/nwojke/deep_sort>]
* [Deep-TAMA](https://arxiv.org/abs/1907.00831)[<https://github.com/yyc9268/Deep-TAMA>]
* [MOTDT](https://arxiv.org/abs/1809.04427)[<https://github.com/longcw/MOTDT>]
* [SORT](https://arxiv.org/abs/1602.00763)[<https://github.com/abewley/sort>]
* [Tracktor](https://arxiv.org/abs/1903.05625)[<https://github.com/phil-bergmann/tracking_wo_bnw>]

## Feedback

* [MPNTracker](https://arxiv.org/abs/1912.07515)[https://github.com/dvl-tum/mot_neural_solver]

## Datasets

* [MOT16, MOT17](https://arxiv.org/abs/1603.00831)[<https://motchallenge.net>]
* [MOT20](https://arxiv.org/abs/2003.09003)[<https://motchallenge.net>]

## Frameworks

* py-motmetrics[<https://github.com/cheind/py-motmetrics>] for evaluating trackers.

## Requirements

1. Clone the repository of experts and feedback

    ```sh
    mkdir external
    cd external
    # CenterTrack
    git clone https://github.com/xingyizhou/CenterTrack.git
    # DAN
    git clone https://github.com/shijieS/SST.git
    # DeepMOT
    git clone https://gitlab.inria.fr/yixu/deepmot.git
    # SORT
    git clone https://github.com/abewley/sort.git
    # Tracktor
    git clone https://github.com/phil-bergmann/tracking_wo_bnw.git
    # UMA
    git clone https://github.com/yinjunbo/UMA-MOT.git
    # MPNTracker
    git clone https://github.com/songheony/mot_neural_solver.git
    ```

2. Install necessary libraries with Anaconda 3

    For our framework

    ```sh
    conda create -n [ENV_NAME] python=3.6
    conda activate [ENV_NAME]

    # For AAA
    conda install -y black flake8 pandas seaborn
    conda install -y pytorch torchvision cudatoolkit=[CUDA_VERSION] -c pytorch
    pip install opencv-python

    # For feedback
    # Please refer https://github.com/rusty1s/pytorch_geometric to install torch-scatter, torch-sparse, torch-geometric.
    pip install torch-scatter==latest+[CUDA_VERSION] -f https://pytorch-geometric.com/whl/torch-[TORCH_VERSION].html
    pip install torch-sparse==latest+[CUDA_VERSION] -f https://pytorch-geometric.com/whl/torch-[TORCH_VERSION].html
    pip install torch-geometric
    pip install pytorch-lightning pulp
    conda install scikit-image

    # For evaluation
    pip install motmetrics lapsolver
    ```

    For CenterTrack

    ```sh
    cd external/CenterTrack
    conda create --name CenterTrack python=3.6
    conda activate CenterTrack
    conda install -y pytorch==1.4.0 torchvision==0.5.0 cudatoolkit=[CUDA_VERSION] -c pytorch
    pip install -r requirements.txt

    # For DCNv2
    cd src/lib/model/networks
    git clone https://github.com/CharlesShang/DCNv2.git
    cd DCNv2
    ./make.sh
    ```

    For UMA

    ```sh
    cd external/UMA-MOT
    conda create --name UMA python=3.6
    conda activate UMA
    conda install -y tensorflow-gpu==1.14.0
    pip install -r requirements.txt

    # For our framework
    conda install -y pyyaml pandas
    pip install motmetrics
    ```

    For Tracktor

    ```sh
    cd external/tracking_wo_bnw
    conda create --name Tracktor python=3.6
    conda activate Tracktor
    conda install -y pytorch==1.4.0 torchvision==0.5.0 cudatoolkit=[CUDA_VERSION] -c pytorch
    pip install opencv-python cycler matplotlib

    # For our framework
    conda install -y pyyaml pandas
    pip install motmetrics
    ```

    For DeepMOT

    ```sh
    cd external/deepMOT
    conda create --name DeepMOT python=3.6
    conda activate DeepMOT
    conda install -y pytorch=0.4.1 torchvision cuda92 -c pytorch
    pip install opencv-python==4.0.1.* PyYAML==4.2b1 easydict matplotlib

    # For our framework
    conda install -y pandas
    pip install motmetrics
    ```

    For DAT

    ```sh
    cd external/SST
    conda create --name DAN python=3.6
    conda activate DAN
    conda install -y pytorch=0.4.1 torchvision cuda92 -c pytorch

    pip install opencv-python==3.4.0.12 PyYAML==3.12 matplotlib

    # For our framework
    conda install -y pandas
    pip install motmetrics
    ```

## How to run

## Author

👤 **Heon Song**

* Github: [@songheony](https://github.com/songheony)
* Contact: songheony@gmail.com
