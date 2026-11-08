# prism_training

**GitHub:** https://github.com/e11bio/prism_training
**Language:** Python | **Stars:** 7
**Paper:** https://www.biorxiv.org/content/10.1101/2025.09.26.678648v1
**Blog:** https://www.e11.bio/blog/prism

Training scripts and released checkpoints for **PRISM** (Protein Reconstruction and
Identification through Multiplexing) — E11's neuron-reconstruction platform combining viral
barcoding, expansion microscopy, and iterative immunolabeling. This is the flagship E11 repo
for anyone doing segmentation on multiplexed light-microscopy volumes.

Companion data: [e11-open-data](../datasets-papers/e11-open-data.md) (`s3://e11bio-prism/ls`).

## The five models

| # | Model | Directory | What it predicts |
|---|-------|-----------|------------------|
| 1 | Barcode signal enhancement | `train/enhanced/` | Denoised/enhanced barcode channels (default target = **residual** vs. per-object average barcode) |
| 2 | Affinities + LSDs | `train/affs/` | MTLSD head: 3-ch affinities + 10-ch local shape descriptors |
| 3 | Uniform embedding | `train/uniform/` | Per-voxel embedding where L2 distance ≈ barcode dissimilarity |
| 4 | Barcode expression | `train/binary_channel_agnostic/` | Per-channel binary barcode-bit expression |
| 5 | Synapse detection | `train/synapses/excitatory/` | Pre/post synaptic masks |

Each subdirectory has `train.py` (and `view_batch.py` to inspect a batch in neuroglancer);
`train/enhanced/` also has `predict.py`.

## Key Features
- Full 3D UNet + MTLSD implementation in `train/models.py` (`ConvPass`, `Downsample`,
  `Upsample`, `UNet`, `MtlsdModel`, `ChannelAgnosticModel`, `ChannelAgnosticWrapper`,
  `SigmoidWrapper`) — self-contained, no framework dependency beyond torch
- `train/losses.py`: `ContrastiveLoss` (for the uniform embedding),
  `WeightedBCELossMultiChannel`, `WeightedMSELoss`
- `train/nodes.py`: custom gunpowder augmentation nodes for multiplexed data —
  `Blur`, `ChannelWiseIntensityAugment`, `CreateDiff`, `ExpandChannels`, `ShuffleChannels`,
  `SimpleDefectAugment`, `ZeroChannels`
- **Channel-agnostic training** (`ChannelAgnosticModel` + `ShuffleChannels`/`ZeroChannels`):
  the model must not depend on barcode-channel ordering or count — this is the transferable
  trick for multiplexed/multi-round imaging
- `data/download_data.py` + `data/consolidate_data.py` pull the example crop from the public S3

## Stack
gunpowder (pipelines/augmentation) · dacapo (experiment config) · volara (blockwise inference) ·
neuroglancer (visualization) · `uv` for env management.

## Getting started
```bash
git clone https://github.com/e11bio/prism_training.git
cd prism_training/prism_training

cd data && uv run download_data.py && uv run consolidate_data.py && cd ..

# enhancement inference (~10 min on RTX 6000)
cd train/enhanced && uv run predict.py && cd ../..
cp -r data/instance/example_data.zarr/enhanced data/semantic/example_data.zarr/enhanced

# then any model:
cd train/affs && uv run train.py -d enhanced -c model
```
Common flags: `-i N` iterations · `-c model` start from downloaded checkpoint ·
`-d raw|enhanced` input array · `-d false` (enhancement) learn absolute rather than residual barcodes.

Tested on Ubuntu 22.04 + A6000. Post-processing/analysis code is stated to be released separately.

## Relevance to PyTC
The most directly reusable external training code for the lab's multiplexed-imaging work:
a working MTLSD 3D UNet, a contrastive per-voxel embedding loss, and — most usefully — the
channel-agnostic training recipe for volumes whose channel count varies between acquisitions.
The enhancement→affs cascade (predict a cleaned signal first, then segment on it) is a
pattern worth testing on noisy EM/ExM data.

Related: [volara](../core-libs/volara.md), [gunpowder](gunpowder.md), [dacapo](dacapo.md),
[lsd](lsd.md), [e11-open-data](../datasets-papers/e11-open-data.md).
