# MALIS - Maximin Affinity Learning of Image Segmentation

**Location:** `lib/malis/` (inside pytorch_connectomics repo)
**Origin:** Python wrapper for the MALIS C++ implementation by Srinivas Turaga (Janelia / TuragaLab); upstream at https://github.com/TuragaLab/malis
**License:** MIT
**Language:** Python + Cython + C++11 (Boost `disjoint_sets`)
**Dependencies:** Cython>=0.24, numpy>=1.9, scipy, h5py (tests)

## Purpose

MALIS is a **structured loss function** for supervised learning of affinity-graph-based image segmentation. It computes per-edge loss weights from the maximum spanning tree (MST) of predicted affinities, charging mistakes by the number of voxel pairs they wrongly merge or split. Used to train CNNs that predict affinity graphs for connectomics EM segmentation.

Reference: SC Turaga, KL Briggman, M Helmstaedter, W Denk, HS Seung (2009). *Maximin learning of image segmentation*. NIPS 2009.

## Installation

```bash
# from PyPI
pip install malis

# build from source (this repo)
cd lib/malis && ./make.sh        # runs: python setup.py build_ext --inplace
# or
pip install -e lib/malis
```

Produces `malis/malis.so` extension module.

## Package Structure

```
lib/malis/
├── make.sh                     # ./make.sh -> python setup.py build_ext --inplace
├── setup.py                    # Top-level setuptools (Cython extension build)
├── MANIFEST.in
├── requirements.txt
├── README.md
├── LICENSE                     # MIT
└── malis/
    ├── __init__.py             # Re-exports malis.* + malis_weights_op / malis_loss_op
    ├── malis_cpp.h             # C++ headers: 3 functions
    ├── malis_cpp.cpp           # C++ implementations (Boost disjoint_sets)
    ├── malis.pyx               # Cython bindings + pure-Python helpers
    ├── malis_loss.py           # TensorFlow op wrappers (MalisWeights, malis_weights_op, malis_loss_op)
    ├── test_malis.py           # Python-2 style smoke test (uses Janelia data path)
    └── setup.py                # Inner Cython-only setup (used by make.sh path)
```

## C++ Core (`malis_cpp.cpp`)

Three header-exposed functions, all operate on a flat edge-list `(node1, node2, edgeWeight)`:

| Function | Purpose |
|---|---|
| `malis_loss_weights_cpp` | MALIS Kruskal's MST pass. For each MST edge, counts pairs of voxels merged that share (pos) or differ in (neg) GT label. Returns `nPairPerEdge`. |
| `connected_components_cpp` | Standard union-find connected components on a thresholded edge graph (int edge weights, 0 = cut). |
| `marker_watershed_cpp` | Marker-controlled watershed via MST: extends each marker label to its basin by descending edge weights. |

