# dacapo (E11 fork)

**GitHub:** https://github.com/e11bio/dacapo
**Fork of:** [funkelab/dacapo](https://github.com/funkelab/dacapo) (3★)
**Language:** Python | **Stars:** 0
**Divergence:** 24 commits ahead, 0 behind (forked 2023-10-16, last push 2024-02-14)
**Upstream docs:** https://funkelab.github.io/dacapo/

Experiment-configuration framework layered on gunpowder: an ML job is declared as a
combination of **DataSplit** × **Architecture** × **Task** × **Trainer**, run over arbitrarily
large multi-dimensional volumes. Currently torch-only.

## E11 changes (24 commits, the most-modified E11 fork)
Substantive, not cosmetic. Touched files include:
- `experiments/architectures/funlib_unet.py` + `funlib_unet_config.py` — **new architecture**
  wiring the funlib UNet in
- `experiments/tasks/affinities_task.py` / `affinities_task_config.py` /
  `predictors/affinities_predictor.py` / `post_processors/watershed_post_processor.py` —
  changes across the whole affinity task path
- `experiments/trainers/gp_augments/` — new augment configs: `blur_config.py`,
  `channel_wise_intensity_augment_config.py` (matches the multiplexed-channel augmentation in
  [prism_training](prism_training.md))
- `datasplits/datasets/arrays/intensity_array.py`, `zarr_array.py`, `experiments/model.py`

Note this fork is pinned to a **2024-02** upstream snapshot; upstream dacapo has moved on
considerably. Use the fork only to read E11's PRISM-era configuration, not as a current dacapo.

## Core abstractions
```python
# DataSplit  — train/val arrays + masks
# Architecture — backbone (e.g. UNet), declares input/output shape contract
# Task       — predictor + loss + post-processor + evaluator (e.g. AffinitiesTask)
# Trainer    — batch assembly, augments, optimizer, snapshots (GunpowderTrainer)
run_config = RunConfig(datasplit_config=..., architecture_config=...,
                       task_config=..., trainer_config=..., num_iterations=...)
```

## Relevance to PyTC
Closest external analogue to PyTC's YAML-config experiment system. The
`Task = predictor + loss + post_processor + evaluator` factoring is a cleaner separation than
PyTC's, and the E11 diff shows exactly which extension points you hit when adding a new
architecture and a new augmentation to that design.
