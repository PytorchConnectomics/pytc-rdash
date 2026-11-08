# LSD (Local Shape Descriptors) Reference

**LSD** computes a per-voxel descriptor of local segmentation shape from a label volume.
Used as an auxiliary training target — predicting LSDs alongside affinities (MTLSD)
improves boundary prediction and downstream instance segmentation quality
(Sheridan et al., *Nature Methods* 2022).

**Location**: `lib/lsd/` (vendored copy of `funkelab/lsd`, package name `lsds` on PyPI/conda-forge).

## What an LSD is

For each voxel, compute statistics over a local neighborhood (Gaussian-weighted or
spherical) of the connected segment occupying that voxel:

| Channel group | 3D indices | 2D indices | What it encodes |
|---|---|---|---|
| Mean offset | 0,1,2 | 0,1 | Vector from voxel to local center of mass |
| Orthogonal covariance | 3,4,5 | 2,3 | Variance along principal axes |
| Diagonal covariance | 6,7,8 | 4 | Cross-axis covariance |
| Size | 9 | 5 | Local count |

3D total = **10 channels**; 2D total = **6 channels**. The `components` arg ("012", "0129",
etc.) selects which subset to return — pick the cheapest combination that still helps
downstream training.

## Package layout

```
lib/lsd/lsd/
├── train/
│   ├── local_shape_descriptor.py   # get_local_shape_descriptors(), LsdExtractor (576 lines)
│   └── gp/add_local_shape_descriptor.py  # gunpowder BatchFilter node
├── post/
│   ├── fragments.py                # watershed / watershed_from_affinities / from_boundary_distance
│   ├── agglomerate.py              # LsdAgglomeration (in-memory hierarchical merge)
│   ├── parallel_fragments.py       # blockwise watershed
│   ├── parallel_aff_agglomerate.py # blockwise affinity-based merge (uses waterz)
│   ├── parallel_lsd_agglomerate.py # blockwise LSD-based merge
│   ├── rag.py / shared_rag_provider.py / graph_merge.py
│   ├── persistence/{mongodb,sqlite}_rag_provider.py
│   ├── merge_tree.pyx              # Cython merge-tree (built via setup.py extension)
│   └── local_segmentation.py       # LocalSegmentationExtractor
└── tutorial/
    ├── notebooks/                  # quick_tutorial, train_lsds, train_mtlsd, segment, inference …
    └── scripts/01..05_*.py         # canonical blockwise pipeline (predict → fragments → agglomerate → find_segments → evaluate)
```

## Public entry points

```python
# Compute LSDs directly
from lsd.train import get_local_shape_descriptors, LsdExtractor
lsds = get_local_shape_descriptors(
    segmentation, sigma=(80, 80, 80), components="0123456789",
    voxel_size=(40, 4, 4), mode="gaussian", downsample=2,
)

# Gunpowder training pipeline
from lsd.train.gp import AddLocalShapeDescriptor

# Post-processing
from lsd.post import (
    watershed_from_affinities,
    LsdAgglomeration,
    parallel_watershed, parallel_aff_agglomerate, parallel_lsd_agglomerate,
)
```

## Dependencies

- **gunpowder** — Funke-lab DAG data-pipeline lib; LSD training uses it heavily, all tutorial notebooks/scripts are gunpowder graphs. **Not** PyTorch Lightning / MONAI compatible out of the box.
- **mahotas**, **scipy.ndimage** — Gaussian convolution + watershed.
- **waterz** (Funke lab fork at `funkey/waterz` SHA `8ccd0b3`) — agglomeration backend. Note: distinct from the in-tree `lib/waterz/` PyTC fork.
- **funlib.segment** (Funke lab) — block-graph utilities.
- Optional: MongoDB or SQLite for distributed RAG storage (`post/persistence/`).

## Relationship to PyTC

LSD is **not currently wired into PyTC**:

- The `connectomics/models/losses/` set does not include an LSD target generator.
- `connectomics/data/processing/target.py` produces affinity / distance / contour
  targets, not LSDs.
- The `lib/waterz/` PyTC fork and the `lsd.post.waterz`-based parallel agglomeration
  here are independent codebases (different forks, different APIs).

If integrating MTLSD into PyTC, the cleanest path is:

1. Port `get_local_shape_descriptors` (NumPy, no gunpowder dep) into a new
   `connectomics/data/processing/lsd.py` and register it as a target transform.
2. Add `MTLSDLoss` (wrapper over `BCEWithLogitsLoss` for affinity + `MSELoss` for LSD
   regression) under `connectomics/models/losses/`.
3. Skip everything under `lsd/post/` and `lsd/tutorial/` — those assume
   gunpowder + funlib + the upstream waterz fork and have no analogue in the PyTC
   pipeline. PyTC's existing decoding stage (`connectomics/decoding/`) already covers
   the fragments + agglomeration responsibilities.

## Citation

```bibtex
@article{sheridan_local_2022,
  title  = {Local shape descriptors for neuron segmentation},
  author = {Sheridan, Arlo and Nguyen, Tri M. and Deb, Diptodip and
            Lee, Wei-Chung Allen and Saalfeld, Stephan and Turaga, Srinivas C.
            and Manor, Uri and Funke, Jan},
  journal = {Nature Methods}, year = 2022,
  url = {https://www.nature.com/articles/s41592-022-01711-z},
}
```

Lighter-weight alternative: [`lsd-lite`](https://github.com/funkelab/lsd-lite) — pure-NumPy
LSD/affinity functions without the gunpowder / RAG / persistence stack. Often a better
starting point for embedding LSDs into a non-Funke-stack pipeline like PyTC.
