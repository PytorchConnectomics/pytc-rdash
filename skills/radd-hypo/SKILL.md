---
name: radd-hypo
description: Write one hypothesis or task as a self-contained contract card under a research project, validated by the probe readiness checker, so a fresh Claude or Codex session can execute it by reading the card alone. Use when capturing a research question, framing a comparison, or preparing work to hand off to an agent session.
---
# radd-hypo — one task, one contract card

Turn **one** hypothesis or task into a card that is simultaneously a research-dashboard
entry and an executable contract. The card is the handoff: a fresh session reads it and
nothing else from this conversation.

```text
/radd-hypo <project> "<hypothesis or task>"
/radd-hypo <project>                          # ask for the task, then proceed
```

`<project>` is a directory under `projects/` (e.g. `<org>-<topic>-26`). It is the project-memory directory, not a code repo.

## Scope

One card = one task = one contract. Do not bundle a second question into the same card;
write a second card and cross-link it. Writing a card is not authorization to run
anything, and an authored card verdict does not replace canonical conclusions in the
project's `lessons/` and state files.

## Procedure

### 1. Place it in the right project

Confirm the project directory before writing. Grep the projects tree for the identifiers
in the request (dataset names, run IDs, experiment IDs) rather than matching on a
similar-sounding name — sibling projects here deliberately share vocabulary and mean
different datasets. If two projects could own it, ask; a card in the wrong project
imports the wrong baseline.

### 2. Read the project before writing about it

Read the project's `spec.md` (goal, environment, tasks, milestones, invariants, stop
conditions, open `FILL:` items), its `state.yaml` / `loop.md` if present, and the
`lessons/` entries that bear on the task. Pull the **existing baseline number and its
exact scope** — a card whose acceptance has no baseline is not executable.

