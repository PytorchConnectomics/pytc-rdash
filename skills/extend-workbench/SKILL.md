---
name: extend-workbench
description: Add a project, card, notebook, host config or lesson to a pytc-jam workbench as a pull request that passes the workbench checks, so any student's agent can extend the repo without the maintainer. Use when asked to "add a project", "start a notebook", "add a lesson", "set up my host config" or to prepare a PR to pytc-jam or pytc-jam-msi.
---
# extend-workbench — a mergeable PR from any agent

The workbench (`pytc-jam` for BC, `pytc-jam-msi` for Mindspan) is the team's living repo.
It grows only by PR. This skill is what the repo ships so that *your* agent can extend it the
way the maintainer would, and so the maintainer's review is a merge decision, not a rewrite.
The tooling under `rdash/` is a submodule: never edit it here; send a tooling fix to
`PytorchConnectomics/pytc-rdash` by PR.

## Before anything

1. `git submodule update --init rdash` and read the workbench `CLAUDE.md` (one screen of
   invariants). Do not read more than the project you are extending.
2. Branch from `main`: `git checkout -b <owner>/<slug>`.
3. Know which workbench you are in. A project named `msi-*` belongs to `pytc-jam-msi` only;
   `tests/test_boundary.py` refuses it elsewhere.

## The five extensions

| You want | Do | Files |
|---|---|---|
| **A project** | copy `projects/TEMPLATE/` to `projects/<name>/`, fill `spec.md` (GOAL, TASK CONTRACT, TRACKS fence), add the label to `projects/config/project-labels.json` | `projects/<name>/spec.md`, `projects/config/project-labels.json` |
| **A card** (a run or a question) | `rdash/skills/radd-task/SKILL.md` for "run this"; `rdash/skills/radd-hypo/SKILL.md` for "which is true". Owner-scoped ID `<PROJECT>-<TASK>-<owner>-<NNN>`, `owner:` in frontmatter, `state: working` | `projects/<name>/cards/YYYY-MM-DD_<owner>_<slug>.md` |
| **A notebook** (one person, two models, one iteration at a time) | create `focus/F-NNN.md` with frontmatter `state: working`, the standing report block, Goal and evaluator, State, Best, Tried, Next; rules in `rdash/rloop/focus/planner-loop/README.md` | `projects/<name>/focus/F-NNN.md` |
| **Host config** | copy `projects/config/` to `~/.config/rdash/config` and edit *there*; the committed files are templates with placeholders | nothing committed; never your account name or a shared root |
| **A lesson** | one file in `projects/<name>/lessons/`, naming the result file its number came from and the scope it holds for; add its row to `lessons/lessons.md` | `projects/<name>/lessons/lesson_<slug>.md` |

Write the problem, not the route: the card states hypothesis, data split, metric, threshold and
budget (that is scientific control); it does not prescribe how the implementer should code it.

## Checks the PR must pass (run them yourself)

```bash
python3 -m unittest discover -s tests                       # boundary: no msi-* here, rdash is a submodule
RDASH_REPO_ROOT=$(pwd) python3 -m rdash.dashboard.app.lint  # duplicate card IDs, owner mismatch
python3 rdash/probe/scripts/check_readiness.py <project>    # if you touched a contract fence
python3 rdash/rloop/focus/planner-loop/check_plan.py <plan> # if you wrote a plan.md
```

A failing check is fixed in the PR, not explained in the description. Renumber the *newer* card
on a duplicate ID.

## What the PR looks like

- Title: `<project>: <what it adds>` (one line).
- Body, four lines: what this adds; which check output you ran (paste the last line); what it
  does **not** claim (no result, no verdict, no launch authorized by the merge); who owns it.
- One concern per PR. A project plus its first card is one PR; a lesson is its own PR.

## Never in a PR

Credentials, signed links, `data.yaml`, source data, run artifacts, a copy of anything under
`rdash/`, an edit to another owner's card, a number without the file it came from, a Mindspan
path or record in the BC workbench.

## What happens next

`rdash/skills/pr-review/SKILL.md` describes the review an agent runs on your PR; it writes one
recommendation (merge, close, needs-change) with evidence. The maintainer decides. A closed PR
is not a judgement of you; it was written by an agent, and the idea may come back as a card.
