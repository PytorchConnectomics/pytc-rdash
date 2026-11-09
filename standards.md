# standards.md — Coding Standards & Cluster Reference

Read this before writing or modifying code. For agent workflow, see [CLAUDE.md](CLAUDE.md). Follow the selected project's requirements and its owning code repository's conventions; the PyTC conventions below apply to projects using that stack.

## Source of Truth Boundaries

| Information | Canonical home |
|-------------|----------------|
| Scientific question, biological/imaging rationale, hypotheses, decisions, limitations, and lessons | The relevant project files in this repository |
| Scientific task state and next experiment | The project's spec and existing scientific-state record |
| Accepted reusable research-loop procedure | `probe/protocol/PROBE_PROTOCOL.md` at the project's adopted revision; project settings/adaptations remain local |
| Method proposals and reviews | `probe/reviews/`, read on demand; proposals do not become rules until accepted into the protocol |
| Project process reviews and retrospectives | The relevant `projects/<name>/retrospectives/` |
| Application code, runtime configuration, data, checkpoints, and substantial run artifacts | The owning code repository and its storage; the project spec links permitted locations |
| Personal allocation, domain priorities, team commitments, session coordination, and work-in-progress limits | The dw-os planner, `workflow/`, and relevant `ops/` records |
| Outside-source synthesis and broadly reusable knowledge | `dw-kb` |
| Collaborative narratives and presentations | Google Docs/Slides derived from canonical planning and research evidence |

Keep scientific rationale with its decision and evidence. Link external source material instead of copying it into a second editable record. Preserve each project's sharing boundary: shared specs must not expose private data or filesystem paths; keep restricted execution configuration on its owning side.

## Evaluation bank

`probe/evals/` (behavior cases in `cases.json` and the `failure-replay/` tasks) is the
human-owned evaluator of the agent engine. Any PR that adds, changes or removes a case,
expected answer, verifier or recorded score requires DW's explicit approval; an agent or
self-improvement loop may run the bank, never edit it. This is the review-rule form of the
former root `dw-os/evals/` directory boundary (2026-11-08).

## Project Spec Format

For an executable assignment, `projects/<name>/spec.md` should contain the following sections or their existing equivalents. An exploratory project may record unresolved fields explicitly; do not fabricate paths, data dimensions, or metrics to fill a template.

### Required Sections
- **GOAL** — question, scientific rationale, task, target objects, and data modality
- **ENVIRONMENT** — owning code repository, execution host, permitted input/code/output locators, environment, and libraries; restricted locations stay in the authorized runtime configuration
- **DATA SPEC** — file naming, array shapes, channel semantics with indexing, resolution, data types
- **TASKS** — per-script: location, purpose, CLI usage, implementation pattern, status tag
- **MILESTONES** — ordered list with status tags: `DONE`, `CURRENT`, `TODO`, `BLOCKED`

For a project using `probe`, its existing `loop.md` or equivalent records the adopted protocol revision, evaluator/gate settings, and explicit project adaptations. The generic procedure stays in `probe/protocol/`; do not reproduce it as a second authoritative project protocol. Preserve existing adoption, scientific gates, and thresholds until an explicit project adoption change. A missing revision is a gap to resolve, not permission to substitute the newest protocol. Method reviews and project retrospectives remain evidence for review, not additional default bootstrap rules.

### Style Rules
- Use tables for paths, function signatures, and generated files
- Specify array shapes explicitly: `(267, 2048, 2048, 2)` not "a 3D volume"
- Include channel semantics with indexing: `im[:,:,0]` = Red → axons
- Write concrete next actions, not "continue project" or "improve results"
- Every execution command must be copy-pastable in its stated authorized environment; keep restricted values in that environment's configuration

## Coding Standards

### Debugging, testing, and module design

Three reusable disciplines live in `dw-kb/skills/aihero-skills/skills/`; read the
selected `SKILL.md` before the matching task, rather than re-deriving it here.

| Situation | Read |
|-----------|------|
| A bug or performance regression that is not obvious | `engineering/diagnosing-bugs/` |
| Choosing what to test and where the seam goes | `engineering/tdd/` |
| Designing or reshaping a module's interface | `engineering/codebase-design/` |

Three rules from them apply to research code in this repository regardless of
stack:

- **Build a feedback loop before forming a theory.** Get one fast, deterministic,
  agent-runnable command that fails on the actual symptom and run it once, then
  hypothesise. A run that merely finishes without erroring is not that command.
- **Name the seams under test before writing tests.** Testing effort lands on the
  critical path by agreeing the seams up front; everything else stays untested on
  purpose, and the spec records that choice.
- **Expected values come from an independent source.** A check that recomputes the
  expected value the way the code does passes by construction. Use a known-good
  literal, a worked example, a published number, or an independent implementation.

These decide whether *code* is correct. Whether a *scientific claim* is supported
stays with the project's adopted `probe/protocol/` revision and its gates.

### Existing PyTC conventions

Apply these to PyTC-based work. Other microscopy, simulation, reconstruction, or analysis projects use their own documented stack and data conventions.

- **Framework:** PyTorch + PyTorchConnectomics ecosystem
- **I/O library:** `em_util` (see `tools/em_util.md`)
- **Training/Inference:** `pytc` (see `tools/pytc.md`)
- **Annotation tool:** VAST Lite (see `tools/vast.md`)
- **HDF5 convention:** dataset name `"main"`, gzip compression (automatic via `write_h5`)
- **Volume axis order:** ZYX for volumes, XYZ for neuroglancer

### Script Organization
- Put new application, experiment, and pipeline code in the owning code repository specified by the project. Document its location and invocation in the project spec here.
- Keep existing scripts colocated with project specs where they already are. No relocation is required to continue or reproduce that work; follow the spec's recorded location.
- Reusable `probe` method utilities belong under `probe/scripts/`; keep project-specific implementation in its owning code location.
- Each standalone task script maps to a pipeline step and has a documented, independently runnable command. Preserve the owning repository's module/package conventions.
- Where a project uses ordered scripts, use numeric prefixes such as `01_preprocess.py`, `02_train.py`. Add shared helpers only when multiple scripts reuse non-trivial logic, in the owning code location.

### Code/Data Separation
Never hardcode data paths into new application code. Use the owning project's configuration mechanism and permitted runtime paths. For existing standalone scripts that use an adjacent `data.yaml`, preserve this pattern and its execution location:
```python
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.yaml')
with open(config_path) as f:
    cfg = yaml.safe_load(f)
```

### CLI & Parallelism
- Use `sys.argv` for CLI args.
- Support `job_id`/`job_num` for parallel chunking.

### Error Handling
If a job fails, attempt one logical fix (halve batch size, verify path). If it fails twice, log the error and stop.

## Agent Locking Convention

Before project writes or execution, check ownership and exclusively create a lock
file. Read-only inspection and readiness/source checks do not mutate locks:

```python
# .agent-lock format (JSON)
{"session_id": "abc123", "started": "2026-04-06T14:30:00Z", "task": "fiber_seg Stage 0b"}
```

- If `.agent-lock` exists and `started` is < 6 hours ago, another agent may be active — skip mutations to this project.
- An older lock does not prove that its job stopped. Reconcile actual run/job state and ownership before takeover; this convention does not implement distributed locking or automatic recovery.
- Use exclusive creation and remove only your own lock when done or on failure.
- `.agent-lock` files are gitignored.

## Session Log Format

After each session, write to `projects/<name>/logs/YYYY-MM-DD_<task-slug>.md`:

```markdown
# Session: <task name>
- **Date:** YYYY-MM-DD HH:MM
- **Task:** <what was attempted>
- **Commands:** <scripts run, SLURM job IDs>
- **Outcome:** success | failure | blocked
- **State change:** <which status tags were updated>
- **Notes:** <errors encountered, assumptions made>
```

## Cluster Reference

### Harvard FASRC
- Scheduler: SLURM
- Home: `/n/home04/donglai/`
- Common conda envs: `imu`, `pytc`, `tensorstore`
- GPU partitions: `gpu`, `gpu_requeue`

### BC
- Scheduler: SLURM
- GPU partitions: `gpu` (≤24h), `gpu-long` (≤7d)

## Quality Bar

A project spec is complete only if:
- Execution paths are verified in the authorized environment; shared records contain only permitted locators and point to local configuration when needed
- Applicable array shapes and channel semantics are explicit
- Every script has copy-pastable usage commands in its recorded code/runtime location
- Milestones have status tags
- Another agent can resume work from the spec alone
