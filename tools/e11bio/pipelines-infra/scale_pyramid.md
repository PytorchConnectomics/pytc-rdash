# scale_pyramid (E11 fork)

**GitHub:** https://github.com/e11bio/scale_pyramid
**Fork of:** [funkelab/scale_pyramid](https://github.com/funkelab/scale_pyramid) (0★)
**Language:** Python | **Stars:** 1 | **License:** MIT
**Divergence:** 1 commit ahead, 0 behind (forked 2024-03-19, last push 2026-02-19)

Single-script tool that builds a multi-resolution scale pyramid for nD **zarr/N5** datasets.
Supports multiple channels; parallelizes downsampling with
[daisy](https://github.com/funkelab/daisy).

## E11 change
1 commit touching `scale_pyramid.py` and `.gitignore`.

## Usage
```bash
python scale_pyramid.py --help
```
Typical arguments: input container + dataset, scale factors per level, chunk shape, number of
workers. Writes `s0, s1, s2, …` datasets alongside the source, the layout Neuroglancer and
OME-Zarr readers expect.

## Relevance to PyTC
The zarr/N5 counterpart to seung-lab's `tinybrain` + `igneous image downsample` (which target
Neuroglancer Precomputed). Reach for it when the lab's data is already zarr and a pyramid is
needed for viewing or multi-MIP inference. [volara](../core-libs/volara.md) datasets and
[e11-open-data](../datasets-papers/e11-open-data.md) both use this `s0…s5` convention.
