# e11-open-data

**GitHub:** https://github.com/e11bio/e11-open-data
**Language:** Jupyter Notebook | **Stars:** 8 | **License:** CC BY-SA 4.0
**Bucket:** `s3://e11bio-prism/ls` (AWS Open Data, anonymous access)

Index + tutorials for the public **PRISM** hippocampal dataset accompanying *"Combinatorial
protein barcodes enable self-correcting neuron tracing with nanoscale molecular context."*
This is the dataset behind [prism_training](../deep-learning/prism_training.md).

## Dataset at a glance
- Mouse hippocampal **CA3**, AAV-transduced with a library of "protein bit" epitope-tag barcodes
- Modified expansion microscopy, ~5× physical expansion → **effective voxel size ~35 × 35 × 80 nm**
- Iterative immunostaining: multiple stain/image/strip cycles on the same expanded tissue
- **~10 million µm³** total volume, **23 distinct molecular channels**
- Ships imaging data, automated segmentations, and human proofreading annotations

## Zarr layout — `s3://e11bio-prism/ls/images/full_dataset.zarr`

| Group | Scales | Type | dtype | Notes |
|-------|--------|------|-------|-------|
| `all` | 0–5 | image | uint8 | 40 channels, all barcodes + markers, unnormalized |
| `raw` | s0–s5 | image | uint8 | 18 channels, min/max normalized |
| `markers` | s0–s5 | image | uint16 | 7 channels, unnormalized |
| `barcode_mask` | s0–s5 | image | uint8 | |
| `dense_segmentation` | s0–s5 | seg | uint64 | |
| `local_segmentation` | s0–s5 | seg | uint64 | ~1500 skeleton-seeded segments |
| `local_segmentation_spines` | s0–s5 | seg | uint64 | 10 skeletons traced to spines |
| `proofread_segmentation` | — | seg | uint64 | |
| `barcode_relabeled_segmentation` | — | seg | uint64 | |

Also: `…/full_dataset.zarr/skeletons/` — manually annotated axon/dendrite skeletons (the seeds
for the `local_segmentation` volumes), and
`…/models/training_data/{instance,semantic}/crop_N.zarr` — the training crops
`prism_training/data/download_data.py` pulls.

## Neuroglancer Precomputed mirror — `…/full_dataset.zarr/precomputed/`
`raw` · `enhanced` · `markers_all` · `combined_affs` · `dense_seg` · `local_seg_full` ·
`local_seg_spines` · `pre_mask_dense_seg` · `post_mask_dense_seg` ·
`pre_mask_local_seg_spines` · `post_mask_local_seg_spines` · `proofed_cells` ·
`segments_skeleton_barcode_relabeled`

## Access
```python
import s3fs, zarr
fs = s3fs.S3FileSystem(anon=True)
store = s3fs.S3Map("e11bio-prism/ls/models/training_data/instance/crop_0.zarr/raw", s3=fs)
arr = zarr.open(store, mode="r")
print(arr.shape)
```
```bash
aws s3 ls s3://e11bio-prism/ls/images --no-sign-request
aws s3 cp s3://e11bio-prism/ls/images/full_dataset.zarr/markers/s5/ . \
    --recursive --no-sign-request
```

Tutorials: `tutorials/Browsing_and_downloading_data.ipynb`,
`tutorials/Open_and_view_zarr_array.ipynb`.

## Relevance to PyTC
A rare public, densely-proofread **multiplexed light-microscopy** connectomics volume with
matched skeletons and synapse masks — a natural benchmark for the lab's multi-object
foundation-model work alongside EM datasets, and a ready-made test case for channel-agnostic
architectures (40 channels, variable subsets). Free anonymous S3 access means it needs no
data agreement.
