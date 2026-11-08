# DeepEM (ZettaAI fork) — now private

**GitHub:** https://github.com/ZettaAI/DeepEM (404 since ~2026-09; private)
**Public upstream:** https://github.com/seung-lab/DeepEM (last push 2022-08-18) — see [../../seung-lab/deep-learning/DeepEM.md](../../seung-lab/deep-learning/DeepEM.md), [../../deepem.md](../../deepem.md)
**Archived copy:** Software Heritage, origin `https://github.com/ZettaAI/DeepEM`
**Language:** Python (PyTorch) | **Main authors:** Kisuk Lee, Nico Kemnitz, Ran Lu, Alex (Jabae) Bae, Nicholas Turner, Thomas Macrina

Zetta's production training/inference code for every voxel-wise model behind its reconstruction service (affinities, synapses, mitochondria, nuclei, glia, blood vessels, myelin, folds, semantic compartments, embeddings, super-resolution). The public seung-lab repo stops in 2022; ZettaAI carried on to August 2026.

## Recovery (as of 2026-11-06)

| Source | What it has |
|---|---|
| **Software Heritage** visit 61, **2026-08-25**, status `full` | Every branch, tag and PR head (55 branches, 29 PRs, tags `0.0.1`–`0.0.6`, `S1`, `minnie`). Snapshot `swh:1:snp:a5da2b8efcdd6a8ba2c14dc1ac54a5c788be951d`. Visit 62 (2026-09-06) is `not_found`, so the repo went private between those dates. |
| Wayback Machine | Only 2020-11-28 HTML pages (repo front page, PR #1, insights). No code worth having. |
| GitHub forks | None of `ZettaAI/DeepEM`; the 12 forks of `seung-lab/DeepEM` are older. |

Browse: https://archive.softwareheritage.org/browse/origin/directory/?origin_url=https://github.com/ZettaAI/DeepEM

A full bare git repository (all branches) was requested from the SWH Vault on 2026-11-06
(cook id 422385639). Check its status and download it:

```bash
SNP=swh:1:snp:a5da2b8efcdd6a8ba2c14dc1ac54a5c788be951d
curl -s https://archive.softwareheritage.org/api/1/vault/git-bare/$SNP/          # status: new → pending → done
curl -L -o deepem.git.tar https://archive.softwareheritage.org/api/1/vault/git-bare/$SNP/raw/
tar xf deepem.git.tar && git clone <extracted>.git DeepEM
```

Anonymous API use is limited to 120 requests/hour; a free SWH account token raises it.
Single files can be read without the vault: `/api/1/directory/<dir>/<path>/` then
`/api/1/content/sha1_git:<id>/raw/`. Licence is MIT (inherited from seung-lab).

## Branch timeline (newest first, heads from the 2026-08-25 snapshot)

`master` stopped at 2022-11-03 (ONNX export). Development lives on feature branches:

| Date | Branch | Author | Change |
|---|---|---|---|
| 2026-08-18 | `feature/sr-zero-pad` | K. Lee | RSUNet core that upsamples along z (`models/core/rsunet.py`, `models/v2/`) |
| 2026-05-14 | `feature/class-registry`, `feature/apex-detection` | K. Lee | `ClassSpec` registry; three more APEX subcellular detection heads |
| 2026-04-07 | `feature/synpartner-loss` | K. Lee | WIP 4-headed U-Net and combined loss for synaptic partner assignment |
| 2026-04-02 | `feature/coarse-load` | K. Lee | Docker for rejection-sampling DataProvider3 |
| 2026-03-25 | `feature/val-prefix-syntax`, `feature/exclude-train-ids` | K. Lee | `+val:` inline val ids; exclude samples |
| 2026-03-10 | `mtc_ddp` | K. Lee | DDP for multi-task; PNG-encoded CloudVolumes |
| 2026-03-02 | `feature/sr-cubic-subsample` | K. Lee | separate iso/aniso augmentation for super-resolution |
| 2026-02 | `nkem/feat-ema`, `nkem/feat-focalloss`, `nkem/wandb-viz`, `nkem/fix-zettasets-src` | N. Kemnitz | EMA weights, focal loss, wandb, zettasets fallback |
| 2026-01-14 | `feature/tta-memory-optimization` | K. Lee | TTA variance with Welford's algorithm |
| 2025-12-04 | `hotfix/combine-binary-targets` | K. Lee | combine several binary targets |
| 2025-11-25 | `malis` | K. Lee | PyTorch-native MALIS loss (see [malis.md](malis.md)) |
| 2025-10 | `bf16`, `gradient_accumulation` | R. Lu | BF16 mixed precision; grad accumulation (commit notes it breaks with `size_average` and BatchNorm) |
| 2025-10-13 | `mito_to_cell` | K. Lee | mitochondria→cell assignment; `group_eps` for GroupNorm |
| 2025-08-18 | `assignment` | A. Bae | synapse assignment |
| 2025-03 | `DDP`, `multi_io_dict` | R. Lu, K. Lee | PyTorch 2.6 DDP; multi-input nets take dicts |
| 2025-01-07 | `diag_xy_aff` | K. Lee | diagonal xy affinity edges |
| 2023–2024 | `zettasets`, `myelin_augmentation`, `nucleus`, `mip3_aug`, `test-time-aug`, `metric_learning`, `fix_class_balancing`, `wandb` | various | Zettaset data loading, wandb, class balancing, metric-learning "means" loss |
| 2022 | `onnx*`, `tilt_series`, `jlichtman-zebrafish`, `wclee-fly-cns`, `pg-fly-larva-001` | various | ONNX export; per-customer project branches |

Project branch names show the customer datasets: Lichtman zebrafish, Wei-Chung Lee fly CNS,
fly larva, worm (`ariadne-worm-001`), MICrONS (`minnie`, `pinky`), V1DD.

## Layout (`feature/sr-zero-pad`, 2026-08-18)

```
deepem/
  data/classes.py           # ClassSpec registry (see below)
  data/augment/{cortex,flyem,isotropic,kasthuri11,pinky_basil,retina,super_resolution,tilt_series}/
  data/dataset/{zettaset,multi_zettaset}.py   # "zettasets": CloudVolume-backed training sets
  data/sampler/{zettaset,mito_to_cell,super_resolution}.py
  data/modifier/{crop2x,seg2bdr}.py
  loss/{affinity,loss,mean,utils}.py         # affinity BCE, metric-learning MeanLoss
  models/rsunet*.py, updown*.py              # anisotropic/isotropic RSUNet variants (emvision core)
  models/core/rsunet.py, models/v2/          # new isotropic core, trilinear upsampling
  models/{minnie_cleft,minnie_semantic,pinky_mito,tony_glia_detector,tilt_series_srnet}.py
  train/{run,option,model,data,utils,logger,wandb_logger}.py
  test/{forward,batch_run,cv_utils,mask,chkpt_to_onnx}.py
  utils/onnx_utils.py
docker/{samwise,zettasets}/Dockerfile
test_rsunet_core.py, test_decode_concat_order.py, test_target_combination.py
```

## Design points worth copying

- **Class registry.** `REGISTRY: dict[str, ClassSpec]` maps a CLI flag to an `internal_name`
  that names the output submodule, the state_dict/ONNX key, the loss, the wandb metric and the
  dataset key. Adding a head is one line (`'ribo': ClassSpec(internal_name='ribosome', binarize=True)`);
  the `--ribo` flag appears automatically. Semantic classes carry a `semantic_id` for a combined
  semantic target (dendrite 1, axon 2, soma 3, nucleus 4, glia 5, ECS 6, blood vessel 7, other 10).
- **Isotropic upsampling bug.** The README says emvision's `BilinearUp` builds its kernel from
  x/y only, so old `*_iso` models never interpolated along z. `models/v2` fixes it; old checkpoints
  load with `--pretrain` (state dict minus the `up.up.0.weight` buffers). ONNX export needs opset ≥ 11
  or `Resize` silently mismatches PyTorch. *PyTC check, 2026-11-06:* `connectomics/models/architectures/rsunet.py`
  `BilinearUp3d` builds a separable kernel on all three axes, so current PyTC is not affected.
- **Production features** on top of the 2017 recipe: DDP, BF16, EMA, focal loss, TTA with streaming
  variance, MALIS, ONNX export for inference in chunkflow/zetta_utils, wandb logging,
  remote checkpoints, preemptible-safe runs (via samwise).

## Relation to other ZettaAI repos

Data: [DataProvider3](DataProvider3.md) + [Augmentor](Augmentor.md) (both still public, with 2026 commits).
Loss: [malis](malis.md). Inference: [chunkflow](../segmentation-pipeline/chunkflow.md), then
zetta_utils (private). Agglomeration: [waterz](../segmentation-pipeline/waterz.md), [abiss](../segmentation-pipeline/abiss.md).
