# volara

**GitHub:** https://github.com/e11bio/volara
**Language:** Python | **Stars:** 45 | **License:** MIT
**PyPI:** `pip install volara` | **Docs:** https://e11bio.github.io/volara/

Declarative framework for block-wise operations on arbitrarily large nD volumes. Wraps
[Daisy](https://github.com/funkelab/daisy) with pydantic-typed task objects so a segmentation
pipeline is written as `task_a + task_b + task_c` instead of hand-rolled scheduler glue.
This is E11's answer to the same problem `igneous` solves for seung-lab — but centered on
zarr/OME-zarr + mutex watershed rather than Neuroglancer Precomputed.

## Key Features
- Next-gen file formats: zarr, OME-zarr, N5 (via `funlib.persistence`); S3 stores supported
- Lazy dataset ops (threshold, normalize, slice, dtype cast, channel selection) applied on read
- Graph backends behind one interface: SQLite (single-machine) or PostgreSQL (cluster)
- Compute contexts: serial / multiprocess / SLURM / LSF, CPU or GPU, via `Worker` subclasses
- Per-block completion tracking in a side zarr → **tasks resume** after a crash without redoing work
- Task chaining with `+` (builds a `pipeline`), each task's outputs feeding the next
- Plugin system for custom tasks (subclass `BlockwiseTask`); `volara-ml` is the reference plugin

## Blockwise Tasks (`volara.blockwise`)

| Task | What it does |
|------|--------------|
| `ExtractFrags` | Fragment (supervoxel) extraction via mutex watershed ([mwatershed](https://github.com/pattonw/mwatershed)) |
| `SeededExtractFrags` | Same, constrained by skeletonized seed points |
| `AffAgglom` | Writes supervoxel-pair affinity scores as graph edges |
| `DistanceAgglom` | Same, but edge weight = distance between stored supervoxel embeddings |
| `GraphMWS` | Global fragment→segment LUT via mutex watershed on the region graph |
| `Relabel` | Applies the LUT, writing fragments out as segments |
| `Argmax` | Argmax across predicted probability channels |
| `Threshold` | Intensity threshold an array |
| `ComputeShift` | Phase cross-correlation shift between moving and fixed image |
| `ApplyShift` | Apply the computed shift (rigid registration) |
| `LambdaTask` | Wrap an arbitrary callable as a blockwise task |

## Core Types

```python
# volara.datasets — pydantic Dataset wrappers over zarr/OME-zarr/CloudVolume
Dataset(store, voxel_size, offset, axis_names, units, channels, writable, zarr_kwargs)
Raw(...)                      # + ome_norm, scale_shift, stack
Affs(..., neighborhood=[Coordinate(...), ...])   # affinity array + its offset neighborhood
LSD(...)                      # local shape descriptors
Labels(...)                   # segmentation / fragments
CloudVolumeWrapper(..., mip, timestamp, agglomerate, fill_missing)  # read Precomputed/graphene

# volara.dbs — region-adjacency graph storage
SQLite(path, node_attrs=..., edge_attrs={"adj_weight": "float", "lr_weight": "float"})
PostgreSQL(host, name, user, password, node_attrs=..., edge_attrs=...)

# volara.lut — fragment→segment lookup tables
LUT(path)                     # .save(lut, edges) / .load(); LUTs composable with `+`

# volara.workers — where blocks execute
LocalWorker()
SlurmWorker(queue, num_cpus, num_gpus)
LSFWorker(queue, num_cpus, num_gpus)
```

## Example Pipeline (affinities → segmentation)
```python
from funlib.geometry import Coordinate
from funlib.persistence import open_ds
from pathlib import Path
from volara.blockwise import ExtractFrags, AffAgglom, GraphMWS, Relabel
from volara.datasets import Affs, Labels
from volara.dbs import SQLite
from volara.lut import LUT

file = Path("test.zarr")
block_size, context = Coordinate(15, 40, 40) * 3, Coordinate(15, 40, 40)
bias = [-0.4, -0.7]  # (adjacent, long-range) mutex watershed biases

affs = Affs(store=file / "affinities", neighborhood=[
    Coordinate(1,0,0), Coordinate(0,1,0), Coordinate(0,0,1),      # adjacent
    Coordinate(4,0,0), Coordinate(0,8,0), Coordinate(0,0,8),      # long-range
    Coordinate(8,0,0), Coordinate(0,16,0), Coordinate(0,0,16),
])
db = SQLite(path=file / "db.sqlite",
            edge_attrs={"adj_weight": "float", "lr_weight": "float"})
fragments = Labels(store=file / "fragments")
lut = LUT(path=file / "lut.npz")
roi = open_ds(file / "affinities").roi

pipeline = (
    ExtractFrags(db=db, affs_data=affs, frags_data=fragments,
                 block_size=block_size, context=context,
                 bias=[bias[0]]*3 + [bias[1]]*6, num_workers=10)
    + AffAgglom(db=db, affs_data=affs, frags_data=fragments,
                block_size=block_size, context=context,
                scores={"adj_weight": affs.neighborhood[0:3],
                        "lr_weight":  affs.neighborhood[3:]}, num_workers=10)
    + GraphMWS(db=db, lut=lut,
               weights={"adj_weight": (1.0, bias[0]), "lr_weight": (1.0, bias[1])},
               roi=[roi.get_begin(), roi.get_shape()])
    + Relabel(frags_data=fragments, seg_data=Labels(store=file / "segments"),
              lut=lut, block_size=block_size, num_workers=5)
)
pipeline.run_blockwise()
```

## Custom Task
Subclass `BlockwiseTask`, declare `task_type` / `fit` / `read_write_conflict`, implement
`write_roi`, `write_size`, `context_size`, `init()`, `drop_artifacts()`, and a
`@contextmanager process_block_func()` that yields `process_block(block)`. The yielded closure
gets a `daisy.Block` with `.read_roi` / `.write_roi`.

```python
class Argmax(BlockwiseTask):
    task_type: str = "argmax"
    fit: str = "shrink"
    read_write_conflict: bool = False

    @contextmanager
    def process_block_func(self):
        in_array  = open_ds(..., mode="r+")
        out_array = open_ds(..., mode="r+")
        def process_block(block):
            out_array[block.write_roi] = in_array[block.read_roi].argmax(axis=0)
        yield process_block
```

## CLI
```bash
volara --log-level INFO blockwise-worker --config-file <task.yaml>
```
(The CLI is mainly the worker entrypoint that `SlurmWorker`/`LSFWorker` submit; pipelines are
driven from Python.)

## Relevance to PyTC
Closest external analogue to a PyTC inference + post-processing driver. Worth reading before
writing new blockwise machinery for large-volume inference: the `Dataset`/`DB`/`Worker`/`LUT`
separation, the resume-via-done-zarr trick, and `+` chaining are all directly transferable.
The affinity → mutex-watershed → region-graph → LUT → relabel path is the same shape as PyTC's
`waterz`/`zwatershed` post-processing, but blockwise and resumable by construction.
Used in production by [prism_training](../deep-learning/prism_training.md).

Related: [volara-ml](volara-ml.md) (torch/jax inference plugin), [nps](nps.md),
[funlib.persistence](../pipelines-infra/funlib.persistence.md).
