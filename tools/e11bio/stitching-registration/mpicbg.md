# mpicbg (E11 fork)

**GitHub:** https://github.com/e11bio/mpicbg
**Fork of:** [axtimwalde/mpicbg](https://github.com/axtimwalde/mpicbg) (72★)
**Language:** Java | **Stars:** 0 | **License:** GPL-2.0
**Divergence:** `master` is 0 ahead / 1 behind — **the E11 work is on the `prepipe` branch**
(1 commit ahead of upstream master)

Fiji/ImageJ library of image transformation and feature-based registration primitives
(models, tiles, point matches, SIFT/block matching, global optimization). Underpins
BigStitcher / multiview-reconstruction / TrakEM2.

## E11 change — branch `prepipe`
Single commit: **"Fix optimizeConcurrently crash on disconnected tiles"**
- `mpicbg/src/main/java/mpicbg/models/TileUtil.java` — the fix
- `mpicbg/src/test/java/mpicbg/models/TileUtilConcurrentTest.java` — regression test
- `mpicbg/pom.xml` — version bump

`TileUtil.optimizeConcurrently()` is the parallel global-optimization solver used by
BigStitcher. Upstream it crashes when the tile graph has disconnected components — which
happens routinely on sparse/patchy acquisitions. E11 patched it so concurrent optimization can
stay enabled instead of falling back to the serial solver.

Other branches (`blockpmcc`, `fiji`, `spring-mesh2`, `spring-mesh3`) are upstream branches.

## Consumed by
[prepipe-containers](../pipelines-infra/prepipe-containers.md) builds
`ghcr.io/e11bio/bigstitcher-spark:latest` from this branch plus
[multiview-reconstruction@prepipe](multiview-reconstruction.md).

## Relevance to PyTC
Only relevant if the lab hits the same disconnected-tile crash while running BigStitcher's
concurrent solver on sparse acquisitions. Worth knowing the fix exists and where it lives
before debugging global optimization from scratch.
