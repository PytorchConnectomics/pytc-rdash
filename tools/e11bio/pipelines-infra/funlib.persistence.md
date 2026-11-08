# funlib.persistence (E11 fork)

**GitHub:** https://github.com/e11bio/funlib.persistence
**Fork of:** [funkelab/funlib.persistence](https://github.com/funkelab/funlib.persistence) (5★)
**Language:** Python | **Stars:** 0 | **License:** MIT
**Divergence:** 1 commit ahead, 128 behind (forked 2023-10-17, last push 2024-05-17)

Unified interfaces for **arrays** (zarr, N5, HDF5) and **graphs** (SQLite, PostgreSQL,
MongoDB) with world-coordinate awareness. The array abstraction that [volara](../core-libs/volara.md)
and gunpowder/dacapo build on: an `Array` carries `voxel_size`, `offset`, and a `Roi`, so you
index by physical coordinates rather than voxel indices.

## E11 change
One commit touching `funlib/persistence/arrays/datasets.py` (the `open_ds`/`prepare_ds` path).
128 commits behind upstream — **volara depends on upstream PyPI `funlib.persistence`, not this
fork.** Treat the fork as historical.

## API
```python
from funlib.persistence import open_ds, prepare_ds
from funlib.geometry import Coordinate, Roi

arr = open_ds("data.zarr/raw", mode="r")
arr.voxel_size, arr.offset, arr.roi     # physical geometry
data = arr[Roi((0, 0, 0), (100, 200, 200))]   # index in world coordinates

out = prepare_ds("data.zarr/out", shape=(3, 100, 100, 100),
                 chunk_shape=(3, 50, 50, 50), offset=(0, 0, 0),
                 voxel_size=(40, 8, 8), dtype="uint8")

from funlib.persistence.graphs import SQLiteGraphDataBase, PgSQLGraphDatabase
```

## Relevance to PyTC
The world-coordinate `Array`/`Roi` convention is worth borrowing: it removes a whole class of
off-by-voxel-size bugs when chaining operations at different MIP levels. Install upstream
(`pip install funlib.persistence`), not this fork.
