# zettaai-neuroglancer (Calcada proofreading)

**GitHub:** https://github.com/ZettaAI/zettaai-neuroglancer
**Language:** TypeScript | **Status (2026-11-06):** fork of seung-lab/neuroglancer, ~2,000 commits not in upstream, 283 branches; pushed 2026-11-06 (daily)

Zetta's production viewer and proofreading front end. Upstream: [../../seung-lab/visualization/](../../seung-lab/visualization/). Default branch `main`; CI deploys dev and prod from `main`. Much 2026 work is by contractors (TechMagic: Dmytro Prokopenko, Volodymyr Yushko, Yaroslav Kutsmyda) on `TM-###` tickets; older work by Chris Jordan (`cj-*`: Graphene/CAVE, multicut, find-path, spelunker).

## Calcada (`src/datasource/calcada/`, ~200 files)
A new proofreading datasource built around a **piece graph** (supervoxel pieces → roots) rather than PyChunkedGraph alone:
- **Merge-candidate review**: `candidate_ranking`, `candidate_traversal`, `candidate_heat`, `candidate_decision`, filter trees/presets/library, score-range slider, "rejected by" picker.
- **Split-error detection**: per-point split-error scores coloured green→red, threshold stepping with +/-, detection toggled with `?`.
- **Trace mode**: a 3D trace sphere cursor that walks a neurite; decisions are timed (`decision_timing`), skips and accepted merges recorded (proofreading stats PR #248, 2026-10-12).
- Annotation tables with filters, branch picker, timestamp pickers, retired roots, undo serialization, LUT/manifest retries.

## Voxel editing (`src/editing/`)
Edit sessions with locks, chunk preloading, HTTP save backend, per-voxel conflict resolution against a session baseline (TM-494), z-extrapolation (TM-518), live 3D painted-volume preview without meshing (TM-490, `docs/PAINTED_VOLUME_PREVIEW.md`), Playwright browser tests.

## Takeaways
- Proofreading is being reframed as ranked review of model-proposed merges/splits with per-decision timing, i.e. the human cost per edit is measured. That is the metric to beat for any automated proofreading work.
- Voxel painting plus conflict resolution in-browser replaces offline VAST-style edits for ground truth.
