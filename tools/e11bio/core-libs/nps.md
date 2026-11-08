# nps

**GitHub:** https://github.com/e11bio/nps
**Language:** Python | **Stars:** 2
**PyPI:** `pip install nps-cli`

Single-purpose CLI for distributed point-cloud sampling from segmentation volumes. Walks a
CloudVolume-backed segmentation blockwise and writes a fraction of each label's voxel
coordinates out as a queryable point cloud. Built on [volara](volara.md)'s blockwise machinery.

## Key Features
- Reads any CloudVolume path: `precomputed://gs://…`, `precomputed://s3://…`, graphene
- Graphene extras: `--timestamp` for a dataset version, `--sample_svids` to also emit supervoxel IDs
- Blockwise + parallel: `LocalWorker` / `SlurmWorker` / `LSFWorker`
- `--fraction` subsamples voxels per label (default 0.001) — keeps output tractable on petascale
- `--bbox` restricts to a subvolume; `--fill-missing` tolerates missing chunks
- Output is read back with [pocaduck](https://github.com/JaneliaSciComp/pocaduck)

## CLI
```bash
nps --cv-path precomputed://gs://neuroglancer-janelia-flyem-hemibrain/v1.0/segmentation \
    --bbox 15347 19712 18606 15859 20224 19118 \
    --fraction 0.01 \
    --block-size 128 128 128 \
    --worker-type SlurmWorker --num-workers 8 --cpus-per-worker 4 \
    -o ./nps_output
```

Full option set: `--cv-path` (required), `--mip`, `--timestamp`, `--sample_svids`,
`--fill-missing`, `-o/--output-dir`, `--worker-type`, `--num-workers`, `--cpus-per-worker`,
`--queue`, `--fraction`, `--bbox`, `--block-size`.

## Reading the output
```python
from pocaduck import Query

query = Query(storage_config="./nps_output")
labels = query.get_labels()
points = query.get_points(label=12345)   # (N, 3) coords, aggregated across blocks
query.close()
```

## Internals
`nps/main.py` wraps the segmentation in `volara.datasets.CloudVolumeWrapper` and runs a
`SamplePoints` blockwise task (`nps/blockwise/sample_points.py`). ~200 lines total — a good
minimal example of writing a third-party volara task.

## Relevance to PyTC
Useful when a downstream method wants point clouds rather than dense labels (skeleton
seeding, point-transformer models, shape descriptors, mesh sampling) and the segmentation is
too large to load. Also the shortest readable example of the volara plugin pattern.
