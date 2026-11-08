# E11 Bio Repository Index

**GitHub:** https://github.com/e11bio (29 repos) · **Site:** https://e11.bio
**Surveyed:** 2026-08-05

E11 Bio — nonprofit focused research org building **PRISM** (Protein Reconstruction and
Identification through Multiplexing): viral protein barcoding + expansion microscopy +
iterative immunolabeling for neuron reconstruction. Where seung-lab reconstructs from **EM**,
E11 reconstructs from **multiplexed light microscopy** — the barcodes are extra channels that
make merges self-correcting. Per-repo docs are in [`e11bio/`](e11bio/).

The org is small and unusually legible: **12 original repos, 17 forks**, and most forks are
pinned dependencies rather than real work. Only 5 forks carry meaningful E11 changes
(marked ⚡ below).

## Directory Structure

```
e11bio/
├── core-libs/               (3)  volara framework + CLI tools (PyPI packages)
├── deep-learning/           (4)  PRISM models, gunpowder/dacapo/lsd forks
├── stitching-registration/  (6)  BigStitcher stack, SOFIMA, BigStream
├── pipelines-infra/         (6)  Nextflow workflows, containers, cluster/IO plumbing
├── visualization-io/        (4)  Neuroglancer, BDV, vendor formats, Fiji scripts
└── datasets-papers/         (6)  Open data, barcode analysis, wet-lab QC
```

## Start here (highest value for PyTC)

| Repo | Why |
|------|-----|
| **[volara](e11bio/core-libs/volara.md)** | Declarative blockwise framework over Daisy — affinities → mutex watershed → region graph → LUT → segments, resumable by construction. The single best-designed thing in the org. |
| **[prism_training](e11bio/deep-learning/prism_training.md)** | Working MTLSD 3D UNet + contrastive embedding loss + **channel-agnostic training** for multiplexed data. Released checkpoints. |
| **[e11-open-data](e11bio/datasets-papers/e11-open-data.md)** | Free anonymous S3: ~10M µm³ hippocampal CA3, 23 molecular channels, dense + proofread segmentation, skeletons, synapse masks. |
| **[sofima](e11bio/stitching-registration/sofima.md)** ⚡ | E11's multichannel patch to Google's JAX optical-flow aligner — averages per-channel correlograms before peak detection. |
| **[volara-ml](e11bio/core-libs/volara-ml.md)** | Model-shape-contract-as-data inference over huge volumes; torch and jax behind one interface. |

## Core Libraries (PyPI)

| Package | Repo | Stars | What it is |
|---------|------|-------|------------|
| `volara` | [volara](e11bio/core-libs/volara.md) | 45 | Blockwise ops on large nD volumes (Daisy + pydantic + zarr) |
| `volara-ml` | [volara-ml](e11bio/core-libs/volara-ml.md) | 1 | `Predict` task — torch/jax inference plugin for volara |
| `nps-cli` | [nps](e11bio/core-libs/nps.md) | 2 | Distributed point-cloud sampling from segmentation volumes |

## Deep Learning

| Repo | Stars | Fork of | Description |
|------|-------|---------|-------------|
| **[prism_training](e11bio/deep-learning/prism_training.md)** | 7 | — | 5 PRISM models: enhancement, affs+LSDs, uniform embedding, barcode expression, synapses |
| **[dacapo](e11bio/deep-learning/dacapo.md)** ⚡ | 0 | funkelab/dacapo | +24 commits: funlib UNet architecture, affinity-task path, channel-wise augments |
| **[gunpowder](e11bio/deep-learning/gunpowder.md)** ⚡ | 0 | funkelab/gunpowder | +3 commits, all in `RandomLocation` |
| **[lsd](e11bio/deep-learning/lsd.md)** | 0 | funkelab/lsd | Unmodified 2022 snapshot — see [`tools/lsd.md`](lsd.md) |

## Stitching & Registration

| Repo | Stars | Fork of | Description |
|------|-------|---------|-------------|
| **[sofima](e11bio/stitching-registration/sofima.md)** ⚡ | 0 | google-research/sofima | +14: multichannel flow estimation (JAX, GPU) |
| **[streamline](e11bio/stitching-registration/streamline.md)** ⚡ | 0 | JaneliaSciComp/bigstream | +6: E11 BigStream customization (dask, CPU-distributed) |
| **[BigStitcher-Spark](e11bio/stitching-registration/BigStitcher-Spark.md)** ⚡ | 0 | JaneliaSciComp/BigStitcher-Spark | +3 in `SparkPairwiseStitching` |
| **[mpicbg](e11bio/stitching-registration/mpicbg.md)** ⚡ | 0 | axtimwalde/mpicbg | branch `prepipe`: fix `optimizeConcurrently` crash on disconnected tiles |
| **[multiview-reconstruction](e11bio/stitching-registration/multiview-reconstruction.md)** ⚡ | 0 | JaneliaSciComp/multiview-reconstruction | branch `prepipe`: re-enable concurrent solver in `GlobalOptIterative` |
| **[nf-BigStitcher-Spark](e11bio/stitching-registration/nf-BigStitcher-Spark.md)** | 0 | JaneliaSciComp/nf-BigStitcher-Spark | Unmodified mirror |

## Pipelines & Infrastructure

