# streamline (E11 fork of BigStream)

**GitHub:** https://github.com/e11bio/streamline
**Fork of:** [JaneliaSciComp/bigstream](https://github.com/JaneliaSciComp/bigstream) (95★)
**Language:** Python | **Stars:** 0 | **License:** MIT
**Divergence:** 6 commits ahead, 655 behind (forked 2023-05-18, last push 2024-05-13)

"BigStream customization for E11." 3D registration for images too large to fit in memory or to
register in one process: chunks the alignment into overlapping blocks, distributes them to dask
workers, and stitches the results into a single smooth transform.

## Capabilities (upstream BigStream)
- Global **affine**, piecewise affine, and piecewise **deformable** alignment
- Feature-point detection, RANSAC affine, random affine search
- Transform application and inversion; linear blending across block boundaries
- Full access to SimpleITK `ImageRegistrationMethod` options
- Ready-made pipelines (e.g. the EASI-FISH registration pipeline) plus modular building blocks

## E11 changes
6 commits across `bigstream/align.py`, `features.py`, `piecewise_align.py`,
`piecewise_transform.py`, `transform.py`, `utility.py`, `README.md`. The README's own TODO list
states what was still open at E11: dask-array input for distributed align, non-isotropic grid
for deformable registration, more feedback on point registration, better distributed-write wait
management.

**Caveat:** 655 commits behind upstream (upstream reached a v1.0 milestone after this fork).
For new work start from `JaneliaSciComp/bigstream` and port the E11 deltas only if needed.

## Installation
```bash
pip install bigstream      # upstream
# or: pip install git+https://github.com/e11bio/streamline
```

Pairs with [ClusterWrap](../pipelines-infra/ClusterWrap.md) for the dask-jobqueue cluster.

## Relevance to PyTC
Candidate for cross-round / cross-modality volume registration on the lab's clusters — it is
CPU-distributed via dask, so it fits SLURM without GPUs, unlike [sofima](sofima.md). The
piecewise-deformable + linear-blending approach is the reference design for stitching
block-wise transforms into a globally smooth one.
