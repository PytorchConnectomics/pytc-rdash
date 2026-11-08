# multiview-reconstruction (E11 fork)

**GitHub:** https://github.com/e11bio/multiview-reconstruction
**Fork of:** [JaneliaSciComp/multiview-reconstruction](https://github.com/JaneliaSciComp/multiview-reconstruction) (34★)
**Language:** Java | **Stars:** 0 | **License:** GPL-2.0
**Divergence:** `master` is 0 ahead / 374 behind — **the E11 work is on the `prepipe` branch**
(1 commit ahead of upstream master)

Reconstruction engine behind BigStitcher / SPIM processing: interest-point detection and
matching, view registration, global optimization, non-rigid and affine fusion, deconvolution,
for multi-view microscopy (SPIM, light sheet, expansion).

## E11 change — branch `prepipe`
Single commit: **"Re-enable concurrent tile optimization in GlobalOptIterative"**
- `src/main/java/net/preibisch/mvrecon/process/interestpointregistration/global/GlobalOptIterative.java`
- `pom.xml`

Pairs with [mpicbg@prepipe](mpicbg.md): once `TileUtil.optimizeConcurrently()` no longer
crashes on disconnected tiles, `GlobalOptIterative` can use the concurrent solver again
instead of the serial fallback. Together these are the two patches
[prepipe-containers](../pipelines-infra/prepipe-containers.md) bakes into
`ghcr.io/e11bio/bigstitcher-spark:latest`.

The fork's `master` is a stale 2026-04 snapshot (374 commits behind); the many other branches
are upstream development branches, not E11's.

## Relevance to PyTC
Same as [mpicbg](mpicbg.md) — reference only, unless the lab runs BigStitcher global
optimization on large tile sets and needs the concurrent solver.
