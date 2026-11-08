# sofima (E11 fork)

**GitHub:** https://github.com/e11bio/sofima
**Fork of:** [google-research/sofima](https://github.com/google-research/sofima) (96★)
**Language:** Python / JAX | **Stars:** 0 | **License:** Apache-2.0
**Divergence:** 14 commits ahead, 1 behind (forked 2026-06-09)

SOFIMA = Scalable Optical Flow-based Image Montaging and Alignment. Stitches, aligns, and warps
large 2D/3D/4D microscopy datasets using optical flow regularized by an elastic mesh. Flow
estimator and mesh solver are both JAX → free GPU acceleration.

Core data structure: a **coordinate map** — a dense array of relative offsets (see the module
docstring in `map_utils.py`). Estimated flow fields and mesh node positions share this
representation.

## E11 changes — multichannel support (the reason to use this fork)
14 commits adding channel-aware flow estimation, plus `docs/multichannel.md`.
Touched: `flow_field.py`, `processor/flow.py`, `stitch_elastic.py`, `stitch_rigid.py`,
`tests/flow_field_test.py`, `tests/warp_test.py`.

A `channel` parameter is threaded through all flow-estimation entry points:
- `None` (default) — original single-channel behavior, no breaking change
- `int` — align on one specific channel
- `list[int]` — cross-correlations computed independently per channel and **averaged before
  peak detection**, giving more robust alignment when several channels carry signal

That last mode is exactly what multiplexed/iterative-immunolabeling data needs, where no single
channel is reliably informative everywhere.

## Installation
```bash
pip install git+https://github.com/e11bio/sofima     # multichannel fork
pip install git+https://github.com/google-research/sofima   # upstream
```

## Key modules
`flow_field.py` (flow estimation) · `mesh.py` (elastic mesh solver) · `map_utils.py`
(coordinate maps) · `stitch_rigid.py` (coarse tile offsets) · `stitch_elastic.py` (fine elastic
stitching) · `warp.py` (apply maps) · `processor/` (blockwise drivers).

## Relevance to PyTC
The strongest option for elastic alignment of multi-channel volumes, and the multichannel
patch is a genuinely reusable idea for any cross-correlation-based registration on multiplexed
data — average the per-channel correlograms rather than picking a channel. Compare against
[streamline](streamline.md) (dask/SimpleITK, CPU-distributed) when choosing an aligner:
SOFIMA is GPU/JAX and optical-flow based, streamline is intensity/feature based.
