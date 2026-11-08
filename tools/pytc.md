# PyTC (PyTorch Connectomics) — API Reference for AI Agents

> **Purpose:** This document enables AI coding agents to use PyTorch Connectomics (PyTC) as a library through Python API calls. It covers the complete workflow: configuration, model building, data loading, training, inference, decoding, and evaluation.

## Quick Start

```python
# Minimal end-to-end training
from connectomics.config import load_config
from connectomics.training.lightning import (
    ConnectomicsModule, create_datamodule, create_trainer, setup_run_directory
)
from pytorch_lightning import seed_everything

cfg = load_config("tutorials/mito_lucchi++.yaml")
seed_everything(cfg.system.seed)
run_dir = setup_run_directory(cfg)
datamodule = create_datamodule(cfg, mode="train")
model = ConnectomicsModule(cfg)
trainer = create_trainer(cfg, run_dir=run_dir)
trainer.fit(model, datamodule=datamodule)
```

---

## 1. Configuration (`connectomics.config`)

### Loading & Manipulating Configs

```python
from connectomics.config import (
    Config,              # Top-level dataclass
    load_config,         # Load YAML → Config
    save_config,         # Config → YAML file
    merge_configs,       # Merge multiple configs
    update_from_cli,     # Apply dot-notation overrides
    to_dict,             # Config → dict
    from_dict,           # dict → Config
    print_config,        # Pretty-print config
    validate_config,     # Validate config values
    resolve_data_paths,  # Resolve split base paths
)
```

**Load and customize:**
```python
cfg = load_config("tutorials/mito_lucchi++.yaml")
cfg.data.dataloader.batch_size = 4
cfg.optimization.max_epochs = 100
cfg.model.architecture = "mednext"
cfg.model.loss_functions = ["DiceLoss", "BCEWithLogitsLoss"]
cfg.model.loss_weights = [1.0, 1.0]

# Or apply CLI-style overrides
cfg = update_from_cli(cfg, ["data.dataloader.batch_size=8", "optimization.lr=1e-3"])
```

**Config structure (key fields):**
```python
cfg.system.num_gpus          # int: number of GPUs
cfg.system.num_workers       # int: dataloader workers
cfg.system.seed              # int: random seed

cfg.model.architecture       # str: model name (see §2)
cfg.model.in_channels        # int: input channels (default 1)
cfg.model.out_channels       # int: output channels
cfg.model.filters            # list[int]: encoder filter sizes
cfg.model.loss_functions     # list[str]: loss function names
cfg.model.loss_weights       # list[float]: loss weights
cfg.model.deep_supervision   # bool: enable multi-scale loss

cfg.data.train.image         # str|list: training image path(s), supports globs
cfg.data.train.label         # str|list: training label path(s)
cfg.data.val.image           # str|list: validation image path(s)
cfg.data.val.label           # str|list: validation label path(s)
cfg.data.test.image          # str|list: test image path(s)
cfg.data.dataloader.batch_size   # int
cfg.data.dataloader.patch_size   # list[int]: [D, H, W]

cfg.optimization.optimizer       # str: "adamw", "adam", "sgd"
cfg.optimization.lr              # float: learning rate
cfg.optimization.max_epochs      # int
cfg.optimization.scheduler       # str: scheduler name
```

### GPU Utilities

```python
from connectomics.config import (
    get_gpu_info,           # → dict with GPU details
    suggest_batch_size,     # → int: recommended batch size
    get_optimal_num_workers,# → int: recommended num_workers
)
```

---

## 2. Models (`connectomics.models`)

### Building Models

```python
from connectomics.models import build_model

model = build_model(cfg)  # → nn.Module (ConnectomicsModel subclass)
print(model.get_model_info())  # dict with parameter count, architecture details
```

### Architecture Registry

```python
from connectomics.models.arch import (
    list_architectures,          # → list[str]: all registered names
    get_architecture_builder,    # name → builder function
    register_architecture,       # decorator to register custom architectures
    is_architecture_available,   # name → bool
    get_available_architectures, # → dict with grouped architecture info
    ConnectomicsModel,           # ABC base class for all models
)
```

