# Augmentor (ZettaAI fork)

**GitHub:** https://github.com/ZettaAI/Augmentor
**Language:** Python | **Status (2026-11-06):** fork of seung-lab/Augmentor, 14 commits ahead on master, 12 feature branches; last push 2026-10-22

3D EM augmentation library used by [DeepEM](DeepEM.md). Upstream: [../../seung-lab/deep-learning/Augmentor.md](../../seung-lab/deep-learning/Augmentor.md).

## ZettaAI-only additions (Kisuk Lee unless noted)
| Date | Branch / commit | Augmentation |
|---|---|---|
| 2023-07 | master | dynamic border creation; border/label augment with selectable targets |
| 2024-02 | `myelin-aug` | myelin augmentation |
| 2024-05 | master | **section gap** augmentation |
| 2024-12 | `superresolution` (Ran Lu) | super-resolution experiment augs |
| 2026-01 | master (PR #4) | **ContrastCompression** (low SNR/contrast), **image degradation pipeline** |
| 2026-02 | `nkem/simplex-noise-warp` (Nico Kemnitz) | warp with 2D simplex-noise fields |
| 2026-02/03 | `feature/sr-subsample` | `SubsampleZ`, `CubicSubsampleZ` for z-super-resolution training |
| 2026-10-06 | master (PR #6) | fix: `FlipRotateIsotropic` now draws **uniformly from the 48 cube symmetries** |
| 2026-10-09 | `test/characterization` | characterization tests pinning **the 23 augmentations DeepEM uses** at fixed seeds |
| 2026-10-22 | `feature/fibsem-noise` | `FIBSEMNoise`, named degradation levels, inverted Poisson noise |
| 2022 | `tilt_series`, `mixed_resolution` | tilt-series simulation; mixed-resolution crops |

## Takeaways
- The flip fix implies the earlier isotropic flip/rotate was not uniform over the octahedral group; worth checking any port (PyTC/MONAI) for the same bias.
- FIB-SEM noise and contrast compression target the low-SNR datasets (FIB-SEM, fast SEM) Zetta now serves.
- Pinning augmentations with seeded characterization tests before refactoring is a cheap guard against silent training-distribution drift.
