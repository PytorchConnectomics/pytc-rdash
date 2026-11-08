# pybdv (E11 fork)

**GitHub:** https://github.com/e11bio/pybdv
**Fork of:** [constantinpape/pybdv](https://github.com/constantinpape/pybdv) (23★)
**Stars:** 0 | **License:** MIT
**Divergence:** none — snapshot fork (created 2023-05-30; fork point predates creation)

Python tools for **BigDataViewer**: write numpy arrays or existing HDF5/N5 data into the
BDV format (data container + XML metadata), with scale pyramids, multiple setups/timepoints,
and affine transforms per view. The bridge between Python-side processing and the
Fiji/BigStitcher/multiview-reconstruction world, which speaks BDV XML.

**No E11 modifications.**

## Usage
```python
from pybdv import make_bdv

make_bdv(
    volume,                      # numpy array
    "out.h5",                    # or out.n5 for the N5 backend
    downscale_factors=[[2, 2, 2], [2, 2, 2], [2, 2, 2]],
    downscale_mode="mean",
    resolution=[0.08, 0.035, 0.035], unit="micrometer",
    setup_id=0, timepoint=0,
    affine={"tile": [1, 0, 0, dx, 0, 1, 0, dy, 0, 0, 1, dz]},
)

from pybdv.converter import convert_to_bdv     # convert existing h5/n5
from pybdv.metadata import write_affine, get_affine, get_resolution
```

## Relevance to PyTC
Needed whenever the lab's zarr/HDF5 output has to be read by BigStitcher /
multiview-reconstruction, which only consume BDV XML + N5/HDF5. Also the simplest reference for
what the BDV metadata actually contains (per-setup affines, resolution, unit, pyramid levels) —
useful when debugging a stitching run whose transforms look wrong.