Note which project invariants constrain the task. If an invariant forbids the obvious
form of the answer (for example, "this pipeline's output may not be presented as a
quality claim"), say so in the card and design around it. That constraint is usually the
most valuable thing the card carries.

### 3. Separate what is known from what was asserted

Label every fact in the card as one of:

- **verified here** — found in this repository, with the file, section, run directory or
  job ID quoted;
- **user-reported** — stated in the request and not yet in the repository, marked with
  the date and the phrase "not yet verified in this repository";
- **missing** — named explicitly, in its own list.

Never promote a user-reported run into a verified one, never invent a run directory,
config path, job ID, or metric, and never carry a number across datasets. If the
decisive artifact does not exist yet, the card's job is to say precisely which four or
five facts are missing and who supplies them.

### 4. Find the confounds and the scoreable volume

Two checks do most of the work:

- **Is the stated comparison a single variable?** Infrastructure changes (GPU count,
  node type, batch layout) usually drag effective batch size, learning rate, step count
  and EMA behaviour with them. If they were not held fixed, record the comparison as a
  recipe-vs-recipe comparison and say what has to be logged to disentangle it.
- **Can the proposed data decide it?** Evaluation needs ground truth. If the volumes
  named in the request have none, say so plainly, name the volume that does have GT and
  its existing baseline, and make that the primary experiment. Demote the GT-free data
  to a transfer or sanity check with explicitly GT-free proxies.

Also carry forward any known decode/eval trap from the project's lessons that would
silently produce garbage — threshold conventions, output-naming limits, axis or channel
order, memory sizing. A fresh session will hit them.

### 5. Write the card

Path: `projects/<project>/cards/YYYY-MM-DD_<slug>.md`. Slug is lowercase
`[a-z0-9._-]`, ≤ 80 characters before `.md`. Create `cards/` if absent.

Frontmatter is the dashboard contract — all seven keys, `project` matching the directory
name exactly, `id` stable across renames, stage one of `idea`, `formulating`, `probing`,
`reviewing`, `parked`:

```yaml
---
id: PROJECTSLUG-TRACK-NNN
title: <the question, as a question>
project: <project directory name>
track: <lowercase slug, e.g. model, decode, data, infra>
stage: formulating
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

Then a `probe-contract` fence — exactly one per file, `schema_version: 1`, `kind` one of
`engineering`, `science`, `exploration`, and references to headings **in this same
card**. Paths are project-relative and may not contain `..`; anchors are GitHub-style
slugs of the card's own ATX headings. `science` additionally requires `method`.

```probe-contract
{
  "schema_version": 1,
  "kind": "exploration",
  "references": {
    "objective":  "cards/<file>.md#objective",
    "acceptance": "cards/<file>.md#acceptance",
    "evidence":   "cards/<file>.md#evidence",
    "authority":  "cards/<file>.md#authority",
    "method":     "cards/<file>.md#decision-procedure"
  }
}
```

Pick `kind` honestly. A comparison with a falsifiable claim and a scoreable volume is
`science`; selecting or wiring a component is `engineering`; "we have outputs and no way
to score them yet" is `exploration`.

**The fence does not adopt probe.** It is the readiness checker's structure format,
which probe happens to ship as a linter. A project runs the probe loop only if it has
its own `loop.md` recording an adopted revision. If the project has none, say so in the
card rather than letting the fence imply a method the project never adopted, and follow
whatever discipline its `spec.md` actually defines.

Required sections, in this order:

| Heading | Contains |
|---|---|
| `## Status` | A `probe-status` fence declaring artifacts and job IDs, then the generated block between the two markers — never a hand-written table. Authored prose here is limited to what a machine cannot answer, e.g. whether the project has adopted probe. |
| `## Objective` | What is being decided and why it matters *to this project*; which `FILL:`/open item it closes. The user-reported vs verified split goes here. |
| `## Hypothesis` | H1, the H0 it must beat, and each unexcluded confound as its own labelled alternative. |
| `## Decision procedure` | The ordered experiment. Primary experiment on data that can decide it; secondary reads demoted and labelled. Traps and resource sizing. |
| `## Acceptance` | The baseline number with its scope, what counts as a difference (state the noise floor), and what must **not** be claimed. |
| `## Evidence` | Verified artifacts with paths/job IDs; then an explicit **Missing:** list. |
| `## Authority` | Who authorized it, dated; what it covers; what it does not; stop-and-escalate conditions. |
| `## Connections` | Links to spec sections, prior logs, sibling projects (marked when a different dataset), run IDs, agent sessions. |
| `## Ideas and discussion` | Dated entries. Quote the user's framing verbatim, then mark which parts of the card are your additions rather than their claim. |
| `## Next decision` | The missing facts, each with an owner, and the fork the human has to settle. |

Keep the dashboard rules: cards are entry points, not duplicate experiment ledgers. Link
canonical plans, results and lessons where they already live; preserve original
predictions and source dates; append revisions rather than rewriting them.

Use `- [ ]` task items under `## Acceptance`, including forbidden-claim items.
Indented continuations belong to the same item. Only a person checks an item;
append a dated entry in `## Ideas and discussion` naming the item and evidence.
A checked item carries ` — evidence: <references>` at its end. References are
1–8 identifiable tokens (up to 200 characters each): an absolute path, a
repository-relative filename with extension and optional anchor, a 6–10 digit
scheduler job ID (optional array suffix), or a Markdown link. Prose such as
"looks good" is not a reference. A reference's syntax does not prove support.
On uncheck, remove the suffix and preserve its references in the dated log,
with the human's reason (or note "none recorded" if there was no suffix).
Optional frontmatter `verdict` accepts `open`, `met`, `failed`, `inconclusive`.
Only a human writes it, alongside a dated rationale in discussion. Never derive
acceptance or verdict from scheduler state or artifact presence. rdash currently
displays these authored fields read-only; its evaluation write endpoints are deferred.

### 6. Declare status sources; never write status by hand

A remembered status is wrong as soon as a job changes state, and it reads as
authoritative while being wrong. Declare the sources instead, in one
`probe-status` fence, and leave an empty pair of markers for the report:

```probe-status
{
  "schema_version": 1,
  "host": "bc",
  "artifacts": {"<short label>": "<absolute path on the execution host>"},
  "jobs": [3013750, 3013751]
}
```

```text
<!-- radd-status:begin -->
<!-- radd-status:end -->
```

Then generate, and regenerate whenever the card is read after a state change:

```bash
python3 skills/radd-hypo/radd_status.py <project> --task cards/<file>.md --write
```

It reports artifact presence/size/mtime, scheduler state for each job (live
`squeue` first, then `sacct`), and whether the contract still passes the checker.
Add `--json` for a machine-readable report. Anything it cannot reach is
`unknown`, never guessed — and it deliberately does not infer a job's success
from an artifact's presence, or an artifact's validity from a job's exit state.
Unlike contract references, status paths are absolute execution-host paths and
are expected to sit outside the repository.

`host` names an ssh alias; omit it to probe the local machine. When the host is
unreachable the report says so and every row degrades to `unknown`, so a stale
snapshot cannot pass for a fresh one — which also means a committed report is
safe to hand to a session with no cluster access.

### 7. Validate the contract

```bash
python3 -B probe/scripts/check_readiness.py projects/<project> --task cards/<file>.md
```

Exit 0 with every reference `PRESENT` is required before the card is handed off. Fix any
`MISSING` anchor (usually a heading renamed after the fence was written). The residual
`UNKNOWN` entries for authority and evidence verification are expected and correct.

**Exit 0 is a structure check.** It does not establish scientific validity, engineering
correctness, or permission to execute — never quote it as a green light.

### 8. Hand off

The card is the prompt. A fresh session gets the checkout path, the card path, and the
execution host; it reads the nearest `CLAUDE.md`, `standards.md`, the card, and the
project files the card links. Give it the lock discipline (`.agent-lock` in the project,
exclusive create, release only your own) and the log destination
(`projects/<project>/logs/YYYY-MM-DD_<task-slug>.md`).

For a non-interactive delegated run:

```bash
probe/scripts/probe-run-agent.sh codex /path/to/prompt.md /path/to/final.md
```

`claude` is the other backend. Invoke it from the intended code workspace; verify the
agent's final message against actual artifacts rather than trusting the summary.

## Report back

State the card path, the checker's exit status, the primary experiment in one sentence,
and the missing facts that block it. Do not summarize the card's full contents — the
point of the card is that it does not need a summary.

## Optional live measurements

Add `results` inside the existing `probe-status` JSON object, for example:

```json
"results": [{"name": "val NERL", "path": "results/metric.json", "key": "nerl",
             "baseline": 0.604428, "direction": "higher",
             "source": "contract baseline reference"}]
```

Copy the actual contract baseline; omit it if no baseline is declared. The
example is illustrative, not a measurement for a new card. The board reads
JSON data only (at most 1 MiB), never generators. Missing and unreadable results
are not zero. Relative paths use the project's results/ or logs/ root; external
content requires operator roots documented in dashboard/README.md. Generated
`radd-status` blocks remain handoff snapshots; the board collapses and age-labels
them below the live artifact table. Refresh the snapshot with `--write` for a
handoff, not to refresh the board. Health and session attach remain deferred.
