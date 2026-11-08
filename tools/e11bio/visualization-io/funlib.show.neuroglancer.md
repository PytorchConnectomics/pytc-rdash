# funlib.show.neuroglancer (E11 fork)

**GitHub:** https://github.com/e11bio/funlib.show.neuroglancer
**Fork of:** [funkelab/funlib.show.neuroglancer](https://github.com/funkelab/funlib.show.neuroglancer) (6★)
**Language:** Python | **Stars:** 1
**Divergence:** 14 commits ahead, 16 behind (forked 2023-10-06, last push 2025-01-27)

Scripts and helpers for the [neuroglancer](https://github.com/google/neuroglancer) WebGL
viewer. Upstream provides:
- a layer type for showing **multi-scale volumes** from Python
- a modified `video_tool.py` that works with `LocalVolume`
- a convenience method to add daisy-like arrays to a neuroglancer context

## E11 changes (14 commits)
`funlib/show/neuroglancer/add_layer.py`, `funlib/show/neuroglancer/scale_pyramid.py`,
`scripts/neuroglancer`, `setup.py` — i.e. the layer-adding entry point, the multi-scale layer
implementation, and the CLI script. This is one of the more-modified E11 forks and is the one
[prism_training](../deep-learning/prism_training.md)'s `view_batch.py` scripts rely on for
inspecting gunpowder batches.

## Usage
```python
import neuroglancer
from funlib.show.neuroglancer import add_layer
from funlib.persistence import open_ds

viewer = neuroglancer.Viewer()
with viewer.txn() as s:
    add_layer(s, open_ds("data.zarr/raw"),    "raw")
    add_layer(s, open_ds("data.zarr/labels"), "labels")
print(viewer)
```
```bash
neuroglancer -d data.zarr raw labels     # scripts/neuroglancer CLI
```

`add_layer` reads `voxel_size`/`offset` off a `funlib.persistence` Array, so world coordinates
line up across layers without manual transform setup.

## Relevance to PyTC
Fastest path from "I have a zarr on the cluster" to "I'm looking at it in neuroglancer with
correct physical coordinates," including multi-scale arrays. Compare with `em_util`'s
neuroglancer helpers ([em_util.md](../../em_util.md)) — same job, different array abstraction.
