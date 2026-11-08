# uct_seg — MicroCT 3D Segmentation Toolset

Per-target segmentation toolset for microCT / synchrotron volumes (blood vessel,
crack + bright-aggregate artifact, nuclei, dendrite, cell type), plus the shared
I/O, VAST-interop, segmentation-op, neuroglancer, and SLURM helpers the lab's
legacy `ct/T_*.py` scripts were built on.

**Repo:** `/projects/weilab/weidf/lib/uct_seg` (PytorchConnectomics)
**Install:** `pip install -e .`; extras `[viz,cv,cc,pytc,dev]`
**Deps:** numpy, h5py, imageio, scipy, scikit-image; optional cv2, cc3d,
neuroglancer, cloud-volume, torch+yacs

## Status — read this before planning work

| Module | State |
|---|---|
| `util.io` / `util.vast` / `util.seg_ops` / `util.imops` / `util.viz` / `util.butterfly` / `slurm` | done (ported from `ct/`) |
| `nuclei.postproc`, `nuclei.curate` | done (ported) |
| `artifact.mask` | done (ported) |
| `bv` | **preproc only** — CLAHE + median. No model, no inference, no checkpoint |
| `dendrite`, `celltype` | stubs (docstring only) |

**There is no trained segmentation model in this repo and no inference entry
point.** `configs/bv.yaml` is a PyTC training config (3D U-Net, WeightedBCE +
Dice) that expects labeled `IMAGE_NAME` / `LABEL_NAME` volumes; training and
inference run through the `pytc` CLI, not through `uct_seg`. A blood-vessel
result today means either (a) training on labels from `docs/data_paths.md`
(Dyer-17 V0–V4 carry `bv` annotations) or (b) a classical pipeline assembled
from the pieces below. Do not report `uct_seg.bv` output as a model prediction.

## Conventions

- **Volume axis order:** ZYX, matching `em_util`; neuroglancer layers are XYZ
  (`util.viz.ng_layer3` does the transpose).
- **Bounding boxes:** `[z0, z1, y0, y1, x0, x1]` (3D), `[r0, r1, c0, c1]` (2D);
  per-id bbox tables prepend the id, and append the voxel count when
  `do_count=True`.
- **VAST pngs:** 24-bit RGB carrying a uint32 seg id (`seg2vast` / `vast2seg`).
- **Dataset roots:** `scripts/_paths.py` reads `UCT_DL`, `UCT_DL2`, `UCT_DV`,
  `UCT_DW`; defaults point at Harvard mounts, so set them on BC.

## Quick import patterns

```python
from uct_seg.util.io import readh5, writeh5, vast2seg, seg2vast, get_bb, mkdir
from uct_seg.util.imops import im_adjust, histogram_clahe
from uct_seg.util.seg_ops import remove_small, remove_seg, relabel, seg_iou3d
from uct_seg.util.seg_ops import get_bb_label3d_v2, seg_to_count
from uct_seg.util.viz import ng_layer3, launch_viewer
from uct_seg.bv.preproc import preprocess_slice, preprocess_volume
from uct_seg.nuclei.postproc import cc3d_label, filter_dust
from uct_seg.artifact.mask import fuse_crack_bv, apply_artifact_mask
```

## API surface

### `util.io` — files, VAST, bbox
`mkdir(fn, opt='')` (`''`/`'all'`/`'parent'`) · `readtxt` / `writetxt` ·
`readh5(fn, datasetname=None)` / `writeh5(fn, arr, datasetname='main')` ·
`readh5_b` / `writeh5_b` (bit-packed binary masks) ·
`seg2vast(seg)` uint32 → HxWx3 uint8 · `vast2seg(seg)` inverse (2D grayscale
passes through) · `get_bb(seg, do_count=False)` tight bbox over `seg>0` ·
`get_union` / `get_intersect` on bbox vectors · `arr2str`, `print_arr`.

### `util.imops` — intensity
- `im_adjust(I, thres=(1, 99, True), autoscale=None)` — clamp to a percentile
  (or absolute, with `thres[2]=False`) window; `autoscale='uint8'` rescales to
  0–255. This is the quantizer used to take float32 reconstructions to 8-bit.
- `histogram_clahe(im, clip_limit=2.0, tile_grid_size=(8, 8))` — cv2 CLAHE, **2D
  only** (`cv2.createCLAHE().apply` takes a single 8-bit plane), so a volume is
  processed slice by slice. Aliases `imAdjust` / `HistogramCLAHE` exist for
  legacy call sites.

### `util.seg_ops` — segmentation arrays
`get_seg_dtype(mid)` / `cast_to_dtype(seg)` — smallest uint that holds the max
id · `remove_seg(seg, did, invert=False)` LUT-based id removal ·
`remove_small(seg, thres=100, bid=None, invert=False)` · `relabel(seg, uid=None,
do_sort=False)` compact to 1..N · `seg_to_count(seg, do_sort=True,
rm_zero=False)` · `get_bb_label2d_v2` / `get_bb_label3d_v2(seg, do_count=False,
uid=None)` per-id bboxes · `seg_iou3d(seg1, seg2, ui0=None)` best-overlap match
per id (the workhorse for comparing a prediction to GT).

