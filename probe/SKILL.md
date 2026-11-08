---
name: probe
description: Preregister and evaluate empirical research experiments, choose a useful next test, and record evidence-backed lessons. Use for testing an idea, running an ablation, interpreting a completed experiment, or resuming a project research loop.
---
# Probe

Turn an authorized research question into a traceable experiment and a defensible conclusion. A valid negative result can complete an experiment without achieving the broader research objective.

## Resolve the project and method

The first argument is the **project-memory directory**, containing its spec and, when established, `loop.md`, `state.yaml`, and lessons. It is not the method package or the literature KB.

Read the project's method adoption record before changing its state. New bootstraps use **probe 2.0**, defined in [the protocol](protocol/PROBE_PROTOCOL.md). An existing project keeps its adopted revision and explicit local rules. Resolve a pinned protocol from that Git revision or recorded immutable snapshot; do not silently substitute the newest checkout. Unversioned projects retain their recorded legacy rules until a version change is explicitly adopted. Read [protocol §1](protocol/PROBE_PROTOCOL.md#1-adoption-and-authority) for resolution and authority.

## Route the request

| Request after the project directory | Action |
|---|---|
| An intuition | Select the stated test, preregister it, and execute within its authorized scope |
| No second argument | Show status and recommend useful next work; do not infer permission to launch |
| `status` | Reconstruct state, open runs, evidence gaps, and decisions needed; read-only |
| `next` | Recommend a candidate; execute only if selection and execution are already authorized |
| `bootstrap` | Build a v2 project contract from available context; use the [templates](templates/) and scaffold described in [protocol §7](protocol/PROBE_PROTOCOL.md#7-actions-and-helpers) |
| `lesson [run-or-name]` | Identify the run and land its evidence and verdict using [protocol §6](protocol/PROBE_PROTOCOL.md#6-landing-and-resume) |

Optional modifiers remain `implement=none|full-claude|full-codex|ccc-duet` and `auto`. Backend selection and actual shell signatures are in [protocol §7](protocol/PROBE_PROTOCOL.md#7-actions-and-helpers). `auto` reduces routine check-ins within existing authority; it grants no additional scope, budget, or permissions.

## Essential decision boundaries

- Carry forward the task's authorization, consumed budget, and stop conditions. Do not repeat fixed approval checkpoints already satisfied by the user.
- Gate settings belong to the project. A gate pass permits the defined next step; it does not establish scientific success.
- Check implementation and measurement validity separately from the hypothesis. Report valid negatives, inconclusive findings, invalid measurements, and execution failures distinctly.
- Keep generic procedure in the adopted protocol and project settings in the project. Method proposals and their history live in [reviews/README.md](reviews/README.md); they do not automatically change active projects.