**Available architectures (8 total):**

| Name | Backend | Deep Supervision | Notes |
|------|---------|-----------------|-------|
| `monai_basic_unet3d` | MONAI | No | Simple 3D U-Net, fast |
| `monai_unet` | MONAI | No | U-Net with residual units |
| `monai_unetr` | MONAI | No | Vision Transformer backbone |
| `monai_swin_unetr` | MONAI | No | Swin Transformer (SOTA, memory-heavy) |
| `mednext` | MedNeXt | Yes | Predefined sizes: S/B/M/L |
| `mednext_custom` | MedNeXt | Yes | Full parameter control |
| `rsunet` | PyTorch | Yes | Anisotropic convolutions (EM-optimized) |
| `rsunet_iso` | PyTorch | Yes | Isotropic convolutions |

**MedNeXt config:**
```python
cfg.model.architecture = "mednext"
cfg.model.mednext_size = "S"          # S(5.6M), B(10.5M), M(17.6M), L(61.8M)
cfg.model.mednext_kernel_size = 3     # 3, 5, or 7
cfg.model.deep_supervision = True
```

**Register custom architecture:**
```python
from connectomics.models.arch import register_architecture, ConnectomicsModel

@register_architecture("my_model")
def build_my_model(cfg):
    class MyModel(ConnectomicsModel):
        supports_deep_supervision = False
        output_scales = 1
        def forward(self, x):
            return x  # your model logic
    return MyModel()
```

### Loss Functions

```python
from connectomics.models import create_loss, create_combined_loss, create_loss_from_config
from connectomics.models.loss import list_available_losses

# Single loss
loss_fn = create_loss("DiceLoss")

# Combined losses with weights
loss_fn = create_combined_loss(
    loss_names=["DiceLoss", "BCEWithLogitsLoss"],
    loss_weights=[1.0, 0.5],
)

# From config (uses cfg.model.loss_functions and cfg.model.loss_weights)
loss_fn = create_loss_from_config(cfg)

# List all available
print(list_available_losses())
```

**Available losses:**
- **MONAI:** `DiceLoss`, `DiceCELoss`, `DiceFocalLoss`, `FocalLoss`, `TverskyLoss`, `GeneralizedDiceLoss`
- **PyTorch:** `BCEWithLogitsLoss`, `CrossEntropyLoss`, `MSELoss`, `L1Loss`, `SmoothL1Loss`
- **Custom:** `WeightedBCEWithLogitsLoss`, `WeightedMSELoss`, `WeightedMAELoss`, `GANLoss`
- **Regularization:** `BinaryRegularization`, `ForegroundDistanceConsistency`, `ContourDistanceConsistency`, `NonOverlapRegularization`

---

## 3. Data (`connectomics.data`)

### I/O — Reading and Writing Volumes

```python
from connectomics.data.io import (
    read_volume,    # → np.ndarray: auto-detects format (H5, TIFF, PNG, NIfTI, Zarr)
    save_volume,    # Save array to file
    read_hdf5,      # Read HDF5 with optional dataset/slice
    write_hdf5,     # Write array(s) to HDF5
    get_vol_shape,  # → tuple: shape without loading data
)

# Read any supported format
image = read_volume("data/train_image.h5")            # HDF5
image = read_volume("data/volume.tif")                 # TIFF stack
image = read_volume("data/volume.nii.gz")              # NIfTI

# Write
save_volume("output.h5", prediction, dataset="main", file_format="h5")
write_hdf5("output.h5", data_array, dataset="main", compression="gzip")

# Get shape without loading
shape = get_vol_shape("data/train_image.h5")  # e.g., (100, 4096, 4096)
```

### Datasets