The MALIS pass:
1. Each voxel starts as its own disjoint set, carrying the GT label as a count `{label: 1}` in an overlap map.
2. Edges are sorted in **decreasing** weight order (maximum spanning tree, Kruskal's).
3. For each edge that joins two distinct components, count merged pairs `it1->second * it2->second`:
   - `pos=1`: count pairs **with same** GT label (mistakenly split affinities that should be high)
   - `pos=0`: count pairs **with different** GT labels (mistakenly merged affinities that should be low)
4. Accumulate counts into `nPairPerEdge`, then merge overlap maps into the surviving root.

## Cython Layer (`malis.pyx`)

### Core ops (thin C++ wrappers)

| Function | Signature | Notes |
|---|---|---|
| `malis_loss_weights(segTrue, node1, node2, edgeWeight, pos)` | uint64 seg + edge list + float32 weights | Returns uint64 `nPairPerEdge` |
| `connected_components(nVert, node1, node2, edgeWeight, sizeThreshold=1)` | int32 edge weights (0 = cut) | Returns `(seg, segSizes)` renumbered descending by size |
| `marker_watershed(marker, node1, node2, edgeWeight, sizeThreshold=1)` | uint64 markers + float32 weights | Returns `(seg, segSizes)` |

### Pure-Python helpers (also in `malis.pyx`)

| Function | Purpose |
|---|---|
| `prune_and_renum(seg, sizeThreshold=1)` | Renumber labels descending by component size; drop components <= threshold |
| `bmap_to_affgraph(bmap, nhood, return_min_idx=False)` | Convert a boundary map to an affinity graph along a neighborhood; `aff` shape = `(nEdge, Z, Y, X)`, int32 |
| `seg_to_affgraph(seg, nhood)` | Convert a segmentation to an affinity graph: edge=1 iff both endpoints share a positive label |
| `nodelist_like(shape, nhood)` | Build `(node1, node2)` linear-index arrays matching a `(nEdge, Z, Y, X)` affinity graph |
| `affgraph_to_edgelist(aff, nhood)` | Flatten an affinity graph to `(node1, node2, edge)` |
| `connected_components_affgraph(aff, nhood)` | CC on an affinity graph; returns `(seg[Z,Y,X], segSizes)` |
| `mk_cont_table(seg1, seg2)` | Co-occurrence matrix (scipy.sparse-based) |
| `compute_V_rand_N2(segTrue, segEst)` | Rand-score-like metric: returns `(V_rand, V_rand_split, V_rand_merge)`; ignores GT label 0 |
| `rand_index(segTrue, segEst)` | Classic Rand index + fscore/precision/recall |
| `mknhood2d(radius=1)` | 2D neighborhood offsets within a disk of `radius` |
| `mknhood3d(radius=1)` | 3D neighborhood offsets within a sphere (e.g. `radius=1` gives 6-connectivity) |
| `mknhood3d_aniso(radiusxy=1, radiusxy_zminus1=1.8)` | Anisotropic 3D neighborhood: in-plane + previous-z disk |

### Neighborhood (`nhood`) convention

`nhood` is `(nEdge, 3)` int32 offset vectors. For an affinity graph `aff[e, z, y, x]`, the edge connects voxel `[z,y,x]` to voxel `[z,y,x] + nhood[e, :]`. The first index of `nhood[e]` is **z**, then **y**, then **x**.

## TensorFlow Loss Wrappers (`malis_loss.py`)

> WARNING: **TF1-era code.** Uses `tf.py_func` and would need porting (or a PyTorch equivalent) for use with current PyTC.

### `MalisWeights` (NumPy class)

Precomputes the `edge_list` once per output shape + neighborhood, then on each call runs **two MALIS passes**:

- **Negative pass** (`pos=0`): clamp affinities to 1 wherever GT affinity is 0 (force-merge GT splits), then count edge pairs that wrongly merge across GT boundaries.
- **Positive pass** (`pos=1`): clamp affinities to 0 wherever GT affinity is 1 (force-split GT merges), then count edge pairs that wrongly split within a GT object.

Per-edge weights from each pass are normalized to sum to 1, and the two passes are summed. Supports:
- `gt_aff_mask`: binary mask for edges with known GT affinities (others ignored).
- `gt_seg_unlabelled`: binary mask marking partially-unlabelled GT objects; unlabelled regions get a unique synthetic ID before the pass.

### `malis_weights_op(affs, gt_affs, gt_seg, neighborhood, gt_aff_mask=None, gt_seg_unlabelled=None, name=None)`

TF op (via `tf.py_func`) returning per-edge MALIS weights with the same shape as `affs`.

### `malis_loss_op(affs, gt_affs, gt_seg, neighborhood, gt_aff_mask=None, gt_seg_unlabelled=None, name=None)`

Returns `sum(weights * (gt_affs - affs)^2)` -- constrained MALIS loss with squared-distance base loss.

## Key Data Types

| Concept | dtype | shape | Notes |
|---|---|---|---|
| GT segmentation | `uint64` | `[Z, Y, X]` flattened to `[nVert]` | Label 0 = background; ignored in pos pass |
| Edge list | `uint64` x 2 | `[nEdge]` each | `node1[i], node2[i]` give the two endpoints |
| Predicted affinities | `float32` | `[nEdge]` | Range typically [0, 1] |
| Per-edge pair counts | `uint64` | `[nEdge]` | Output of `malis_loss_weights` |
| Neighborhood | `int32` | `[nEdge_per_voxel, 3]` | (dz, dy, dx) offsets |

## Pipeline

For an affinity-graph training loop:

1. Compute `nhood = mknhood3d(1)` (or `mknhood3d_aniso(...)` for EM volumes).
2. Generate `gt_affs = seg_to_affgraph(gt_seg, nhood)`.
3. Predict `affs` from a CNN (same shape as `gt_affs`).
4. Build `(node1, node2) = nodelist_like(gt_seg.shape, nhood)` once.
5. Call `malis_loss_weights(gt_seg.ravel(), node1.ravel(), node2.ravel(), affs.ravel(), pos)` for `pos in {0, 1}`.
6. Combine the two passes (normalize + sum, as in `MalisWeights.get_edge_weights`).
7. Multiply edge-wise weights against a per-edge base loss (e.g. MSE between `affs` and `gt_affs`) and sum.

## Usage in PyTorch Connectomics

**Not currently wired into PyTC.** A grep of `connectomics/` returns no real malis references (only false-positive substring matches in `formalised`/`normalisation`). To use MALIS as a PyTC loss, you would need:

- A PyTorch wrapper (the included `malis_loss.py` is TF1).
- Registration via `connectomics/models/losses/build.py` `create_loss()` and metadata in `losses/metadata.py`.
- An affinity-graph target generator (consumes `seg`, emits `gt_affs` per a fixed `nhood`).

## Notes / Gotchas

- `test_malis.py` is **Python 2 syntax** (`print ...` statements) and references a non-portable Janelia data path; treat as historical, not a runnable test.
- C++ uses Boost `boost::pending::disjoint_sets` -- make sure Boost headers are available at build time.
- All node IDs are `uint64`; the comment `node1[i] >= 0` in `malis_cpp.cpp` is a dead check on unsigned values.
- Edge weights for `connected_components_cpp` are `int*` (0 = cut), distinct from the `float*` weights used in the MST pass.
- `mknhood3d_aniso` returns a neighborhood with the in-plane offsets first and the previous-z disk appended with both signs -- see code for exact layout.
