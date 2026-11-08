# voxelflow

**GitHub:** https://github.com/e11bio/voxelflow
**Language:** Nextflow | **Stars:** 0

E11's own Nextflow workflow for **stitching and registration** of large microscopy
acquisitions. Wraps BigStitcher / BigStitcher-Spark / BigWarp behind reproducible,
container-executed pipeline steps, with both dask and Spark backends.

## Top-level workflows (`*.nf`)
| Entry | Purpose |
|-------|---------|
| `convertImgs.nf` | Convert raw acquisition images → zarr/N5 |
| `initOme.nf` | Initialize an OME-Zarr container |
| `fiducialStitch.nf` | Stitch using fiducial markers |
| `phaseCorrStitch.nf` | Stitch by phase correlation |
| `addRound.nf` | Register a new imaging round onto an existing volume (iterative immunolabeling) |
| `render.nf` | Render/fuse the final volume |
| `startDask.nf` | Bring up a dask cluster for the run |

## Process modules (`processes/`)
`bigstitcher.nf` · `registration.nf` · `zarr.nf` · `meta.nf` · `utils.nf`
Backends: `nextflow-dask/` (`dask_params.nf`, `dask_process_utils.nf`, `processes.nf`,
`workflows.nf`) and `nextflow-spark/` (`params_utils.nf`, `processes.nf`, `workflows.nf`).

## Containers (`singularity/`)
Apptainer/Singularity definitions built with `make`:
- `bigstitcher/` — Fiji + BigStitcher, with ImageJ macros
  (`fiducial_stitching.ijm`, `simple_pairwise.ijm`, `copy_transform_channels.ijm`)
- `bigstitcher-spark/` — Spark distribution of BigStitcher
- `pyvoxelflow/` — the Python side

## Usage
```bash
nextflow convert_imgs.nf \
  --inputFolder /mnt/galaxybrain/compute/test-data \
  -profile local -c process_settings.config

cd singularity/bigstitcher && make    # build containers
```

Config: `nextflow.config`, `process_settings.config`. Tested with `nf-test`
(`tests/processes/*.nf.test`, plus a 2-tile N5 fixture under `tests/test-data/`).

## Relevance to PyTC
The most complete open example of a **cluster-portable, containerized pre-segmentation
pipeline** for multi-round microscopy — particularly `addRound.nf`, which is the iterative-
immunolabeling registration step that has no equivalent in EM pipelines. Read it before
building stitching orchestration for the lab's ExM/light-sheet data; the nf-test fixtures
also show the expected BigDataViewer XML + N5 layout.

Related: [prepipe-containers](prepipe-containers.md),
[BigStitcher-Spark](../stitching-registration/BigStitcher-Spark.md),
[nf-BigStitcher-Spark](../stitching-registration/nf-BigStitcher-Spark.md).