```python
from connectomics.data.dataset import (
    CachedVolumeDataset,      # Pre-loads volumes into RAM, crops with numpy
    LazyZarrVolumeDataset,    # Lazy zarr reads (low memory)
    MonaiFilenameDataset,     # Loads pre-tiled images from JSON
    create_data_dicts_from_paths,  # Create MONAI-style data dicts
    split_volume_train_val,   # Split single volume into train/val
)

# Create MONAI-style data dictionaries
data_dicts = create_data_dicts_from_paths(
    image_paths=["train_image.h5"],
    label_paths=["train_label.h5"],
    mask_paths=None,
)
# → [{"image": "train_image.h5", "label": "train_label.h5"}]

# CachedVolumeDataset (recommended for moderate-size volumes)
dataset = CachedVolumeDataset(
    image_paths=["train_image.h5"],
    label_paths=["train_label.h5"],
    patch_size=(128, 128, 128),
    iter_num=1000,           # samples per epoch
    transforms=transforms,   # MONAI Compose
    mode="train",
)

# Split single volume for train/val
train_slices, val_slices = split_volume_train_val(
    volume_shape=(100, 4096, 4096),
    train_ratio=0.8,
    axis=0,  # split along Z
)
```

### Augmentation (MONAI Transforms)

```python
from connectomics.data.augment import (
    build_train_transforms,   # → monai.transforms.Compose
    build_val_transforms,     # → Compose (no augmentation)
    build_test_transforms,    # → Compose (no crop, for sliding window)
    # Connectomics-specific transforms (not in standard MONAI):
    RandMisAlignmentd,        # Section misalignment artifact
    RandMissingSectiond,      # Missing section artifact
    RandMissingPartsd,        # Partial section loss
    RandMotionBlurd,          # Motion blur artifact
    RandCutNoised,            # Cut noise augmentation
    RandCutBlurd,             # Cut blur augmentation
    RandMixupd,               # Mixup augmentation
    RandCopyPasted,           # Copy-paste augmentation
)

train_transforms = build_train_transforms(cfg)
val_transforms = build_val_transforms(cfg)
test_transforms = build_test_transforms(cfg)

# Use skip_loading=True when data is already loaded (e.g., CachedVolumeDataset)
augment_only = build_train_transforms(cfg, skip_loading=True)
```

### Label Processing (Target Generation)

```python
from connectomics.data.process import (
    # Primary entry point
    create_label_transform_pipeline,  # Build label transform pipeline from config

    # Individual MONAI transforms for label processing
    MultiTaskLabelTransformd,         # Multi-task label generation
    SegToBinaryMaskd,                 # Segmentation → binary mask
    SegToAffinityMapd,                # Segmentation → affinity map
    SegToInstanceBoundaryMaskd,       # Segmentation → instance boundaries
    SegToInstanceEDTd,                # Segmentation → instance EDT
    SegToSemanticEDTd,                # Segmentation → semantic EDT
    SegToFlowFieldd,                  # Segmentation → flow field
    SegToSynapticPolarityd,           # Segmentation → synaptic polarity
    ComputeBinaryRatioWeightd,        # Compute class-balancing weights
)
```

---

## 4. Training (`connectomics.training`)

### Lightning Module

```python
from connectomics.training.lightning import ConnectomicsModule

# Create from config (builds model + loss internally)
model = ConnectomicsModule(cfg)

# Or with pre-built model
import torch.nn as nn
custom_model = build_model(cfg)
model = ConnectomicsModule(cfg, model=custom_model)

# Key methods (called automatically by Lightning Trainer):
# model.training_step(batch, batch_idx)   → loss tensor
# model.validation_step(batch, batch_idx) → loss tensor
# model.test_step(batch, batch_idx)       → predictions
# model.configure_optimizers()            → optimizer + scheduler
# model.forward(x)                        → model output
```

### Lightning DataModule

```python
from connectomics.training.lightning import (
    create_datamodule,        # Factory: cfg → DataModule (RECOMMENDED)
    ConnectomicsDataModule,   # Direct construction
    SimpleDataModule,         # Wraps pre-built DataLoaders
)

# Recommended: factory function handles all complexity
datamodule = create_datamodule(cfg, mode="train")       # training
datamodule = create_datamodule(cfg, mode="test")        # inference
datamodule = create_datamodule(cfg, mode="tune")        # hyperparameter tuning

# Direct construction (advanced)
datamodule = ConnectomicsDataModule(
    train_data_dicts=train_dicts,
    val_data_dicts=val_dicts,
    transforms={"train": train_tfm, "val": val_tfm},
    batch_size=2,
    num_workers=4,
)

# Wrap existing DataLoaders
datamodule = SimpleDataModule(train_loader, val_loader)
```

