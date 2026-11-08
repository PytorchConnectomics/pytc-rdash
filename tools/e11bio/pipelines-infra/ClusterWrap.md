# ClusterWrap (E11 fork)

**GitHub:** https://github.com/e11bio/ClusterWrap
**Fork of:** [JaneliaSciComp/ClusterWrap](https://github.com/JaneliaSciComp/ClusterWrap) (3★)
**Stars:** 0 | **License:** MIT
**Divergence:** none — snapshot fork, created and last pushed 2024-10-01

Wrappers around `dask-jobqueue` cluster objects for specific on-site clusters. Auto-detects the
environment: if `bsub` is on PATH it builds a `janelia_lsf_cluster`, otherwise a
`LocalCluster`. Clusters are context managers, so workers shut down cleanly on exception, and
LSF clusters autoscale between a min and max worker count based on submitted work.

**No E11 modifications** — forked as a pinned dependency of
[streamline](../stitching-registration/streamline.md).

## Usage
```python
from ClusterWrap.decorator import cluster

@cluster
def your_distributed_function(..., cluster=None, cluster_kwargs={}):
    """dask code — gets a live cluster either way"""
```
Any `@cluster`-decorated function must accept `cluster` and `cluster_kwargs`. If `cluster` is
`None`, one is created from `cluster_kwargs` and torn down afterwards; if a cluster is passed
in, it is reused.

```python
import ClusterWrap
with ClusterWrap.cluster() as cluster:
    ...   # dask code
```

## Relevance to PyTC
The `@cluster` decorator pattern — a function that works identically on a laptop and on a
scheduler, with the cluster as an optional injected argument — is directly worth copying for
lab code that must run both on a workstation and on `g02`/BC SLURM. Note this repo has no
SLURM cluster implementation; you would add one (`dask_jobqueue.SLURMCluster`) to use it here.
