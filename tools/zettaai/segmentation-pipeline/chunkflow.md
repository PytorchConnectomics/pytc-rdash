# chunkflow (ZettaAI fork)

**GitHub:** https://github.com/ZettaAI/chunkflow
**Language:** Python | **Status (2026-11-06):** fork of seung-lab/chunkflow, 126 ahead; last push 2023-11-05

Chunked distributed inference. Upstream: [../../seung-lab/infrastructure/chunkflow.md](../../seung-lab/infrastructure/chunkflow.md).

Zetta changes (Ran Lu, Kisuk Lee, 2023): **onnxruntime** backend when available, CPU fallback, memory estimation and grid rounding, input-mip scaling, whole-volume single-chunk inference, isotropic inference and affinity masking fixes. Later inference moved to zetta_utils (private).