### Trainer

```python
from connectomics.training.lightning import create_trainer, setup_run_directory

run_dir = setup_run_directory(cfg)
trainer = create_trainer(
    cfg,
    run_dir=run_dir,
    fast_dev_run=False,    # True for 1-batch debug
    ckpt_path=None,        # resume from checkpoint
    mode="train",          # "train" or "test"
)

# Train
trainer.fit(model, datamodule=datamodule)

# Test
trainer.test(model, datamodule=datamodule)

# Resume from checkpoint
trainer.fit(model, datamodule=datamodule, ckpt_path="path/to/checkpoint.ckpt")
```

### Optimizer & Scheduler

```python
from connectomics.training.optim.build import build_optimizer, build_lr_scheduler

optimizer = build_optimizer(cfg, model)
scheduler = build_lr_scheduler(cfg, optimizer)
```

**Supported optimizers:** `adamw` (default), `adam`, `sgd`

**Supported schedulers:** `cosineannealinglr` (default), `cosineannealingwarmrestarts`, `steplr`, `multisteplr`, `reducelronplateau`, `warmupcosine`, `constant`

### Loss Orchestration

```python
from connectomics.training import LossOrchestrator, match_target_to_output

# LossOrchestrator handles multi-loss + deep supervision automatically
# Usually created internally by ConnectomicsModule
```

### Callbacks

```python
from connectomics.training.lightning import (
    NaNDetectionCallback,         # Detect NaN losses, optionally stop training
    EMAWeightsCallback,           # Exponential Moving Average of model weights
    ValidationReseedingCallback,  # Reseed RNG for reproducible validation
    VisualizationCallback,        # TensorBoard image logging
)
```

---

## 5. Inference (`connectomics.inference`)

### Inference Manager

```python
from connectomics.inference import (
    InferenceManager,
    build_sliding_inferer,
    TTAPredictor,
)

# InferenceManager wraps sliding window + TTA
manager = InferenceManager(cfg, model, forward_fn=model.forward)

# Run prediction with optional TTA and sliding window
prediction = manager.predict_with_tta(images)  # images: torch.Tensor [B,C,D,H,W]
```

### Sliding Window Inference

```python
from connectomics.inference import (
    build_sliding_inferer,       # → MONAI SlidingWindowInferer or None
    resolve_inferer_roi_size,    # → tuple: ROI size from config
    resolve_inferer_overlap,     # → float|tuple: overlap fraction
    is_2d_inference_mode,        # → bool
)

inferer = build_sliding_inferer(cfg)
# Uses MONAI's SlidingWindowInferer internally
```

### Output Handling

```python
from connectomics.inference import (
    resolve_output_filenames,     # Generate output file paths
    write_outputs,                # Save prediction arrays to disk
    apply_postprocessing,         # Apply post-processing transforms
)
```

---

## 6. Decoding / Post-Processing (`connectomics.decoding`)

### Pipeline API

```python
from connectomics.decoding import (
    apply_decode_mode,           # Apply full decode pipeline from config
    apply_decode_pipeline,       # Apply decode steps to prediction array
    list_decoders,               # → list[str]: available decoder names
)

# From config
segmentation = apply_decode_mode(cfg, prediction_array)

# Manual pipeline
from connectomics.decoding import (
    decode_distance_watershed,
    decode_affinity_cc,
    decode_instance_binary_contour_distance,
)

instances = decode_distance_watershed(prediction)
instances = decode_affinity_cc(prediction)
```

### Post-Processing Utilities

