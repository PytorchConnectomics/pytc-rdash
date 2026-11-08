# elektronn3

Location: `lib/elektronn3/` (vendored clone of ELEKTRONN/elektronn3, master @ `8111e5d`).

A PyTorch-based toolkit for 2D/3D convolutional neural networks, focused on
semantic segmentation of volumetric biomedical (EM/connectomics) image data.
Predates PyTC's Lightning+MONAI stack; kept in-tree as a reference for
custom Trainer, warping-based augmentation, tiled inference, and U-Net
variants. Maintained by the Max Planck Institute of Neurobiology
(M. Drawitsch, P. Schubert; advisor: J. Kornfeld).

## Layout

```
lib/elektronn3/
├── elektronn3/
│   ├── training/      # custom Trainer, SWA, Padam, handlers, metrics
│   ├── data/          # PatchCreator dataset, KNOSSOS sources, transforms/
│   ├── inference/     # Predictor + tiled_apply (overlap-tiled sliding window)
│   ├── models/        # UNet (2D/3D), ResUNet, V-Net, FCN, MSDNet, Tiramisu, simple/
│   ├── modules/       # losses, layers, axial attention, EvoNorm, L1BN, WSConv
│   └── logger.py
├── examples/          # train_unet_neurodata.py, train_simple2d.py,
│                      # train_noise2void.py, inference_h5.py, validate.py
├── benchmark/  docs/
├── pyproject.toml     # name=elektronn3, py>=3.8, deps below
└── requirements.txt
```

~15 K LOC across the package; largest files: `models/resunet.py` (1079),
`training/trainer.py` (1071), `models/unet.py` (1027), `data/cnndata.py` (813),
`inference/inference.py` (710), `data/transforms/transforms.py` (1156),
`modules/loss.py` (737).

## Subpackage summary

### `training/` — Trainer + utilities
- **`Trainer`** (`trainer.py`): general supervised loop for arbitrary
  `(model, criterion, optimizer, train_dataset, valid_dataset)`. Handles
  device placement, AMP (`torch.cuda.amp`), gradient steps, periodic
  validation, preview prediction, tensorboard logging via `tensorboardX`,
  checkpointing (with `Backup`), `NaNException` guard, configurable
  `valid_metrics`, optional semi-supervised path via `unlabeled_dataset` +
  `ss_criterion`. Default log root `~/e3training/`.
- **`SWA`** (`swa.py`): stochastic weight averaging.
- **`Padam`** (`padam.py`): Partially adaptive momentum optimizer.
- **`handlers.py`, `plotting.py`, `metrics.py`, `train_utils.py`,
  `recalibration.py`, `noise2void.py`**: tensorboard hooks, plotting
  helpers, segmentation metrics, calibration, N2V loss helper.
- **`trainer_gnn.py`, `trainer_gnn_batch.py`, `trainer_gnn_minibatch.py`,
  `triplettrainer.py`, `_trainer_multi.py`**: variants for GNN, triplet,
  multi-task training.
- Public API: `from elektronn3.training import Trainer, Backup, Padam, SWA`.

### `data/` — Datasets, sources, augmentations
- **`cnndata.PatchCreator`**: HDF5-backed `torch.utils.data.Dataset` that
  slices 3D patches at random positions. Distinctive feature: applies
  affine/perspective warping to the **sampling coordinates** (not the
  images), interpolating voxels at warped locations — see
  `coord_transforms.py` and `warp_slice()`. Also: `SimpleNeuroData2d`,
  `Segmentation2d`, `Reconstruction2d`.
- **`sources.py`**: `DataSource`, `HDF5DataSource`, `slice_3d` — abstraction
  over HDF5/array sources used by `PatchCreator`.
- **`knossos.py`, `knossos_labels.py`**: KNOSSOS-format volume support.
- **`coord_transforms.py`**: affine/perspective warps in coordinate space.
- **`transforms/transforms.py`**: numpy-based `(inp, target) → (inp', target')`
  transforms. `Compose`, `Lambda`, `RandomSlicewiseTransform`,
  `DropIfTooMuchBG`, `RemapTargetIDs`, `SmoothOneHotTarget`,
  `DistanceTransformTarget`, `Normalize`, `RandomBrightnessContrast`,
  `RandomGammaCorrection`, `RandomGrayAugment`, `RandomGaussianBlur`,
  `RandomBlurring`, `AdditiveGaussianNoise`, `RandomCrop`,
  `ElasticTransform`, `SqueezeTarget`, `RandomFlip`, `RandomRotate2d`,
  `Clahe2d`, `AlbuSeg2d`. Note: unlike torchvision, transforms here
  operate on numpy and on (inp, target) pairs jointly.
