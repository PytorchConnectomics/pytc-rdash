# Planner-loop handoff files

Fable 5.1 (planner/interpreter) and Opus 5.5 (implementer) share context **only through Markdown files**.
Each model starts cold: it reads the files, does its step, and writes its file. A chat transcript or a
subagent's return message is not memory, and anything not written down is lost at the handoff.
Method: [2026-11-05 planner–implementer trial](../../../probe/reviews/2026-11-05-planner-implementer-loop.md).

## Layout

```
projects/<project>/focus/
  F-NNN.md                 # notebook: frontmatter `state:`, goal, State, Best, Next — the long-lived state
  F-NNN/
    iter-01/
      plan.md              # Fable writes; frozen once Opus starts
      effects.md           # Opus appends: intent before each submit/upload/push, settled after
      receipt.md           # Opus writes; facts only
      interpret.md         # Fable writes; verdict, Best update, next plan seed
    iter-02/ ...
```

## Who reads and writes what

| Step | Model | Reads | Writes |
|---|---|---|---|
| Plan | Fable | notebook, previous `interpret.md`, the project spec | `iter-NN/plan.md`, plus a `Next` line in the notebook |
| Implement + run | Opus | `plan.md` (its whole brief), the files it links, `research/standards.md`, `effects.md` if it exists | code, card, `effects.md` lines around each job, then `receipt.md` |
| Interpret | Fable | `plan.md`, `receipt.md`, the raw result files the receipt names | `interpret.md`, then notebook `State` / `Best` / `Next` |

## Rules

1. **Self-contained.** Each file must make sense to a model that has seen nothing else. Use full
   repository-relative paths or `cajal:/...` paths. Avoid "as discussed" and "see above".
2. **The plan is frozen once Opus starts.** If the plan cannot be followed, Opus stops and records the
   reason under `Deviations` in `receipt.md`. Only Fable revises a plan, as a new file `plan-v2.md`.
3. **Receipts hold facts only.** Commands, commits, job IDs, output paths, and numbers copied verbatim
   with the file they came from. No interpretation.
4. **Every number in `interpret.md` or `Best` cites the file it was read from.** No file, no number.
5. **Negative and failed results are written up too.** A failed job is a receipt plus an interpretation.
6. **Respect project boundaries.** No Mindspan data or credentials go into BC files. Paths that point
   at data are fine; data contents are not.
7. **One state signal, declared not inferred.** The notebook's frontmatter carries
   `state: working | needs-you | paused | done`. A session may end in a waiting state only by setting
   `needs-you` and writing a `## Needs you` section with one to three ranked options and a
   `Recommendation:` line (the same block closes `interpret.md`). The board and
   `rdash/dashboard/app/needs_you.py` read that field; a free-text `Decision needed:` line is
   display, not the bell. `paused` is set by a person and rings nothing.
8. **Intent before every external action, settlement after.** Before `rsub`/`sbatch`, a GCS
   upload or a push to a shared branch, append `- intent En <time> <action> ... job-name=<exact>
   comment=<exact> replay=never` to `iter-NN/effects.md`; when it returns, append
   `- settled En <time> ok|error|aborted|unknown slurm=<id>`. A session that starts or resumes
   an iteration reads `effects.md` first. An intent with no settled line means "may have run":
   look it up by exact job-name and comment in `sacct`, settle it, or set `needs-you` asking
   whether it ran. Never submit again while one is open. Template: [effects.md](effects.md).
   (From the legacy rloop reservation rule and Agnes Harness's intent/settled ledger,
   dw-os `workflow/reviews/2026-11-22-agnes-harness.md`.)
9. **No `Best` row without a check that ran.** The receipt's `## Progress` block names the
   proving check and its result (pass / fail / not run), what changed since the last
   iteration, and FINISH / CONTINUE / SWITCH. Interpret may not add a `Best` row whose proving
   check says `not run`. Run `python3 rloop/focus/planner-loop/check_receipt.py <iter-dir>`
   before interpreting; exit 0 is required.

Templates: [plan.md](plan.md) · [effects.md](effects.md) · [receipt.md](receipt.md) · [interpret.md](interpret.md).

## CCC inside the implement step

| Iteration step | File | CCC |
|---|---|---|
| Plan | `iter-NN/plan.md` | becomes CCC `task.md` |
| Implement | `iter-NN/ccc/artifacts/` | plan, plan review, code, code review |
| Run and receipt | `iter-NN/receipt.md` | after CCC, launch the card and record job IDs and numbers |
| Interpret | `iter-NN/interpret.md` | not a CCC stage |

Freeze hypothesis, data split, metric, threshold and budget before CCC; CCC does not revise them. Before starting, run `python3 rloop/focus/planner-loop/check_plan.py <plan.md>`; start CCC only on exit 0. At plan review, S1–S4 must contain concrete frozen requirements and evidence paths, with no placeholders. At code review, each requires code evidence at file:line in the diff or relevant unchanged code the planner pastes into the CCC task. An unmet or unverifiable S requirement at its applicable stage is a [major] finding. These checks cover the named manifest and split, evaluation frozen before results open, held-out access only for the final score, and outputs the receipt can cite.

Write the receipt only after a `review_vN.md` approving verdict whose raw transcript has no open S1–S4 finding. Otherwise use `Decision needed: CCC science check <Sn> open` in the notebook. CCC `.done` sentinels and the notebook's `Decision needed:` line are the decision bell. The shipped pairing is `claude-codex`; `claude-claude` currently uses one model for both roles.