```python
from connectomics.decoding import (
    remove_small_instances,     # Filter by min voxel count
    remove_large_instances,     # Filter by max voxel count
    merge_small_objects,        # Merge small objects into neighbors
    binarize_and_median,        # Threshold + median filter
    watershed_split,            # Split touching instances
    stitch_3d,                  # Stitch tile predictions
    apply_binary_postprocessing,# Full binary post-processing pipeline
)

cleaned = remove_small_instances(instances, min_size=100)
```

### Decoder Registry

```python
from connectomics.decoding import register_decoder, get_decoder

# Register custom decoder
def my_decoder(data, **kwargs):
    return (data > 0.5).astype(int)

register_decoder("my_threshold", my_decoder)

# Use it
fn = get_decoder("my_threshold")
result = fn(prediction)
```

### Hyperparameter Tuning (requires `optuna`)

```python
from connectomics.decoding import (
    optimize_threshold,         # Optimize single threshold
    optimize_parameters,        # Optimize multiple decoding params
    run_tuning,                 # Full tuning pipeline from config
    OptunaDecodingTuner,        # Optuna-based tuner class
)
```

---

## 7. Metrics (`connectomics.metrics`)

### Segmentation Metrics

```python
from connectomics.metrics import (
    # NumPy functions (for evaluation scripts)
    adapted_rand,              # → float: Adapted Rand error
    instance_matching,         # → dict: precision, recall, F1 with Hungarian matching
    instance_matching_simple,  # → dict: relaxed matching (no Hungarian)

    # TorchMetrics wrappers (for Lightning integration)
    AdaptedRandError,          # torchmetrics.Metric
    VariationOfInformation,    # torchmetrics.Metric
    InstanceAccuracy,          # torchmetrics.Metric (with Hungarian matching)
    InstanceAccuracySimple,    # torchmetrics.Metric (relaxed matching)
)

# NumPy evaluation
score = adapted_rand(prediction_labels, ground_truth_labels)

# TorchMetrics (used during training/validation)
metric = AdaptedRandError()
metric.update(preds_tensor, target_tensor)
result = metric.compute()
```

### Skeleton Metrics

```python
from connectomics.metrics import (
    evaluate_image_pair,    # Compare two segmentation images
    evaluate_file_pair,     # Compare two files on disk
    evaluate_directory,     # Evaluate all pairs in a directory
)
```

---

## 8. Common Workflows

### A. Train a Segmentation Model

```python
from connectomics.config import load_config
from connectomics.training.lightning import (
    ConnectomicsModule, create_datamodule, create_trainer, setup_run_directory
)
from pytorch_lightning import seed_everything

# 1. Configure
cfg = load_config("tutorials/mito_lucchi++.yaml")
cfg.model.architecture = "mednext"
cfg.model.mednext_size = "S"
cfg.model.deep_supervision = True
cfg.optimization.max_epochs = 200
cfg.optimization.lr = 1e-3

# 2. Setup
seed_everything(cfg.system.seed)
run_dir = setup_run_directory(cfg)

# 3. Create data + model + trainer
datamodule = create_datamodule(cfg, mode="train")
model = ConnectomicsModule(cfg)
trainer = create_trainer(cfg, run_dir=run_dir)

# 4. Train
trainer.fit(model, datamodule=datamodule)
```

### B. Run Inference on a Volume

```python
from connectomics.config import load_config
from connectomics.training.lightning import ConnectomicsModule, create_datamodule, create_trainer

cfg = load_config("tutorials/mito_lucchi++.yaml")

# Point to test data
cfg.data.test.image = "path/to/test_image.h5"
cfg.data.test.label = "path/to/test_label.h5"  # optional, for evaluation

datamodule = create_datamodule(cfg, mode="test")
model = ConnectomicsModule(cfg)
trainer = create_trainer(cfg, mode="test")

# Load checkpoint and run inference
trainer.test(model, datamodule=datamodule, ckpt_path="path/to/best.ckpt")
```

### C. Load and Evaluate Predictions