- **`transforms/random_blurring.py`, `random.py`, `region_generator.py`**:
  primitives (Normal/HalfNormal/RandInt samplers, region selection).
- **`utils.py`**: misc helpers used by inference/training.

### `inference/` — Tiled / sliding-window prediction
- **`tiled_apply(func, inp, tile_shape, overlap_shape, offset, out_shape)`**:
  generic overlap-tiled application of any `Callable[[Tensor], Tensor]`
  on N-D `(N, C, ...)` tensors. Pads with zeros, supports valid-conv
  `offset`, runs on whichever device `inp` lives on.
- **`Predictor`**: wraps a model + `tiled_apply` for large-volume
  inference; reused by `training.Trainer` for preview images.

### `models/` — Architectures
- **`unet.UNet`**: configurable 2D/3D U-Net with anisotropy support via
  `planar_blocks` (mix 2D/3D conv stages), arbitrary depth, configurable
  normalization, activation, padding. Pure PyTorch. Public via
  `from elektronn3.models.unet import UNet`.
- **`resunet.UNet` + blocks** (`ConvBlock`, `DownBlock`, `UpBlock`,
  `ResizeConv`, `GridAttention`, `DummyAttention`): residual U-Net with
  optional attention gates.
- **`unet3d_lite.py`**: lightweight 3D U-Net.
- **`vnet.py`**: V-Net.
- **`fcn.py`, `fcn_2d.py`**: FCN8s/16s/32s (VGG-backed).
- **`tiramisu_2d.py`** (`FCDenseNet`): 100-layer Tiramisu.
- **`msdnet.MSDNet`**: Multi-Scale Dense Network.
- **`simple.py`**: `Simple3DNet`, `Extended3DNet`, `N3DNet`,
  `StackedConv2Scalar*` for baselines / classification heads.
- **`base.InferenceModel`**: small wrapper used by the inference path.
- `models/__init__.py` is empty — import architectures directly.

### `modules/` — Losses and layers
- **`loss.py`**: `CombinedLoss` (weighted sum), `FocalLoss`,
  `SoftmaxBCELoss`, `GAPTripletMarginLoss`, `MaskedMSELoss`,
  `DistanceWeightedMSELoss`, `DiceLoss`, `FixMatchSegLoss` (semi-sup),
  `NorpfDiceLoss`, `LovaszLoss` (via `lovasz_losses.py`), `ACLoss`
  (active-contour), `MixedCombinedLoss`. Public export:
  `DiceLoss, FocalLoss, LovaszLoss, CombinedLoss, NorpfDiceLoss, ACLoss,
  GAPTripletMarginLoss, FixMatchSegLoss, MaskedMSELoss`.
- **`layers.GatherExcite`**, plus `axial_attention.py`, `evonorm.py`,
  `l1batchnorm.py`, `wsconv.py` (weight-standardized conv).

## Dependencies / install

`pyproject.toml`: `name=elektronn3`, `python>=3.8`, deps: torch, numpy,
scipy, h5py, matplotlib, numba, ipython, imageio, colorlog, tqdm,
scikit-learn, scikit-image, tensorboardX, torchvision. Editable install:
`pip install -e lib/elektronn3`.

## Relationship to PyTC

Strictly a reference / vendored sibling — not imported by `connectomics/*`.
PyTC's own pipeline is Lightning + MONAI + Hydra (`training/lightning/`,
`models/architectures/`, `decoding/`, etc.), and overlapping pieces (custom
Trainer, U-Net, tiled inference, augmentations) live independently inside
`connectomics/`. Use `lib/elektronn3/` for prior-art lookup when working on:

- coordinate-warp augmentation (`data/coord_transforms.py`,
  `cnndata.PatchCreator.warp_slice`) — predecessor pattern to PyTC's
  MONAI-based augmentation in `connectomics/data/augmentation/`.
- overlap-tiled sliding-window inference (`inference/tiled_apply`) —
  compare with `connectomics/inference/sliding.py` and `lazy.py`.
- U-Net design variants (anisotropic `planar_blocks` in `unet.UNet`) —
  PyTC's RSUNet (`models/architectures/rsunet.py`) covers EM anisotropy
  differently.
- Loss zoo (`modules/loss.py`) — PyTC's losses live in
  `connectomics/models/losses/losses.py` and lean on MONAI.

License: MIT (Max Planck Institute of Neurobiology). Status per upstream
`pyproject.toml`: Development Status 3 - Alpha.
