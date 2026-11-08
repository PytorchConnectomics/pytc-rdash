# gunpowder (E11 fork)

**GitHub:** https://github.com/e11bio/gunpowder
**Fork of:** [funkelab/gunpowder](https://github.com/funkelab/gunpowder) (92★)
**Language:** Python | **Stars:** 0 | **License:** MIT
**Divergence:** 3 commits ahead, 0 behind (forked 2026-07-18)
**Upstream docs:** https://funkelab.github.io/gunpowder/

Library for assembling ML pipelines over large multi-dimensional images: data loading →
pre-processing → random batch sampling → augmentation → pre-caching → training/prediction →
output. Framework-agnostic (complements torch/tensorflow rather than replacing them).
Originally by Jan Funke.

## E11 changes
Touches only `gunpowder/nodes/random_location.py` (+ `nodes/__init__.py` export and its test) —
i.e. a modification to how random batch locations are drawn. Nothing else diverges from
upstream, so **read upstream docs and treat this fork as upstream + a RandomLocation tweak**.

## Key upstream concepts
- `BatchRequest` / `BatchProvider` / `BatchFilter` — pipeline nodes composed with `+`
- Source nodes: `ZarrSource`, `Hdf5Source`, `CsvPointsSource`, `GraphSource`
- Augmentation: `ElasticAugment`, `SimpleAugment`, `IntensityAugment`, `NoiseAugment`,
  `DefectAugment`
- Targets: `AddAffinities`, `GrowBoundary`, `BalanceLabels`, `RasterizeGraph`
- `RandomLocation`, `Reject`, `PreCache`, `Train`, `Predict`, `ZarrWrite`, `Scan`

```python
pipeline = (
    ZarrSource("data.zarr", {raw: "raw", labels: "labels"})
    + RandomLocation()
    + SimpleAugment() + ElasticAugment(...) + IntensityAugment(...)
    + AddAffinities(affinity_neighborhood=nbhd, labels=labels, affinities=gt_affs)
    + PreCache(num_workers=10)
    + Train(model, loss, optimizer, inputs=..., outputs=..., loss_inputs=...)
)
with build(pipeline):
    for i in range(iterations):
        pipeline.request_batch(request)
```

## Relevance to PyTC
The dominant alternative to PyTC's own dataset/augmentor stack in the Funke-lab ecosystem.
Read it when comparing augmentation semantics (especially `ElasticAugment` and
`AddAffinities`) or when running [prism_training](prism_training.md), which is built on it.
E11's custom nodes live in `prism_training/train/nodes.py`, not in this fork.
