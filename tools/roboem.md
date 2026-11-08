# RoboEM Reference

**Location:** `/projects/weilab/weidf/lib/pytorch_connectomics/lib/roboem-code-rev2`
**Source:** Springer Nature supplementary code (no public git repo); this tree is the unpacked `41592_2024_2226_MOESM4_ESM.zip` (Nature Methods 2024 supplement 4)
**Paper:** Schmidt M, Motta A, Sievers M, Helmstaedter M. *RoboEM: automated 3D flight tracing for synaptic-resolution connectomics.* Nat Methods (2024). DOI: 10.1038/s41592-024-02226-5
**License:** MPG non-commercial research license (see `RoboEM_license.txt`) — no redistribution, no commercial/clinical use

Automated **flight tracing**: a CNN steers a virtual camera along neurites in 3D EM volumes, producing skeleton tracings (alternative/complement to dense affinity segmentation). On L4 mouse cortex SBEM it reaches ~60 errors/mm axon path length.

## Layout

| Subtree | Purpose |
|---|---|
| `python/RoboEM_Tracer/` | Main inference loop — `tracer2.py`, `taskmanager2.py`, `cachemanager2.py`, `tracing.py`, `trainer.py`, `wkw_data_projection2.py`, `configs/` |
| `python/tf_models/RoboEM_TF2Model/` | TF2 model: `model.py`, `ray_model.py`, `custom_layers.py` |
| `python/libs/roboem-aux/tinterp/` | Cython trilinear interpolation (`pip install .` after env setup) |
| `python/helper_scripts/{msem,sbem}/` | Dataset-specific preprocessing |
| `matlab/` | `startup.m` + helpers (`functions/`, `+Tools/`, `+scripts/`, `mw_file_exchange/{nurbs_toolbox,quiver3D_pub}`) |
| `auxiliaryMethods/` | MATLAB packages: `+Agglo`, `+Cluster`, ... |
| `pipeline/` | `+connectEM/`, `benedikt/` — **incomplete**; needs external L4dense code dropped in |
| `minimal_example/` | `run_roboem.sh`, `writeToNML.m`, expected dirs for `EM_dataset/`, `RoboEM_models/`, `RoboEM_tracings/` |

## Stack & key pins

- Python 3.8.5, TensorFlow **2.3.0**, numpy 1.18.5, h5py 2.10.0
- Ray 1.1, numba 0.52, scikit-image 0.16, networkx 2.5
- WebKnossos toolchain: `wkw 1.1.11`, `wknml 1.0.3`, `wkskel 0.0.2`, `wkcuber 0.8.0`
- MATLAB R2017b; no installation needed for the demo (just start MATLAB from `matlab/`)

## Demo flow

1. **Download SBEM EM volume** (~220 GB, ~5 h @ 100 Mbit) to `minimal_example/EM_dataset/`:
   ```bash
   python minimal_example/EM_dataset/download.py
   ```
2. **Run RoboEM** (~10 min on V100, ~1–2 h on CPU-only 16 cores):
   ```bash
   ./minimal_example/run_roboem.sh
   # uses model rawonly_adaptive_elu_rerun_pol_corr_v3 @ step 700002
   # task: L4_calibration_axons_23.05.2019_ROI2016_corrected.mat
   ```
3. **Export to WebKnossos NML** (~2 min):
   ```bash
   matlab -nodisplay -nosplash -nodesktop -r "run('minimal_example/writeToNML.m'); exit"
   ```
   Pre-canned reference result viewable at https://webknossos.org/links/kYN0JIY29IQPVD8g

## External pieces (not bundled)

- **L4dense MATLAB code** (https://gitlab.mpcdf.mpg.de/connectomics/L4dense) — drop into `pipeline/`, subfolder `L4` into `pipeline/benedikt/L4`
- Ground-truth skeletons for mouse cortex (Motta 2019, Sievers) and human cortex (H01) hosted on MPDL Keeper; URLs in upstream `README.md`

## Relevance to PyTC

- Independent reference for **flight-tracing / agent-based reconstruction** vs PyTC's dense affinity → CC / watershed pipeline.
- Provides skeleton-centric metrics philosophy that PyTC's NERL evaluation already mirrors ([[banis]], `connectomics/evaluation/nerl.py`).
- Useful when comparing tracing-error rates per mm path length against PyTC's per-volume VOI/ARand.
- License **forbids any redistribution**: keep this tree out of any artifacts that get published or shared outside the lab.