```python
from connectomics.data.io import read_volume
from connectomics.metrics import adapted_rand, instance_matching
from connectomics.decoding import remove_small_instances

# Load
pred = read_volume("output/prediction.h5")
gt = read_volume("data/test_label.h5")

# Post-process
pred = remove_small_instances(pred, min_size=500)

# Evaluate
are = adapted_rand(pred, gt)
matching = instance_matching(pred, gt)
print(f"Adapted Rand Error: {are:.4f}")
print(f"F1: {matching['f1']:.4f}")
```

### D. Fine-Tune from Pretrained Weights

```python
cfg = load_config("tutorials/mito_lucchi++.yaml")

# Option 1: Load external weights (resets optimizer state)
cfg.model.external_weights_path = "path/to/pretrained_model.pth"

# Option 2: Resume from Lightning checkpoint (keeps optimizer state)
trainer.fit(model, datamodule=datamodule, ckpt_path="path/to/checkpoint.ckpt")
```

### E. Custom Data Pipeline (No Config)

```python
import torch
from connectomics.models import build_model
from connectomics.models.loss import create_combined_loss
from connectomics.data.io import read_volume
from connectomics.data.dataset import CachedVolumeDataset
from connectomics.data.augment import build_train_transforms
from connectomics.config import load_config

cfg = load_config("tutorials/minimal.yaml")
cfg.model.architecture = "monai_basic_unet3d"
cfg.model.out_channels = 2

model = build_model(cfg)
loss_fn = create_combined_loss(["DiceLoss", "BCEWithLogitsLoss"], [1.0, 0.5])

dataset = CachedVolumeDataset(
    image_paths=["my_image.h5"],
    label_paths=["my_label.h5"],
    patch_size=(64, 64, 64),
    iter_num=500,
    transforms=build_train_transforms(cfg, skip_loading=True),
    mode="train",
)

loader = torch.utils.data.DataLoader(dataset, batch_size=2, num_workers=4)
optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)

for batch in loader:
    pred = model(batch["image"])
    loss = loss_fn(pred, batch["label"])
    loss.backward()
    optimizer.step()
    optimizer.zero_grad()
```

---

## 9. CLI Entry Point

```bash
# Training
python scripts/main.py --config tutorials/mito_lucchi++.yaml

# Testing
python scripts/main.py --config tutorials/mito_lucchi++.yaml --mode test --checkpoint ckpt.ckpt

# Fast debug (1 batch)
python scripts/main.py --config tutorials/mito_lucchi++.yaml --fast-dev-run

# Override config values
python scripts/main.py --config tutorials/mito_lucchi++.yaml \
    data.dataloader.batch_size=8 \
    optimization.max_epochs=200 \
    model.architecture=mednext

# Print resolved config
python scripts/main.py --config tutorials/mito_lucchi++.yaml --debug-config
```

---

## 10. Supported Data Formats

| Format | Extensions | Read | Write |
|--------|-----------|------|-------|
| HDF5 | `.h5`, `.hdf5` | `read_hdf5()` / `read_volume()` | `write_hdf5()` / `save_volume()` |
| TIFF | `.tif`, `.tiff` | `read_volume()` | `save_volume()` |
| PNG stack | `.png` | `read_images()` | — |
| NIfTI | `.nii`, `.nii.gz` | `read_volume()` | `save_volume()` |
| Zarr | `.zarr` | `LazyZarrVolumeDataset` | — |

---

## 11. Installation

```bash
git clone https://github.com/zudi-lin/pytorch_connectomics.git
cd pytorch_connectomics

# Install PyTorch first (match your CUDA version)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# Basic install
pip install -e .

# Full install (all optional features)
pip install -e .[full]

# Verify
python -c "import connectomics; print(connectomics.__version__)"
python -c "from connectomics.models.arch import list_architectures; print(list_architectures())"
```

**Key dependencies:** `torch>=1.8`, `pytorch-lightning>=2.0`, `monai>=0.9.1`, `omegaconf>=2.1`, `h5py`, `cc3d`, `scipy`, `scikit-image`

**Optional:** `optuna` (tuning), `wandb` (experiment tracking), `tifffile` (TIFF support), `neuroglancer` (3D viz)
