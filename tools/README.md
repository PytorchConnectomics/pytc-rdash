# tools/ — reusable library & tool reference

Docs on **functions/tools that already exist** in the connectomics ecosystem, so an
agent reuses them instead of rebuilding from scratch. Each `*.md` is a per-library
reference (API surface, conventions, gotchas). Read the relevant doc before writing
new code for a task it already covers.

## PyTC framework & in-house utilities

| Doc | What it covers |
|-----|----------------|
| [pytc.md](pytc.md) | PyTorch Connectomics training/inference framework (this repo's primary code) |
| [em_util.md](em_util.md) | EM I/O (HDF5/TIFF/Zarr/CloudVolume), segmentation ops, metrics, neuroglancer, SLURM |
| [gcs.md](gcs.md) | `gcloud storage` bulk object work — where to run it, cp/mv flag differences, hierarchical-namespace traps, verification |
| [vast.md](vast.md) | VAST Lite annotation tool + export formats |
| [uct_seg.md](uct_seg.md) | MicroCT 3D segmentation toolset (blood vessel, artifact, nuclei) + VAST/SLURM helpers |
| [pytc-deploy.md](pytc-deploy.md) | PyTC deployment / cluster launch |
| [liconn_preprocessing/](liconn_preprocessing/README.md) | LICONN raw → model input: versioned intensity recipes (clip+CLAHE, GAT), resample rule, publish/verify, and all supporting experiments |

## EM reconstruction pipelines

| Doc | What it covers |
|-----|----------------|
| [em_pipeline.md](em_pipeline.md) | Multi-GPU/core engine for large-scale 3D EM neuron segmentation + reconstruction |
| [fiberpipeline.md](fiberpipeline.md) | Fiber (thin-object) reconstruction pipeline |
| [pathfinder.md](pathfinder.md) | PATHFINDER — multi-stage AI agglomeration for exhaustive reconstruction |

## Affinity → segmentation (watershed / agglomeration / losses)

| Doc | What it covers |
|-----|----------------|
| [abiss.md](abiss.md) | ABISS watershed + affinity agglomeration — conventions, threshold traps, sizing, GT-free selection |
| [waterz.md](waterz.md) | Watershed + hierarchical region agglomeration on 3D affinity graphs |
| [waterz_dw.md](waterz_dw.md) | `lib/waterz_dw/` deltas relative to upstream `lib/waterz/` |
| [zwatershed.md](zwatershed.md) | Zwatershed (upstream) |
| [zwatershed_dw.md](zwatershed_dw.md) | Zwatershed donglaiw fork — steepest-ascent watershed + region-graph agglomeration |
| [lsd.md](lsd.md) | Local Shape Descriptors — auxiliary training target (MTLSD) |
| [malis.md](malis.md) | MALIS structured loss for affinity-graph segmentation |
| [floodfilling_final.md](floodfilling_final.md) | Flood-filling networks (FFN) — iterative single-object segmentation |
| [snemi_old.md](snemi_old.md) | Segmentation post-processing helpers (`lib/snemi_old/*.py`) |

## Training frameworks & models

| Doc | What it covers |
|-----|----------------|
| [banis.md](banis.md) | BANIS — MedNeXt predicting 6-channel (short+long-range) affinities |
| [deepem.md](deepem.md) | DeepEM — RSUNet-based EM training (Seung lab) |
| [elektronn3.md](elektronn3.md) | elektronn3 — PyTorch 2D/3D CNN toolkit for bio image data |
| [emvision.md](emvision.md) | PyTorch EMVision — anisotropic-conv EM models |
| [roboem.md](roboem.md) | RoboEM — CNN flight-tracing (self-steering neurite skeletonization) |

## Microscopy simulation & deconvolution

| Doc | What it covers |
|-----|----------------|
| [dispim_sim.md](dispim_sim.md) | diSPIM dual-view PSF generation, forward blur simulation, dual-view Richardson-Lucy |

## Neuron morphology analysis

| Doc | What it covers |
|-----|----------------|
| [NEURD.md](NEURD.md) | Mesh-decomposition framework for automated proofreading + morphological analysis |

## Research workflow

| Doc | What it covers |
|-----|----------------|
| [autoresearch.md](autoresearch.md) | Autonomous research loop: modify code → short train → eval → keep/discard |

## External-org library surveys

Per-org indexes of what already exists elsewhere. Check these before reimplementing.

| Index | Org | Docs | Covers |
|-------|-----|------|--------|
| [seung-lab.md](seung-lab.md) | [seung-lab](https://github.com/seung-lab) (Princeton) | 187, in [`seung-lab/`](seung-lab/) | EM connectomics: cc3d, cloud-volume, kimimaro, igneous, abiss, neuroglancer, … |
| [zettaai.md](zettaai.md) | [ZettaAI](https://github.com/orgs/ZettaAI/repositories) (Seung-lab spin-out) | 60 repos, in [`zettaai/`](zettaai/) | Zetta-only changes in forks (waterz semantic agglomeration, Calcada proofreading, Augmentor/DataProvider3) + archived private DeepEM |
| [e11bio.md](e11bio.md) | [e11bio](https://github.com/e11bio) | 29, in [`e11bio/`](e11bio/) | Multiplexed-LM connectomics (PRISM): volara, prism_training, sofima, BigStitcher stack, open data |

`seung-lab/` groups: `core-libs/`, `io-formats/`, `deep-learning/`, `segmentation-pipeline/`,
`registration/`, `infrastructure/`, `visualization/`, `datasets-papers/`, `julia/`, `misc/`.
`zettaai/` groups: `deep-learning/`, `segmentation-pipeline/`, `io-formats/`, `registration/`,
`proofreading-visualization/`, `infrastructure/`.
`e11bio/` groups: `core-libs/`, `deep-learning/`, `stitching-registration/`,
`pipelines-infra/`, `visualization-io/`, `datasets-papers/`.

The two stacks solve the same problems from opposite ends (EM + Precomputed vs. expansion
microscopy + zarr) — [e11bio.md](e11bio.md) has a side-by-side mapping table.
