---
name: radd-task
description: Capture one unit of work as a job card in a research project's jobs column, with the commands to run it and a probe-status fence tracking its artifacts and scheduler jobs. Use whenever a request starts with "radd-task:", or when queueing a concrete run rather than framing a question.
---
# radd-task — one unit of work, on the board

```text
radd-task: <what to run>
/radd-task <project> "<what to run>"
```

Any prompt starting with **`radd-task:`** invokes this. Write the work as a card
in the project's `cards/` directory with `stage: jobs`, so it appears in the
board's jobs column and can be picked up by a fresh session.

## radd-task vs radd-hypo

They produce the same kind of file and differ in what they commit to.

| | [radd-hypo](../radd-hypo/SKILL.md) | radd-task |
|---|---|---|
| answers | "which is true?" | "run this" |
| stage | `idea` → `formulating` → `probing` → `reviewing` | `jobs` until it lands |
| core section | Hypothesis + acceptance written *before* results | Commands + what done looks like |
| contract kind | usually `science` / `exploration` | usually `engineering` |

If the request is really a question in disguise — it needs a baseline, a
falsifiable claim, or a "which is better" comparison — stop and use `radd-hypo`
instead. A job card with a hidden hypothesis is how an experiment ends up
judged on whatever number it happened to produce.

## Procedure

### 1. Resolve the project

A directory under `projects/`. Grep for identifiers in the request (dataset
names, run IDs, volume names) rather than matching a similar-sounding name;
sibling projects here deliberately share vocabulary. Ask if two could own it.

### 2. Write down how it actually runs

The card is the handoff, so it carries the real invocation, not a description of
one: the submit command, the config or script path, the host, the environment,
and any env vars that scope it. Copy them from something that has run, and say
where that was. Read [`projects/config/`](../../projects/config/README.md) for
site facts — environment activation, partitions, measured job sizing — and
reference them rather than restating them.

Record the resource ask **and where the number came from**. A memory-limit guess
that OOMs six hours in costs more than the job.

### 3. State what done looks like

One or two checks someone else could apply: an artifact exists at a path and is
non-degenerate, a metric is computed, a count matches. "It ran" is not done —
a job can exit 0 and write nothing, and an artifact can exist and be constant.

If the work produces a number that will be compared to another number, say which
baseline and what counts as a difference **now**, before the run. That is the one
piece of radd-hypo discipline a job card still needs.

### 4. Write the card

Path `projects/<project>/cards/YYYY-MM-DD_<slug>.md`, frontmatter with all seven
keys, `stage: jobs`, `track:` and optionally `task:` (`data`, `deep-learning`, `decoding`
`evaluation` or `qc`) to group the card with the others serving the same piece of work.
When the project's `spec.md` has a `## TRACKS` block, `track:` names the declared
track(s) the card serves, comma separated (`track: clahe, 8-bit`), or `shared` for a
prerequisite of every track in its task, and `cube:` names the target volume(s) if
not all; otherwise `track: job` or a finer slug like `decode`, `infra`:

```yaml
---
id: PROJECT-JOB-NNN
title: <the work, as an imperative>
project: <project directory name>
track: job
task: data
stage: jobs
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

Sections: **Objective** (what and why, one paragraph), **How to run** (the
commands), **Acceptance** (the checks), **Evidence** (paths, job IDs, and an
explicit *Missing:* list), **Authority** (who asked, dated; what it does and does
not cover; stop-and-escalate conditions), **Status**, **Connections**, **Notes**.

The heading must be exactly `## Acceptance` and its items must be markdown
checkboxes — `- [ ]` / `- [x]`. The board parses that heading and nothing else,
so a section called "Done when" reads as zero acceptance items and the card
looks unfinished no matter how well it is written.

Add `verdict: open` to the frontmatter. It is one of `open`, `met`, `failed`,
`inconclusive`, and stays `open` until evidence settles it — a finished job is
not a met acceptance, which is exactly the distinction the board's Next-decision
column exists to keep.

Add a `probe-contract` fence — `kind: engineering` for ordinary work — with
references to headings in this same card. Validate:

```bash
python3 -B probe/scripts/check_readiness.py projects/<project> --task cards/<file>.md
```

To make the card launchable from the board's hub (script path, `launch` block,
`hub.sh launch`), follow [rdash § Make a card launchable](../rdash/SKILL.md#make-a-card-launchable).

### 5. Declare status sources; never hand-write status

Job cards are exactly where a remembered status rots fastest. Add one
`probe-status` fence naming the artifacts and job IDs, leave the marker pair
empty, and generate:

```probe-status
{"schema_version": 1, "host": "bc",
 "artifacts": {"<label>": "<absolute path on the execution host>"},
 "jobs": [123456]}
```

```bash
python3 skills/radd-hypo/radd_status.py <project> --task cards/<file>.md --write
```

It reports artifact presence and scheduler state, marks anything unreachable
`unknown`, and will not infer a job's success from an artifact's presence or an
artifact's validity from a job's exit code. Regenerate whenever the card is read
after a state change; add each new job ID to the fence as it is submitted.

**The same fence feeds three board columns, so fill all three.** Besides
`artifacts` and `jobs` it carries:

```json
{"results":  [{"name": "val VOI", "path": "/abs/path/metric.json", "key": "best.voi",
               "baseline": 0.9129, "direction": "lower", "source": "where the baseline came from"}],
 "sessions": [{"label": "what this session is doing", "provider": "claude",
               "host": "bc", "cwd": "/abs/path"}]}
```

`results` rows must point at a `.json` file; `key` is a dotted path into it
(segments `[A-Za-z0-9_-]+`, at most 8 deep). Give a `baseline` and `direction`
whenever a number will be compared to another number — that is what turns a
measurement into a judgement, and writing it in the card fixes it before the run
rather than after the result is known.

The board only *observes* a declared path if its host is permitted: the host must
be in `RDASH_SSH_HOSTS` (the launcher defaults to `bc`) and the path must sit
under a root in [`projects/config/rdash-roots.yaml`](../../projects/config/rdash-roots.yaml).
Outside those it reads `unknown`, which means unobserved — never absent.

### 6. Move it off the board when it lands

`jobs` means outstanding. When the work is done, put the result in the card,
promote any durable conclusion to the project's `lessons/`, and set the stage to
something terminal — do not leave finished work in the queue, and do not delete
the card, since the commands and the sizing are the reusable part.

## Report back

Card path, checker exit status, the submit command, and what is still missing.
