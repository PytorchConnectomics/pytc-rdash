# abiss / labiss (ZettaAI forks)

**GitHub:** https://github.com/ZettaAI/abiss
**Language:** C++ | **Status (2026-11-06):** forks of seung-lab/abiss; work on branches; last push 2026-07-22

Affinity-based image segmentation system (chunked watershed + mean-affinity agglomeration used for MICrONS/FlyWire). Upstream: [../../seung-lab/segmentation-pipeline/abiss.md](../../seung-lab/segmentation-pipeline/abiss.md).
`labiss` is a second fork ("long-range affinity based"), with no extra commits on its default branch.

## ZettaAI branches
- `tri/python` (2024-04, merged 2026-01): **Python wrapper for `watershed()`**, C++17, GIL released during the call (Nico Kemnitz).
- `dodam/agg_python_wrapper` (2026-03): Python agglomeration interface with a Fibonacci heap.
- `akhilesh/watershed-mem` (2026-07): one global region-graph map, `uint32` segment ids — memory reduction.

## Takeaway
abiss is becoming an in-process Python library rather than a set of CLI binaries driven by seuron; together with waterz this is Zetta's 2026 push on fast agglomeration.