| Repo | Stars | Fork of | Description |
|------|-------|---------|-------------|
| **[voxelflow](e11bio/pipelines-infra/voxelflow.md)** | 0 | — | Nextflow stitching/registration workflow; dask + Spark backends, singularity defs. `addRound.nf` = iterative-immunolabeling registration |
| **[prepipe-containers](e11bio/pipelines-infra/prepipe-containers.md)** | 0 | — | `ghcr.io/e11bio/bigstitcher-spark` — assembles the two `prepipe` patches |
| **[funlib.persistence](e11bio/pipelines-infra/funlib.persistence.md)** | 0 | funkelab/funlib.persistence | World-coordinate array/graph interfaces (+1, 128 behind — use upstream) |
| **[scale_pyramid](e11bio/pipelines-infra/scale_pyramid.md)** ⚡ | 1 | funkelab/scale_pyramid | Daisy-parallel zarr/N5 pyramid builder (+1) |
| **[ClusterWrap](e11bio/pipelines-infra/ClusterWrap.md)** | 0 | JaneliaSciComp/ClusterWrap | `@cluster` decorator over dask-jobqueue (unmodified) |
| **[funlib.run](e11bio/pipelines-infra/funlib.run.md)** | 0 | funkelab/funlib.run | LSF `bsub` wrapper (unmodified, upstream dead since 2021) |

## Visualization & I/O

| Repo | Stars | Fork of | Description |
|------|-------|---------|-------------|
| **[funlib.show.neuroglancer](e11bio/visualization-io/funlib.show.neuroglancer.md)** ⚡ | 1 | funkelab/funlib.show.neuroglancer | +14: multi-scale layer + `add_layer` + CLI |
| **[pybdv](e11bio/visualization-io/pybdv.md)** | 0 | constantinpape/pybdv | numpy/HDF5/N5 → BigDataViewer XML (unmodified) |
| **[SBReadFile22-Python](e11bio/visualization-io/SBReadFile22-Python.md)** | 0 | 3i-microscopes/SBReadFile22-Python | SlideBook `.sldy` reader (unmodified) |
| **[fiji-friends](e11bio/visualization-io/fiji-friends.md)** | 1 | — | Fiji macros: MIPs, ND2→TIFF, montages, corrupt-tile repair |

## Datasets & Papers

| Repo | Stars | Description |
|------|-------|-------------|
| **[e11-open-data](e11bio/datasets-papers/e11-open-data.md)** | 8 | PRISM dataset index: `s3://e11bio-prism/ls`, ~10M µm³, 23 channels, CC BY-SA 4.0 |
| **[Preprint-Barcode-Analysis](e11bio/datasets-papers/Preprint-Barcode-Analysis.md)** | 1 | Barcode length/collision/bimodality analysis + multi-annotator soma zarrs |
| **[combinatorics_dash](e11bio/datasets-papers/combinatorics_dash.md)** | 0 | n-choose-k barcode-space design; birthday-problem collision math |
| **[pool-analysis](e11bio/datasets-papers/pool-analysis.md)** | 0 | Nanopore QC of AAV viral pool balance (minimap2/samtools/bcftools) |
| **[well-plate-assay](e11bio/datasets-papers/well-plate-assay.md)** | 0 | Nikon Elements well-plate assay processing (dormant since 2022) |
| **[open-data-registry](e11bio/datasets-papers/open-data-registry.md)** | 0 | AWS Open Data fork used to register `s3://e11bio-prism` |

## E11 vs. seung-lab — how the two stacks map

| Concern | seung-lab | E11 Bio |
|---------|-----------|---------|
| Volume format | Neuroglancer Precomputed (`cloud-volume`) | zarr / OME-Zarr / N5 (`funlib.persistence`) |
| Blockwise driver | `igneous` + `python-task-queue` | `volara` + Daisy |
| Fragment extraction | `abiss`, `watershed`, `zwatershed` | `ExtractFrags` (mutex watershed, `mwatershed`) |
| Agglomeration | mean-affinity (`MMAAPP`), waterz | `AffAgglom`/`DistanceAgglom` → `GraphMWS` LUT |
| Training stack | `DeepEM`, `chunkflow` | `gunpowder` + `dacapo` + `volara-ml` |
| Alignment | `SEAMLeSS`, `corgie`, `feabas` | BigStitcher/Spark, SOFIMA, BigStream |
| Pyramids | `tinybrain`, `igneous downsample` | `scale_pyramid` |
| Imaging modality | EM | Expansion microscopy + multiplexed immunolabeling |

Two things E11 has that seung-lab does not: **barcode channels as segmentation evidence**
(see [combinatorics_dash](e11bio/datasets-papers/combinatorics_dash.md) for what that buys you)
and **channel-agnostic architectures** for volumes whose channel count varies between
acquisitions (see [prism_training](e11bio/deep-learning/prism_training.md)).

## Caveats
- Most forks are **stale relative to upstream** (`funlib.persistence` −128, `streamline` −655,
  `multiview-reconstruction` −374, `open-data-registry` −1819). Install from upstream/PyPI
  unless you specifically need an E11 patch.
- The `mpicbg` and `multiview-reconstruction` patches are on the **`prepipe` branch**, not
  `master` — invisible from the default branch.
- Analysis repos (`Preprint-Barcode-Analysis`, `fiji-friends`) are unpackaged, untested
  script collections. Read and copy; do not depend on them.