### `util.vast` — annotation interop
`read_vast_meta(fn)` parses a VAST `meta.txt` · `vast_meta_relabel(...)` applies
keyword-based good/bad relabeling (`kw_bad=['bad','not_nuc']` style) ·
`write_vast_anchor_tree_by_id(...)` emits an anchor tree for human review ·
`get_spaced_colors(n)`.

### `util.viz` — neuroglancer
`ng_layer3(data, res, offset=(0,0,0), kind='segmentation')` — ZYX array → XYZ
`LocalVolume` with an explicit `CoordinateSpace` (use this; `ng_layer` is the
legacy positional-`voxel_size` form) · `launch_viewer(ip='localhost',
port=9092)`.

### `bv` — blood vessel
- `preprocess_slice(im, clip_limit=2.0, tile_grid=(8,8), median_ksize=3)` —
  CLAHE then `cv2.medianBlur`, returns uint8. Input must be a 2D uint8 plane.
- `preprocess_volume(src_pattern, dst_pattern, z_range, clip_limit=2.0,
  median_ksize=3)` — per-z png → png, ported from `T_nag.py` opt `0.2`
  (the CLAHE **re-slice**: the legacy pipeline ran it on yz planes, not xy).

The module docstring records the intended pipeline — preproc → PyTC train →
infer → threshold + cc3d → `remove_small` — of which only step 1 exists.

### `nuclei`, `artifact`
`cc3d_label(seg, connectivity=26)` · `filter_dust(seg, dust_sz=25)` ·
`percentile_outlier_ids(values, ids, lo=5, hi=95)` ·
`split_good_bad_by_shape(seg_ids, sphericity, voxel_count, sphe_band=(5,95),
sz_band=(5,95))` · `write_review_meta(meta_path, good_ids, bad_ids, bbs=None,
num_max=8000)` · `fuse_crack_bv(crack_mask, bright_mask)` ·
`apply_artifact_mask(seg, *masks)`.

### `slurm`
`uct-slurm-gen <name> --num N --cmd "<command>"` (entry point
`uct_seg.slurm.gen_jobs:main`), plus `sbatch_header(...)` / `write_jobs(...)`.
Job arrays pass `job_id job_num` as the last two argv, which is the convention
every `scripts/prep_*.py` follows for parallelism.

## `scripts/` — one-shot dataset preps

Each takes a float `opt` selecting a stage, optionally `job_id job_num`:

| Script | Dataset | Notable stages |
|---|---|---|
| `prep_nucmm.py` | Zeiss-Nag NucMM mouse cortex, 720 nm | `8` quantize+resize, `8.1` 500³ crop, `8.3` butterfly JSON, `9` neuroglancer precomputed |
| `prep_nucmm_curate.py` | NucMM curation | `1` stat filter, `1.1` IoU + sphericity, `1.25` VAST relabel + cc3d + dust, `1.26` export pngs |
| `prep_dyer.py` | Dyer-17 Argonne synchrotron, 0.65 µm | `0`/`0.1` → png, `1` nii/nrrd → h5, `1.1` fuse bv+cell, `1.2` semantic → instance |
| `prep_xt_ct.py` | Xiaotang synchrotron, 1.38 µm | `0.1` float32 tiff → 8-bit png, `1.0` ng image pyramid, `1.2` igneous mesh |
| `ng_view.py` | — | neuroglancer viewer presets |

`docs/data_paths.md` lists the source volumes, annotations, and prediction files
these consume (Harvard mounts; needs a BC-side copy or an env override).

## Gotchas

- `histogram_clahe` and `preprocess_slice` are 2D and uint8-only — feeding a 3D
  array or a uint16 plane raises inside cv2. Quantize with `im_adjust` first.
- `preprocess_volume` reads and writes per-slice png through `imageio`; it has
  no h5 or CloudVolume path. For a precomputed volume, pull slices yourself.
- cv2, cc3d, neuroglancer, and torch are optional extras imported lazily inside
  the functions that need them; a missing extra surfaces at call time.
- `scripts/_paths.py` defaults are Harvard `/n/boslfs*` paths that do not exist
  on BC. Set `UCT_DL`/`UCT_DL2`/`UCT_DV`/`UCT_DW` or pass explicit paths.
- `tests/` run on synthetic arrays and need no cluster mounts:
  `python -m pytest tests/`.

## Related

- [em_util.md](em_util.md) — overlapping I/O and seg-op surface, ZYX convention
- [pytc.md](pytc.md) — the trainer `configs/bv.yaml` targets
- [vast.md](vast.md) — annotation formats `util.vast` parses
