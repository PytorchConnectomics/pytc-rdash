# CAVE / proofreading backend repos

**GitHub:** https://github.com/ZettaAI/PyChunkedGraph
**Language:** Python/Go | **Status (2026-11-06):** mostly forks; see table

| Repo | Kind | Notes |
|---|---|---|
| [PyChunkedGraph](https://github.com/ZettaAI/PyChunkedGraph) | fork of CAVEconnectome, 110 branches | Zetta branches: `zetta-python311-fixes`, `zetta-cloudbuild-stages`, `zetta/zstandard-tmp-fix`, `akhilesh-virtual-tables`; most others mirror upstream contributors (Sven Dorkenwald, Forrest Collman, Manuel Castro) |
| [CAVEdeployment](https://github.com/ZettaAI/CAVEdeployment), [CAVEpipelines](https://github.com/ZettaAI/CAVEpipelines) | mirrors | CAVE on GKE; chunkedgraph ingest, meshing, L2 cache |
| [EMAnnotationSchemas](https://github.com/ZettaAI/EMAnnotationSchemas) | mirror | annotation schemas |
| [cave_example_boulanger](https://github.com/ZettaAI/cave_example_boulanger) | original, notebook | CAVE usage example for a customer dataset (2025) |
| [auth-server](https://github.com/ZettaAI/auth-server) | original, Go | traefik `forwardAuth` for proofreading services (2021) |
| [state-server](https://github.com/ZettaAI/state-server) | original, Go | Neuroglancer state server (2023) |
| [graph-server](https://github.com/ZettaAI/graph-server) | original, Python/FastAPI | proofreading server (2021) |
| [helm-charts](https://github.com/ZettaAI/helm-charts) | original | charts: auth-server, annotation-framework, chunkedgraph, linkerd-mTLS, state-server, traefik routes |
| [microviewer](https://github.com/ZettaAI/microviewer) | fork, 2 ahead | read/write PNG segmentation to GCS |
| [webknossos](https://github.com/ZettaAI/webknossos) | mirror | — |
