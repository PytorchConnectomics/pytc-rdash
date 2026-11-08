# nf-BigStitcher-Spark (E11 fork)

**GitHub:** https://github.com/e11bio/nf-BigStitcher-Spark
**Fork of:** [JaneliaSciComp/nf-BigStitcher-Spark](https://github.com/JaneliaSciComp/nf-BigStitcher-Spark) (2★)
**Stars:** 0 | **License:** BSD-3-Clause
**Divergence:** 0 ahead / 0 behind — clean mirror as of 2026-04-21

Nextflow wrapper that runs [BigStitcher-Spark](BigStitcher-Spark.md) as a workflow: spins up an
on-demand Spark cluster (local, SLURM, or LSF), chains the stitching stages, and handles
container execution. Removes the need to hand-write `spark-submit` invocations.

**No E11 modifications** — forked for pinning/vendoring, not for changes.

## Typical stages
`resave → interest points → geometric descriptor matching → solver → affine fusion → export`,
each a Nextflow process submitting a Spark job against the BigDataViewer XML + N5/zarr dataset.

## Relationship to voxelflow
[voxelflow](../pipelines-infra/voxelflow.md) is E11's own Nextflow stitching workflow and
predates this fork (2023 vs 2026). `nf-BigStitcher-Spark` was forked later — treat it as the
upstream reference implementation E11 was evaluating against, and check which one a given
E11 pipeline actually calls before assuming.

## Relevance to PyTC
Reference for how to drive Spark-based stitching from Nextflow on a SLURM cluster — the
closest ready-made pattern if the lab needs distributed stitching on `g02`/BC without
building the orchestration itself.
