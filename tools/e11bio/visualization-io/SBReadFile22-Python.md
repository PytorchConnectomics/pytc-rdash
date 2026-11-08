# SBReadFile22-Python (E11 fork)

**GitHub:** https://github.com/e11bio/SBReadFile22-Python
**Fork of:** [3i-microscopes/SBReadFile22-Python](https://github.com/3i-microscopes/SBReadFile22-Python) (2★)
**Language:** HTML (docs) + Python | **Stars:** 0 | **License:** BSD-3-Clause
**Divergence:** none — snapshot fork, created and last pushed 2025-10-24

Python reader for **SlideBook `.sldy`** files (Intelligent Imaging Innovations / 3i
microscopes). Vendor SDK wrapper: opens a `.sldy` capture, enumerates images/channels/
timepoints/planes, and returns pixel data plus acquisition metadata (voxel size, channel names,
exposure, stage positions).

**No E11 modifications** — vendored so the acquisition format can be read in the preprocessing
pipeline.

```python
from sbread import SBReadFile
f = SBReadFile()
f.Open("capture.sldy")
f.GetNumCaptures(), f.GetNumChannels(0), f.GetNumPositions(0), f.GetNumZPlanes(0)
plane = f.ReadImagePlaneBuf(image_index, position, timepoint, z, channel)
f.GetVoxelSize(0), f.GetChannelName(0, ch)
```
(Exact method names come from the 3i SDK; see the bundled HTML docs in the repo.)

## Relevance to PyTC
Only relevant if the lab receives raw `.sldy` acquisitions from a 3i/SlideBook microscope.
It marks the front of E11's ingest path: `.sldy` → zarr/N5 (via
[voxelflow](../pipelines-infra/voxelflow.md)'s `convertImgs.nf`) → stitching → segmentation.
