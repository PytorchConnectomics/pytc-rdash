# dispim-sim Reference

**dispim-sim** simulates dual-view diSPIM (dual-inverted selective-plane illumination
microscope) observations from a clean 3D volume: it generates the two orthogonal-view
system PSFs from optical parameters, then forward-blurs the input volume with each.
It is a PyTorch port of the core simulation path of the MATLAB repo
[`eexuesong/diSPIM_simulation`](https://github.com/eexuesong/diSPIM_simulation).

Use it to manufacture **paired (clean GT → degraded light-sheet observation) volumes** —
training data for restoration/deconvolution models, or a degradation simulator for
testing segmentation robustness under anisotropic optical blur.

**Location**: `coding/dispim_sim/` (local clone of [`j6k4m8/dispim_sim`](https://github.com/j6k4m8/dispim_sim)).
Note `dw-os/coding/` is gitignored — this is a local sandbox checkout, not vendored into any tracked repo.

| | |
|---|---|
| Package version | `0.1.0`, `requires-python >=3.12` |
| Reviewed at | `ca66882` (2026-08-04) |
| Size | ~1,100 LOC package + ~330 LOC tests (6 test modules) |
| Deps | `torch>=2.4`, `numpy>=2`, `pydantic>=2.8`, `typer`, `tifffile`, `h5py`, `zarr>=3`, `cloud-volume`, `imagecodecs` |
| Build | `hatchling`; env managed by `uv` (`uv.lock` committed) |

## Module map

| Module | LOC | Contents |
|---|---|---|
| `models.py` | 78 | `PSFParams` (pydantic, mirrors `PSF_Generator_Xuesong.m` defaults), `load_psf_params()` |
| `psf.py` | 244 | `detection_psf()`, `light_sheet_profile()`, `imrotate3_y_loose_linear()`, `generate_system_psfs()` |
| `zernike.py` | 145 | `zernike_phase()`, `circular_zernike()`, `convert_index()` — MATLAB `ZernikeCalc` style |
| `ops.py` | 131 | `align_size()`, `flip_psf()`, `weight_2d()`, `normalize_psf_sum()`, `otf_from_psf()`, `rotf_from_psf()`, `fft_convolve_same_circular()` |
| `simulation.py` | 38 | `simulate_dual_view()` → `SimulationResult` |
| `deconvolution.py` | 66 | `dual_view_deconvolution()` — alternating Richardson-Lucy |
| `psf_cache.py` | 139 | `load_or_generate_system_psfs()`, `psf_cache_key/path/payload()` |
| `io.py` | 345 | TIFF / HDF5 / Zarr / CloudVolume readers, `read_volume()`, `write_simulation_outputs()` |
| `devices.py` | 30 | `resolve_device()` — `auto` / `cpu` / `cuda` / `mps` |
| `cli.py` | 88 | typer app; console scripts `simulate` and `dispim-sim` |

Public package surface (`dispim_sim/__init__.py`) is deliberately tiny:
`PSFParams`, `SimulationResult`, `simulate_dual_view`. Everything else is imported by module path.

## Axis conventions — read this first

**This package's internal order is `[Y, X, Z]`, not PyTC's ZYX.** It follows MATLAB
throughout the compute path and converts only at I/O boundaries.

| Boundary | Order | Notes |
|---|---|---|
| Internal compute (all tensors, all PSFs) | `[Y, X, Z]` | MATLAB convention |
| Local TIFF / HDF5 / Zarr read+write | `[Z, Y, X]` | `_as_yxz()` / `_yxz_to_external_zyx()` |
| CloudVolume cutouts | `XYZC` → `[Y, X, Z]` | must be single-channel; multi-channel raises |
| `--bounds` CLI arg | `x0,y0,z0,x1,y1,z1` | end-exclusive, in the selected `--mip` voxel grid |

`_as_yxz()` uses `tifffile` `series.axes` metadata when present; for a 3D array with **no**
axis metadata (HDF5, Zarr) it assumes ZYX. So `standards.md`'s ZYX-on-disk rule holds at the
file boundary — but any tensor you hand to `simulate_dual_view()` or
`dual_view_deconvolution()` directly must already be YXZ.

Output dataset names are `image_blur_A` / `image_blur_B` (plus `psf_A` / `psf_B` when
`--save-psf`), **not** PyTC's `"main"` convention. HDF5 outputs are gzip-compressed.

## PSF model

`generate_system_psfs()` returns `(psf_det, psf_a, psf_b)`, all YXZ, each max-normalized to 1.

1. **Pupil** (`_make_pupil`) — spatial-frequency grid scaled by `pixel_size_um`; wavelength and
   NA divided by `ri_medium`; circular pupil mask at `kr² ≤ (NA/n)²`. Apodization is
   `1/√cos θ` when `use_sqrt_cos_apod` (default on), times an optional Gaussian factor when
   `gaussian_apod < 1`. Emits a **6-component vectorial amplitude** (Exx, Eyx, Ezx, Exy, Eyy, Ezy).
2. **Detection PSF** (`detection_psf`) — defocus phase `(2π/λ)(cos θ − 1)·z` over
   `z = (1..nz − floor(nz/2) − 1)·pixel_depth_um`, plus an optional Zernike aberration phase;
   per-z-plane 2D IFFT of the pupil field; intensity `= Σ|E|²`. `polarization` selects
   `unpolarized`/`scalar` (incoherent sum over all 6 components) or a coherent
   `x` / `y` / `rhc` / `lhc` / numeric-angle-in-degrees state. Optional 1D Gaussian
   `line_fwhm_um` blur along `line_orient` models line-scanning readout.
3. **Light sheet** (`light_sheet_profile`) — Gaussian along Z with FWHM `light_sheet_fwhm_um`,
   broadcast across Y and X. **Ideal sheet: constant thickness, no propagation-dependent waist.**
4. **System PSF A** = detection × sheet, max-normalized.
5. **System PSF B** = PSF A rotated `view_b_angle_degrees` (default 90°) about the MATLAB Y axis
   via `imrotate3_y_loose_linear()` — a centered bilinear `grid_sample` with MATLAB `imrotate3`
   *loose* bounding-box semantics — then `align_size()`-cropped back to `(ny, nx, nz)` and
   re-normalized.

### `PSFParams` defaults

| Field | Default | Field | Default |
|---|---|---|---|
| `light_sheet_fwhm_um` | `8.0` | `polarization` | `"unpolarized"` |
| `lambda_det_um` | `0.525` | `use_sqrt_cos_apod` | `True` |
| `ri_medium` | `1.333` | `gaussian_apod` | `1.0` (must be ≤ 1; `1.0` disables) |
| `na` | `0.64` | `apply_line_blur` | `False` |
| `pixel_size_um` | `0.24` | `line_orient` / `line_fwhm_um` | `"x"` / `1.0` |
| `pixel_depth_um` | `0.24` | `zernike_definition` | `"OSA"` (also `ANSI`/`NOLL`/`WYANT`) |
| `nx`, `ny`, `nz` | `256` each | `zernike_indices` / `_coefficients` | `None` → all-zero, aberration-free |
| | | `view_b_angle_degrees` | `90.0` |

`zernike_coefficients` must match `zernike_indices` in length. When every coefficient is zero
the Zernike path is skipped entirely. Index-set defaults by definition: OSA/ANSI `0..27`,
NOLL `1..28`, WYANT `0..24`.

## Forward model

```python
from dispim_sim.simulation import simulate_dual_view
result = simulate_dual_view(clean_yxz, psf_a, psf_b)   # -> SimulationResult
result.image_blur_a, result.image_blur_b, result.psf_a, result.psf_b
```

Each PSF is `align_size()`d to the volume shape, sum-normalized, then applied via
`fft_convolve_same_circular()` — **circular (periodic) same-size FFT convolution**, matching
MATLAB `fftn`/`ifftn`. Negative values from FFT round-off are clamped to `eps`.

`fft_convolve_same_circular()` prefers `rfftn`/`irfftn` and falls back to full complex
`fftn`/`ifftn` on backends where the real transform is unimplemented (this is the MPS path).

**There is no noise model.** No Poisson/shot noise, no camera read noise, no background,
no bleaching. Output is a pure deterministic blur. Add noise yourself if you need
realistic training data.

## Deconvolution

```python
from dispim_sim.deconvolution import dual_view_deconvolution
est = dual_view_deconvolution(stack_a, stack_b, psf_a, psf_b, iterations=10,
                              constant_initial=False)
```

Alternating dual-view Richardson-Lucy: each iteration does one RL update against view A,
then one against view B. Inputs are min-subtracted and mean-matched to a common level first.
Initial estimate is `(A + B)/2` unless `constant_initial=True`.

The back-projector is `conj(OTF)` — **the exact adjoint of circular convolution**, not the
flipped PSF. Flipping a centered PSF shifts the kernel by one voxel on even-sized axes, which
breaks convergence; that was the fix in `65fe580` and is what `tests/test_deconvolution.py`
pins (40 iterations, 32³ even volume, requires Pearson r > 0.95 against GT).

Full-volume only. The MATLAB repo's **tiled** dual-view deconvolution is not ported —
`ops.weight_2d()` (a port of `Weight.m`, the ramped tile-blending matrix) exists and is
tested, but nothing consumes it yet. This is the obvious next port if you need to deconvolve
volumes larger than device memory. **Not exposed on the CLI.**

## PSF cache

Generated PSFs are cached to `.psf_cache/<sha256>.npz` (gitignored) holding
`psf_det` / `psf_a` / `psf_b` plus `cache_key` and `payload_json`.

The key hashes a canonical JSON payload over: PSF params, dtype, axis order (`"YXZ"`),
cache schema version, generator version string
(`"xuesong-torch-v1-imrotate3-y-loose-linear"`), package version, and `torch.__version__`.
Bump `PSF_GENERATOR_VERSION` in `psf_cache.py` whenever the PSF math changes, or stale
entries will be served.

Writes are atomic (`.tmp` + `replace`). On load, key/payload/shape are all revalidated;
a mismatched or corrupt entry is unlinked and regenerated. Status is one of
`hit` / `miss` / `bypass` and is recorded in the output metadata as `psf_cache_status`.
Explicit `--psf-a`/`--psf-b` inputs never touch the cache.

## CLI

```bash
uv run simulate --in <input> --out <output> [options]
```

| Option | Default | Meaning |
|---|---|---|
| `--in` | required | Local `.tif`, `.h5::/dataset`, `.zarr::/array`, or a CloudVolume precomputed path |
| `--out` | required | Local `.tif`, `.h5`, or `.zarr` **only** |
| `--psf-params` | generator defaults | Inline JSON **or** a path to a JSON file |
| `--psf-a` / `--psf-b` | generated | Precomputed PSF volumes; must be given together; bypass cache |
| `--mip` | `0` | CloudVolume mip level; `--bounds` is interpreted in this grid |
| `--bounds` | whole layer | `x0,y0,z0,x1,y1,z1`, end-exclusive |
| `--device` | `auto` | `auto` → cuda → mps → cpu |
| `--save-psf` / `--no-save-psf` | save | Include PSFs in the output container |
| `--cache` / `--no-cache` | cache | Read/write `.psf_cache/` |

```bash
# local volume, generated PSFs, Apple Silicon
uv run simulate --device mps --in volume.h5::/volume --out simulated.h5

# public precomputed layer, explicit cutout, custom optics
uv run simulate \
  --in precomputed://gs://bucket/dataset/layer --mip 1 --bounds 0,0,0,256,256,128 \
  --out simulated.zarr \
  --psf-params '{"light_sheet_fwhm_um": 8, "nx": 256, "ny": 256, "nz": 256}'
```

TIFF outputs are written as **sibling files** `<out>_A.tif` / `<out>_B.tif`
(+ `_psf_A` / `_psf_B`); HDF5 and Zarr outputs are single containers with named arrays.
Output metadata carries `source`, `device`, `internal_axis_order`, `output_axis_order`,
the full serialized `psf_params`, PSF cache info, and any resolution/mip/bounds metadata
recovered from the input.

`--mip` and `--bounds` are **CloudVolume-only** and raise on local inputs.

## Gotchas

1. **PSF voxel grid is independent of the data voxel grid, and is never resampled.**
   `pixel_size_um` / `pixel_depth_um` describe the PSF's own sampling. If they do not match
   your data's voxel size, the simulated blur is not physically meaningful in µm.
   The bundled H01 experiment hits this: `0.24 µm` MATLAB defaults applied to an
   `8 × 8 × 33 nm` EM cutout — `docs/h01-experiment/plan.md` flags it explicitly as a
   known mismatch. Set these to your data's voxel size for any quantitative use.
2. **PSF `nx/ny/nz` are independent of the input volume shape.** `align_size()` center-crops
   or zero-pads the PSF to the volume shape. A 256³ PSF against a 64³ volume gets its tails
   truncated; against a 1024³ volume it gets zero-padded (fine).
3. **Circular convolution wraps.** No edge padding — expect wrap-around artifacts at the
   volume borders. Pad your input, or crop the margins from the output.
4. **No noise model** (see above).
5. **Internal YXZ ≠ PyTC ZYX.** Only the file-I/O layer converts.
6. **Output arrays are `image_blur_A`/`image_blur_B`, not `"main"`** — regular PyTC readers
   need an explicit dataset selector.
7. **Remote ordinary files are rejected by design.** Remote `.tif`/`.h5`/`.zarr` raise;
   only `precomputed://` cloud paths are supported for reads. Bare `s3://`, `gs://`, `file://`
   are auto-normalized to `precomputed://`. **CloudVolume output is not supported at all** —
   writes are local-only.
8. **CloudVolume cutouts must be single-channel.** Multi-channel raises rather than silently
   picking channel 0. Always pass `--bounds` for precomputed inputs — otherwise the CLI
   requests the entire layer.
9. **Everything runs in `float32`** through the CLI, but `simulate_dual_view()` defaults its
   negative-clamp `small_value` to `float64` eps.
10. **`upstream_matlab/` is an empty gitlink** (mode 160000, commit `60b843b`) with **no
    `.gitmodules` entry** — `git submodule update --init` cannot resolve it without adding a
    URL first. The MATLAB reference is not available locally; read it from the upstream repo.
11. **Only the simulation path is ported.** The MATLAB repo's tiled deconvolution workflow,
    registration, and calibration paths are absent.

## H01 demonstration

`docs/h01-experiment/` is a worked example against public H01 data — the closest thing in the
repo to a connectomics recipe.

| Script | Purpose |
|---|---|
| `extract_h01_cutouts.py` | Pull a `1024 × 1024 × 64` cutout of H01 EM (`4nm_raw`, mip 1) + `c3` segmentation (mip 0) into local Zarrs |
| `render_triples.py` | Render EM / sim-A / sim-B / mean / seg comparison figures (needs `matplotlib`) |

Cutout is centered at XYZ `(318462, 130290, 1988)` at `8 × 8 × 33 nm`. Direct `gs://` access
attempted Google ADC and failed; the working form for this public bucket is the explicit
HTTPS precomputed URL `precomputed://https://storage.googleapis.com/h01-release/data/20210601/4nm_raw`.

```bash
uv run python docs/h01-experiment/extract_h01_cutouts.py
uv run simulate --device mps \
  --in data/h01_em_8nm_center_318462_130290_1988_1024x1024x64.zarr::/volume \
  --out data/h01_dispim_sim_screenshot_params_center_318462_130290_1988_1024x1024x64.zarr \
  --psf-params '{"light_sheet_fwhm_um":8,"lambda_det_um":0.525,"ri_medium":1.333,"na":0.64,"pixel_size_um":0.24,"pixel_depth_um":0.24,"nx":256,"ny":256,"nz":256}' \
  --no-save-psf
uv run --with matplotlib python docs/h01-experiment/render_triples.py
```

The five-panel figure is `EM | sim A | sim B | combined A/B mean | c3 segmentation`. The
"combined" panel is a **plain arithmetic mean for visual comparison only** — not a
deconvolution and not a fused reconstruction. Rendered PNGs are committed under
`docs/h01-experiment/figures/`; `data/` is gitignored.

## Tests

`pytest`, 6 modules. Notable coverage: `align_size` crop/pad symmetry; `rfftn` convolution
equals full-complex `fftn` convolution (including on MPS when available); `imrotate3_y_loose_linear(90°)`
equals `torch.rot90(k=-1)` on the (X, Z) plane; delta-PSF convolution is identity; PSF cache
hit/miss/bypass and key stability across a JSON round-trip; even-volume dual-view RL recovery.
I/O tests monkeypatch `CloudVolume`, so no network is required.

```bash
uv run pytest
```

## Relationship to PyTC

Not integrated. dispim-sim is a standalone simulator with no PyTC dependency and no PyTC
consumer. Two plausible integration paths:

1. **Synthetic paired-data generation** — run the CLI offline over clean GT volumes, then load
   `image_blur_A`/`image_blur_B` as inputs and the GT as target in a PyTC dataset. Simplest,
   and the shape the CLI is already built for. Convert ZYX↔YXZ once at the file boundary.
2. **On-the-fly augmentation** — import `generate_system_psfs()` + `simulate_dual_view()` into a
   `connectomics/data/augmentation/` transform to apply anisotropic light-sheet blur during
   training. Both are pure-torch and device-agnostic, so this works on the training device.
   Cache the PSFs once outside the transform — generation is a 2D-IFFT per z-plane, far too
   expensive per-sample.

For either path, fix gotcha #1 first: set `pixel_size_um`/`pixel_depth_um` to the target
data's voxel size, or the degradation is arbitrary rather than physical.
