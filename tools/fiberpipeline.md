# fiberpipeline Reference

**Location**: `/projects/weilab/weidf/lib/pytorch_connectomics/lib/fiberpipeline`
(nested git repo, remote `github.com/PytorchConnectomics/fiberpipeline`, branch `main`, 3 commits)

End-to-end pipeline for tracing and quantifying **barcoded fibers** in multi-channel
fluorescence microscopy volumes (the `/projects/weilab/dataset/barcode/*` datasets). Given a
4-channel `.tif` stack per sample, it (1) instance-segments fibers and cell somas, (2) fits a
1-D centerline skeleton to every fiber, (3) samples each channel's intensity along that
centerline, (4) normalizes/aligns those 1-D signal profiles, (5) filters fibers by
morphology + soma criteria, and (6) reports per-soma fiber counts and renders results in
napari / Neuroglancer. Total ~2,400 lines. No README; the `justfile` is the entry map.

> **Framework note (important):** the segmentation model runs on the **v1 YACS-based
> PyTorch Connectomics** (`jasonkena/pytorch_connectomics@barcode`, `connectomics.engine.Trainer`,
> `cfg.MODEL.ARCHITECTURE`, uppercase YACS keys) — **not** the v2/v3 Lightning/Hydra framework
> of the surrounding repo. Config is driven by `nicety` (`jasonkena/nicety`), an OmegaConf
> wrapper exposing `get_conf()` / `DotDict` / `dotdict_to_dict`.

## Directory Structure

```
fiberpipeline/
├── config.yaml                     # master run config (nicety/OmegaConf, 81 lines)
├── environment.yaml                # conda env (python 3.13, torch 2.6, micro_sam, napari, ...)
├── justfile                        # stage runner: `just <stage>` / `just everything`
└── fiberpipeline/
    ├── utils.py                    # preprocess_vol (→ C,Z,Y,X), get_basename
    ├── segmentation/
    │   ├── fiber_segmentation.py   # CLAHE → PyTC UNet affinities → BCS watershed (226)
    │   ├── cell_segmentation.py    # micro_sam (SAM) soma instance seg (49)
    │   └── fiber_segmentation_model/   # the v1-PyTC model project
    │       ├── justfile            # `just clahe`, `just train_model`
    │       ├── configs/base_config.yaml  # YACS: unet_3d, 100k iters
    │       ├── configs/bcs_config.yaml   # YACS: 3-head BCS targets/losses
    │       ├── checkpoints/checkpoint_100000.pth.tar  # (referenced; weights not in tree)
    │       └── scripts/{main,preprocess,clahe,postprocess,evaluate}.py
    ├── processing/
    │   ├── skeletonize_fibers.py   # PCA + arc-length spline centerline per fiber (229)
    │   ├── extract_signals.py      # interpn-sample channels+segs along skeletons (105)
    │   ├── normalize_signals.py    # tail-crop + optuna midpoint/scale align + geodesic (241)
    │   ├── validate_fibers.py      # length/PCA/soma filters → is_valid (162)  ← `filter_all` target
    │   └── stats.py                # per-soma valid-fiber counts (87)
    └── plot/
        ├── plot.py                 # interactive napari OR neuroglancer viewer (315)
        ├── plot_signals.py         # matplotlib geodesic-vs-signal profiles (45)
        └── precomputed.py          # numpy → CloudVolume precomputed (mesh/skeleton/downsample) (312)
```

## Pipeline (order from `justfile` → `just everything`)

```
4-channel .tif  (C = [soma, fiber, im_2, im_3];  preprocess_vol → C,Z,Y,X)
   │
   ├─ fiber_segmentation ──> *-fiber_aff.h5 (3ch BCS) ──> *-fiber_seg.h5 (instances)
   │      clahe(fiber ch) → PyTC unet_3d inference → bcs_watershed
   │
   ├─ cell_segmentation ───> *-cell_seg.h5
   │      micro_sam automatic_instance_segmentation on soma ch (vit_b_lm)
   │
   ├─ fiber_skeleton ──────> *-fiber_skel.npz   (per-instance PCA+spline centerline)
   ├─ extract_signals ─────> *-signals.npz      (interpn each channel + both segs along skel)
   ├─ normalize_signals ───> *-normalized_signals.npz (crop, midpoint-align, geodesic axis)
   ├─ filter_all ──────────> *-final_signals.npz (validate_fibers: is_valid mask + criteria)
   └─ stats ───────────────> stats.npz          (valid fibers per soma)

   plot / plot_signals: interactive visualization (not part of `everything`)
```

Every stage globs the previous stage's output in `conf.output_path` and processes each
sample independently; filenames carry the stage suffix (`get_basename` strips the last
`-`-delimited token).

## Stage Details

### fiber_segmentation.py
- `clahe_parallel`: per-Z-slice OpenCV CLAHE (`tile_size`, `clip_limit`) on the **fiber
  channel only**, joblib-parallel.
