# zetta_utils (private) and mazepa

**GitHub:** https://github.com/ZettaAI/zetta_utils
**Language:** Python | **Status (2026-11-06):** zetta_utils returns 404; no public copy found. mazepa fork is public.

zetta_utils is Zetta's current framework for alignment, inference, segmentation and task scheduling on GKE. It is private, absent from Software Heritage, Wayback and PyPI, and its readthedocs site is an empty 2022 placeholder (checked 2026-11-06).

What is visible publicly:
- **[vscode-zutils](https://github.com/ZettaAI/vscode-zutils)** (2026-07): VS Code extension for zetta_utils **builder specs written in CUE**. Each spec block has an `"@type"` naming a registered Python builder (with `@version`); the extension introspects the registry for hover docs, validates parameters against Python signatures (including `Literal` typos), and go-to-definition. So zetta_utils is configured as typed, versioned CUE specs over a builder registry.
- **[mazepa](https://github.com/ZettaAI/mazepa)** (fork of seung-lab/mazepa, 45 ahead, 2022, Sergiy Popovych): the task/flow layer that became `zetta_utils.mazepa` — Tasks and Flows as protocols, multi-queue workers, a mypy plugin.
- **[gke-gpu-monitor](https://github.com/ZettaAI/gke-gpu-monitor)** (2026-05): terminal dashboard for GKE GPU node pools: autoscaler status, **stockouts**, pending pods, `FailedScaleUp` history. Example cluster `zutils-x3` in project `zetta-research`.
- typeguard/mypy forks: runtime type checking of specs (mock-object hack, constrained TypeVar decorators).
