# lsd (E11 fork)

**GitHub:** https://github.com/e11bio/lsd
**Fork of:** [funkelab/lsd](https://github.com/funkelab/lsd) (70★)
**Language:** Python | **Stars:** 0 | **License:** MIT
**Divergence:** none — snapshot fork, created and last pushed 2022-12-16

Local Shape Descriptors: a 10-channel auxiliary target (per-voxel local mean offset, covariance,
and size of the surrounding object) trained alongside affinities (**MTLSD**). Improves boundary
prediction and gives a cheap merge/split error signal.

**No E11 modifications** — a pinned copy of upstream at Dec 2022. Prefer upstream
`funkelab/lsd` (or the lab's existing [`lsd.md`](../../lsd.md)) for anything current; this
entry exists so the org survey is complete and so you know E11's PRISM affinity models train
against stock LSDs.

## The 10 channels
| Idx | Descriptor |
|-----|------------|
| 0–2 | Mean offset from voxel to local object center of mass |
| 3–5 | Diagonal of the local covariance (object extent along each axis) |
| 6–8 | Off-diagonal covariance (orientation/shear) |
| 9   | Local object size (voxel count in the Gaussian window) |

```python
from lsd.train import LsdExtractor
extractor = LsdExtractor(sigma=(80, 80, 80), downsample=2)
lsds = extractor.get_descriptors(segmentation=labels, voxel_size=(40, 8, 8))
```

## Relevance to PyTC
Already documented for this lab in [`tools/lsd.md`](../../lsd.md). E11 relevance:
[prism_training](prism_training.md)'s `train/affs/` model is an MTLSD head (3 affs + 10 LSDs),
so the LSD sigma/downsample conventions there follow this implementation.