- `generate_affinities`: writes CLAHE'd volume to a tempdir, builds a v1-PyTC YACS config on
  the fly by merging `base_config.yaml` + `bcs_config.yaml` (via `nicety.get_conf`),
  overrides `INFERENCE.*` paths + `SAMPLES_PER_BATCH`, then calls `pytc_main()` →
  `connectomics.engine.Trainer(mode="test")` with `checkpoint_100000.pth.tar`. Output:
  3-channel affinity `*-fiber_aff.h5`.
- `bcs_watershed`: **B**oundary/**C**ontour/**S**keleton-distance watershed (adapted from
  legacy `connectomics.utils.process`). Input `(3,Z,Y,X)` = `[semantic, boundary, distance]`;
  seeds = `semantic>thres1 & boundary<thres2 & distance>thres4`, foreground =
  `semantic>thres3 & distance>thres5`, `skimage.watershed(-semantic, seed, mask=fg)`, then
  `remove_small_instances`. Thresholds come from `config.yaml:fiber_segmentation.bcs`
  (thres1/2 were tuned to ~0.213 / ~0.623).

### The model (`fiber_segmentation_model/`)
- `base_config.yaml`: `unet_3d`, `residual_se` blocks, GroupNorm, input/output `[33,97,97]`,
  filters `[32,64,96,128,160]`, WarmupCosineLR, `BASE_LR 0.02`, 100k iters, reject-sampling
  (`SIZE_THRES 1000`). Trained on 6 annotated barcode crops (`barcode/train/{1..4_3}`).
- `bcs_config.yaml`: 3 output heads via `TARGET_OPT ["0", "4-0-1", "a-0-40-16-16"]` =
  binary mask / instance contour / skeleton-aware distance transform; losses
  WeightedBCE+Dice (heads 0,1) and WeightedMSE (head 2, weight 4.0); inference acts
  `[sigmoid, sigmoid, tanh]`.
- `scripts/`: `main.py` (train/infer via `get_args`+`Trainer`), `clahe.py` (offline tiled
  CLAHE preprocessing of train volumes), `preprocess.py` (percentile clip + normalize),
  `postprocess.py` (standalone bcs_watershed + `skopt.gp_minimize` threshold search against
  Adapted-Rand), `evaluate.py` (Adapted-Rand precision/recall). `just train_model` runs
  `main.py --config-base configs/base_config.yaml --config-file configs/bcs_config.yaml`.

### cell_segmentation.py
- `micro_sam` (`get_predictor_and_segmenter` + `automatic_instance_segmentation`) on the
  **soma channel** (channel 0). Model `vit_b_lm` (SAM ViT-B, light-microscopy finetune).
  Output `*-cell_seg.h5`.

### skeletonize_fibers.py
- Per fiber instance (bbox from `em_util.io.box.compute_bbox_all`), `fit_cylinder_spline_pca`:
  scale Z by `manual_z_scale`, normalize to unit sphere, PCA, use 1st PCA axis as spline
  parameter, `splprep`/`splev`, then **arc-length reparameterize** so samples are
  equidistant along the centerline. `extrapolate=[-0.2,1.2]` samples past the endpoints
  (tails trimmed later). Returns a `cloudvolume.Skeleton` (`num_centerline_points` vertices,
  chain edges, `segid = instance label`). Joblib-parallel over instances. Output
  `*-fiber_skel.npz` (`skel_ids`, `skels`).

### extract_signals.py
- `scipy.interpolate.interpn` samples each of the 4 image channels (`method="linear"`) and
  both `fiber_seg`/`cell_seg` (`method="nearest"`) at every skeleton vertex (coords in
  isotropic units via `anisotropy`). Output `*-signals.npz` dict keyed `im_0..im_3`,
  `fiber_seg`, `cell_seg`.

### normalize_signals.py
- `get_tail_crop_points`: crop skeleton tails using the fiber channel (`im_1`) — walk
  outward while the gaussian-smoothed signal keeps rising past the `[0,1]` core.
- `get_midpoint_scale`: **optuna** Bayesian search (`num_trials=100`) for a midpoint index +
  left/right scale that **maximizes the Pearson correlation between the two halves** of the
  `im_2` profile (assumes a symmetric fiber signal about a center).
- `apply_midpoint_scale` resamples both halves to `num_centerline_points/2`; `get_geodesic`
  builds a signed arc-length axis with 0 at the midpoint. Output
  `*-normalized_signals.npz` (`signals`, `skels`, `skel_ids`).

### validate_fibers.py  (the `filter_all` justfile target)
- `evaluate_fiber` per fiber → (geodesic length, 1st-PCA explained-variance ratio =
  straightness, mean soma brightness `im_0`, most-common `cell_seg` label).
- `get_valid` = `length>thres_length & pca>thres_pca_ratio & soma>thres_mean_soma &
  cell_label!=0`, optional `one_per_soma` (keep only the longest valid fiber per soma).
  Output `*-final_signals.npz` (`signals`, `skels`, `skel_ids`, `criteria`, `is_valid`).

### stats.py
- Recomputes a stricter filter (length 800–2000, per-channel min intensities, pca>0.8,
  in-soma) and reports **valid fibers per soma**; writes `stats.npz`.

### plot/
- `plot.py`: interactive `pick` menu → napari (in-memory labels/points, skeletons as colored
  point clouds) **or** Neuroglancer (converts each layer to CloudVolume precomputed in a
  tempdir, serves via `cloudvolume.server`, meshes + skeletons). Optional `validate_fibers`
  masking (`fastremap.mask_except`).
- `precomputed.py`: reusable `to_precomputed` (init info → chunked parallel write → igneous
  downsample → mesh) + `write_skeletons` / `populate_segment_properties`. Strips `uint8`
  vertex attrs (Neuroglancer unsupported).
- `plot_signals.py`: matplotlib overlay of geodesic-vs-intensity for all fibers, per channel.

## config.yaml — key sections

| Section | Notable keys |
|---|---|
| top | `dataset_path`, `output_path=outputs`, `anisotropy=[40,16.3,16.3]`, `to_um=0.01` (Z≈400nm, XY≈163nm), `num_cpus=48`, `num_gpus=1` |
| `fiber_segmentation` | `batch_size`, `checkpoint`/`base_yaml`/`bcs_yaml` (OmegaConf `${_path}` interp), `clahe.{tile_size,clip_limit}`, `bcs.{thres1..5,thres_small}` |
| `cell_segmentation` | `model_type: vit_b_lm` |
| `skeletonize_fibers` | `manual_z_scale=0.33`, `percentile_fit=[0.1,0.9]`, `num_centerline_points=1000`, `extrapolate=[-0.2,1.2]` |
| `normalize_signals` | `gaussian_filter_ratio`, `midpoint_range=[0.45,0.55]`, `scale_range=[-0.2,0.2]`, `num_trials=100` |
| `validate_fibers` | `thres_length=800`, `thres_pca_ratio`, `thres_mean_soma`, `one_per_soma=false` |
| `stats` | `length_thresh=[800,2500]` |
| `precomputed` / `napari` | chunk/downsample/mesh params, `im_shader`, `skel_downsample=5` |

## Data Formats

- **Input**: 4-channel `.tif` volumes (`imageio.volread`); channel order after
  `preprocess_vol` = `C,Z,Y,X` with C = [soma, fiber, im_2, im_3].
- **Affinity / seg**: `.h5` (`main` dataset, gzip).
- **Skeletons / signals / stats**: `.npz` (pickled `cloudvolume.Skeleton` objects and dicts;
  loaded with `allow_pickle=True`).
- **Visualization**: CloudVolume precomputed (image/segmentation + mesh + skeleton).

## Dependencies (environment.yaml)

- **conda**: python 3.13, just, tqdm, h5py, `micro_sam=1.6.0`, `napari=0.6.3`,
  napari-animation, `optuna=4.4.0`, scikit-image, scikit-optimize.
- **pip**: torch 2.6 / torchvision 0.21, `cloud_volume`, fastremap, `igneous_pipeline`,
  neuroglancer, pick, and three git installs:
  - `git+github.com/jasonkena/nicety` — config system (`get_conf`, `DotDict`).
  - `git+github.com/jasonkena/pytorch_connectomics.git@barcode` — **v1 YACS** PyTC providing
    `connectomics.engine.Trainer`, `connectomics.config.load_cfg`,
    `connectomics.utils.process.{remove_small_instances,cast2dtype}`.
  - `git+github.com/PytorchConnectomics/em_util` — `compute_bbox_all`, I/O.

## Gotchas / caveats

- **`just filter_all` runs a non-existent module.** The justfile target is
  `fiberpipeline.processing.filter_all`, but the file on disk is `validate_fibers.py`. Either
  the file was renamed or the justfile is stale — invoke `validate_fibers` directly, or fix
  the target.
- **Two divergent `bcs_watershed` copies** exist (`fiber_segmentation.py` vs
  `fiber_segmentation_model/scripts/postprocess.py`) with different default `thres4`
  (0.50 vs 0.80). `postprocess.py` is a **dev/experimental script and is broken** as written
  (`process_bcs` uses `glob`/`tqdm.tqdm`/`os` without importing them, and passes a path where
  `bcs_watershed` expects a volume). Use the `fiber_segmentation.py` path.
- **`stats.py` hardcodes a second, stricter filter** (im0>100, im1>200, im2/3>20, pca>0.8,
  length 800–2000) that ignores most of the `config.yaml` thresholds — the numbers there are
  the de-facto "final" criteria, not `validate_fibers.*`.
- Model **checkpoint (`checkpoint_100000.pth.tar`) is referenced but not committed**; must be
  present under `fiber_segmentation_model/checkpoints/` for `just fiber_segmentation`.
- Signal alignment assumes a **symmetric fiber intensity profile** (the optuna midpoint step
  maximizes half-to-half Pearson on `im_2`); falls back to midpoint 0.5 if `im_2` absent.
- Runs one sample at a time, whole-volume in memory (no chunked large-volume path).

## Relationship to this repo (pytorch_connectomics v3)

Independent downstream application, **not** wired into the v3 stage pipeline. It depends on
the *legacy* YACS PyTC fork for its fiber model; the only conceptual overlap with the current
tree is the BCS-watershed decoding idea and the `tutorials/fiber_linghu26.yaml` fiber config.
Treat this as a self-contained reference workflow, not a module to import.
