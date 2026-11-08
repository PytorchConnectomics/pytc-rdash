# BigStitcher-Spark (E11 fork)

**GitHub:** https://github.com/e11bio/BigStitcher-Spark
**Fork of:** [JaneliaSciComp/BigStitcher-Spark](https://github.com/JaneliaSciComp/BigStitcher-Spark) (31★)
**Language:** Java | **Stars:** 0 | **License:** BSD-2-Clause
**Divergence:** 3 ahead / 3 behind on `main` (forked 2026-04-17)

Distributed (Apache Spark) implementation of the compute-heavy parts of **BigStitcher** —
tile stitching, global optimization, affine fusion, and export — for multi-view / multi-tile
light-sheet and expansion-microscopy acquisitions too large for a single JVM.

## E11 changes
One file: `src/main/java/net/preibisch/bigstitcher/spark/SparkPairwiseStitching.java`
(pairwise stitching driver). The substantive E11 patches for concurrent tile optimization live
in the sibling forks [mpicbg](mpicbg.md) and
[multiview-reconstruction](multiview-reconstruction.md), and are assembled into a container by
[prepipe-containers](../pipelines-infra/prepipe-containers.md).

## Spark entry points (upstream)
| Command | Purpose |
|---------|---------|
| `net.preibisch.bigstitcher.spark.CreateFusionContainer` | Prepare output N5/zarr container |
| `net.preibisch.bigstitcher.spark.SparkPairwiseStitching` | Pairwise shifts between tiles |
| `net.preibisch.bigstitcher.spark.SparkInterestPointDetection` | Detect interest points |
| `net.preibisch.bigstitcher.spark.SparkGeometricDescriptorMatching` | Match points across views |
| `net.preibisch.bigstitcher.spark.Solver` | Global optimization of view transforms |
| `net.preibisch.bigstitcher.spark.SparkAffineFusion` | Fuse into an N5/OME-Zarr volume |
| `net.preibisch.bigstitcher.spark.SparkNonRigidFusion` | Non-rigid fusion |
| `net.preibisch.bigstitcher.spark.SparkResaveN5` | Resave to N5/zarr with a scale pyramid |

Input/output is a BigDataViewer XML + N5/HDF5/OME-Zarr dataset.

## How E11 runs it
Not directly — via [voxelflow](../pipelines-infra/voxelflow.md) Nextflow processes
(`processes/bigstitcher.nf`), inside the
`ghcr.io/e11bio/bigstitcher-spark:latest` container, or via
[nf-BigStitcher-Spark](nf-BigStitcher-Spark.md).

## Relevance to PyTC
Relevant when the lab needs to stitch/fuse multi-tile ExM or light-sheet acquisitions before
segmentation. Note the branch list on this fork is large (`zarrv3`, `omezarr`, `blk-fusion`,
`n5universe`, …) — those are upstream development branches, not E11 work.
