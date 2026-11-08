# prepipe-containers

**GitHub:** https://github.com/e11bio/prepipe-containers
**Language:** Dockerfile | **Stars:** 0 | **License:** BSD-3-Clause

Container images for E11's **prepipe** preprocessing pipeline. Three files total — one
Dockerfile — but it is the assembly point that documents which patched forks E11 actually runs.

## Image: `ghcr.io/e11bio/bigstitcher-spark:latest`
BigStitcher-Spark **with concurrent tile optimization enabled**. Based on
[JaneliaSciComp/BigStitcher-Spark](https://github.com/JaneliaSciComp/BigStitcher-Spark) plus:

| Patch | Fix |
|-------|-----|
| [e11bio/mpicbg@prepipe](../stitching-registration/mpicbg.md) | `TileUtil.optimizeConcurrently()` crash on disconnected tiles |
| [e11bio/multiview-reconstruction@prepipe](../stitching-registration/multiview-reconstruction.md) | Re-enable the concurrent solver in `GlobalOptIterative` |

Built automatically on push to `main` via GitHub Actions.

## Usage
```bash
docker pull ghcr.io/e11bio/bigstitcher-spark:latest
```
```groovy
// Nextflow (apptainer)
apptainer.runOptions = ''   // no bind mount needed
process {
    withName: BIGSTITCHER_MODULE {
        container = 'ghcr.io/e11bio/bigstitcher-spark:latest'
    }
}
```

## Relevance to PyTC
Read this first when tracing what "the E11 stitching stack" actually is — the two `prepipe`
branch patches are invisible from either fork's default branch. Also a compact template for
publishing a patched-JVM-tool container to GHCR and consuming it from Nextflow.
