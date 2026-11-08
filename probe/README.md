# Probe — empirical research method

`probe/` is maintained inside **dw-research**, mounted at `dw-os/research/`.
It provides a skill, an accepted scientific procedure, project templates, and
small supporting scripts. The coordinating agent turns an authorized research
question into a traceable experiment and an evidence-backed conclusion.

## Method and ownership

[Protocol 2.0](protocol/PROBE_PROTOCOL.md) is the accepted generic method for
**new bootstraps**. [SKILL.md](SKILL.md) routes an invocation. Project memory
lives in [projects/](../projects/): objectives, evaluation/gate settings,
preregistered runs, results, scientific constraints, and lessons. The planner
owns allocation and authorized assignments.

A project's `loop.md` records the adopted method version and source Git revision
or immutable snapshot, plus project settings and explicit adaptations. Load that
source when running the project. Existing projects retain their recorded legacy
rules until an explicit adoption; updating the installed skill does not
retroactively change an experiment or silently migrate scientific state.
[Method reviews](reviews/README.md) preserve evidence and proposals leading to
method changes; a proposal is not an operative rule.

## What v2 changes

- **Gates fit the question.** Exact evaluator shortcuts, empirical pilots,
  diagnostics, and authorized direct experiments have different evidentiary
  meanings. Cost and faithfulness are justified for the project, with no
  universal percentage or exactness requirement. A gate pass permits a next
  step; it is not scientific success.
- **Correct execution and scientific outcome are distinct.** Separate engineering
  checks from hypothesis decision rules and operational stops. Preserve valid
  negatives, inconclusive evidence, invalid measurements, and execution failures
  as different outcomes.
- **Scientific constraints have a scope.** Link evidence, assumptions,
  limitations, reopening conditions, and verification appropriate to their
  consequence. A failed run does not become a permanent class-level kill.
- **Selection admits uncertainty.** Measured properties may be multiple or
  qualitative. Headroom scoring is optional for meaningful comparable quantities;
  unknown bounds and probabilities stay unknown.
- **Authority persists.** Honor existing task permission, consumed/remaining
  budget, and stopping conditions across sessions. Request only consequential
  missing decisions or changes beyond that authority, rather than repeating
  fixed approval checkpoints.

## Install and invoke

Install this **`probe/` subdirectory** as a skill. From the root of a dw-research
checkout, or `dw-os/research/`:

```bash
mkdir -p ~/.claude/skills
ln -s "$PWD/rdash/probe" ~/.claude/skills/probe
```

The destination must not already exist. Inspect and update an existing link
through the normal skill-management workflow instead of creating a second
editable method copy. Codex or marketplace installation should likewise select
this skill subdirectory.

The first argument is the **project-memory directory**, not the skill package
or literature KB:

```text
/probe "<project>" "<intuition>"   # an authorized experiment or ready proposal
/probe "<project>"                 # status plus useful next work; no launch implied
/probe "<project>" bootstrap       # configure a new v2 project from known context
/probe "<project>" next            # recommend; execute only within granted authority
/probe "<project>" status          # read-only reconstruction
/probe "<project>" lesson <run>    # inspect evidence and land or propose the verdict
```

Modifiers remain `implement=none|full-claude|full-codex|ccc-duet` and `auto`.
[Protocol §7](protocol/PROBE_PROTOCOL.md#7-actions-and-helpers) defines their
behavior. `auto` reduces routine check-ins; it does not expand permissions.

## Helpers and implementation limits

### Read-only task inspection

From a `dw-research` checkout:

```bash
python3 -B probe/scripts/check_readiness.py projects/nisb-base-26 \
  --task research_plan/2026-09-15_evaluator-regression.md
```

Add `--json` for a derived machine-readable report. The default selected file is
`spec.md`; `--task` selects an existing project-relative file. Legacy prose
without a contract is reported as unknown and remains unchanged.

The checker recognizes exactly one `probe-contract` JSON fence with
`schema_version: 1`, `kind` (`engineering`, `science`, or `exploration`), and
`references`. Reference keys are `objective`, `acceptance`, `evidence`, and
`authority`; a `science` task also requires `method`. Engineering and exploratory
tasks may link a method when applicable without inventing a scientific hypothesis.
See the [project template](../projects/TEMPLATE/spec.md#task-contract) and
[real NISB engineering task](../projects/nisb-base-26/research_plan/2026-09-15_evaluator-regression.md).

References locate existing canonical sections or files; they do not copy their
contents. Paths resolve from the project root; a bare `#heading` refers to the
selected task file. ATX Markdown headings are supported. External references
and unsupported fragments remain unknown; no network access is attempted.
The checker rejects ambiguous contracts and traversal paths. Files are inspected
as bounded UTF-8 text, with a 1 MiB limit per text read.

`present` means a reference was found, not that its content is complete, true,
scientifically valid, or sufficient authority. Evidence plans may point to an
existing section describing future artifacts. Actual artifacts require separate
verification. Exit code 1 indicates missing/inconsistent structure; exit code 0
can still contain unknowns and must never authorize a launch. Apply the user's
existing authority without asking again merely because a tool cannot verify it.

### Evaluator receipts and behavior cases

The [NISB example](examples/nisb/README.md) connects to the real external PyTC
NERL evaluator and `em_erl` backend. Its default is inspection. Explicit CPU
fixture execution records hashes, parameters, per-check observations, and a
receipt that can be rechecked for drift. It tests evaluator behavior on synthetic
cases; it does not reproduce a NISB benchmark or validate a model checkpoint.

[Behavior cases](evals/README.md) provide reusable, fictional inputs for comparing
agent decisions. Deterministic helper tests run with:

```bash
python3 -B -m unittest discover -s probe/tests -v
```

These additions do not implement a persistent supervisor or silently change a
project's adopted method. Their scope and actual validation are recorded in the
[implementation review](reviews/2026-09-15-executable-checks.md).

### Existing scaffolding and launcher

`scripts/probe-init.sh <project-directory>` copies missing state/loop templates
and creates its standard directories/index. The coordinator fills and checks
those files; the script does not validate readiness or migrate old projects.

The delegated-step launcher accepts a **prompt filename** or `-` for stdin.
Invoke its absolute path from the intended code workspace:

```bash
/path/to/<workbench>/rdash/probe/scripts/probe-run-agent.sh claude /path/to/prompt.md /path/to/final.md
```

Use `codex` instead of `claude` for the other launcher backend. It inherits the
working directory/environment and writes the final agent response. Verify that
response against artifacts. The separately available CCC backend is optional.

The scripts do not implement a persistent supervisor, numeric candidate optimizer,
budget enforcement, job monitoring, restart recovery, or planner notifications.
The coordinator maintains run records and applies the adopted protocol. No new
runtime guarantees are implied by v2.

[Templates](templates/) supply new-project/run scaffolds. The
[NISB reference example](examples/README.md) preserves the method's historical
origin and links its current project memory; its old metric and gate settings
are not defaults for other projects.
