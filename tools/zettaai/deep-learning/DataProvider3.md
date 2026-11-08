# DataProvider3 (ZettaAI fork)

**GitHub:** https://github.com/ZettaAI/DataProvider3
**Language:** Python | **Status (2026-11-06):** fork of seung-lab/DataProvider3, 7 ahead; last push 2026-08-27

Patch sampler/data provider for DeepEM. Upstream: [../../seung-lab/deep-learning/DataProvider3.md](../../seung-lab/deep-learning/DataProvider3.md).

## ZettaAI-only changes
- 2022: super-resolution outputs; 2023: cap on consecutive out-of-range errors (10,000); user-selected sampling dataset (`DataSuperset`).
- 2026-03: **mask locations accumulated by union** instead of overwritten (a bug that silently dropped valid sample locations); `DataSuperset` repr shows child datasets and sampling weights.
- 2026-04 / 2026-08 (`perf/rejection-sampling`, `perf/locs-bbox-rejection`, PR #2): replace `flatnonzero` index arrays with **rejection sampling inside the mask's bounding box**, falling back to an exact index array for small masks; the representation is decided before worker fork.

## Takeaway
For large sparse training masks, storing every valid voxel index costs GBs per worker; bounded rejection sampling with an exact fallback keeps memory flat. Directly relevant to PyTC samplers on large LICONN/NISB volumes.
