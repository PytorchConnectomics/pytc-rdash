---
name: pr-review
description: Review a pull request to a pytc-jam workbench or to rdash and write exactly one recommendation (merge, close, needs-change) with evidence, so the maintainer makes a decision instead of reading the diff. Use when asked to review a PR, triage open PRs, or when a PR-review workflow invokes it.
---
# pr-review — one recommendation per PR, evidence attached

The maintainer's job on this repo is the merge decision. Your job is everything before it:
run the checks, read the diff against the invariants, verify every claim against a file, and
reduce it to one line the maintainer can act on. You never merge, never push to the PR branch,
and never rewrite the contribution; you recommend.

## Procedure

1. **Read the target's one screen.** The workbench `CLAUDE.md` (or `rdash/CLAUDE.md` plus
   `standards.md` for a tooling PR). Those are the invariants you review against.
2. **Run the checks** on the PR head, exactly as `extend-workbench` lists them (`tests/`,
   `lint`, `check_readiness.py` if a contract fence changed, `check_plan.py` if a plan was added;
   for `rdash`: `python3 -m unittest discover -s dashboard/tests -t .` and the probe tests).
   Paste the final line of each as evidence. A check you could not run is reported as not run,
   never as passed.
3. **Read the diff for shape, not style.** For each changed file ask: is it in the place the
   table in `extend-workbench` says; does it copy tooling into the workbench; does it edit
   another owner's card; does it cross the BC/Mindspan boundary; does it carry a credential,
   a signed link or data.
4. **Verify claims.** Every number, path or "verified" in the PR body or in the files must point
   at a file that exists on the PR head. Quote the line you checked. A claim with no file is a
   finding, not a nit.
5. **Scientific shape, not scientific truth.** Confirm the card states hypothesis, split,
   metric, threshold and budget before results; confirm no verdict or acceptance item was
   settled by the PR itself. Do not judge whether the hypothesis is good: that is the
   notebook's and the maintainer's job.

## Output: exactly this

```text
Recommendation: merge | close | needs-change
Why (one line): ...
Checks: tests <last line> · lint <last line> · readiness <last line or "n/a">
Findings (each with file:line or "PR body"):
  [major] ...   # blocks merge: invariant violation, unverifiable claim, boundary crossing
  [minor] ...   # fix before or after merge, maintainer's call
Not reviewed: ...   # what you did not run or could not see
```

`merge` requires zero [major] findings and every check run. `close` is for a PR that
duplicates an existing card or project, copies tooling, or cannot be made to pass without
being a different PR; say which. Everything else is `needs-change` with the list.

## Posting

With `gh` available: `gh pr comment <n> --body-file <file>`. Without it, write the block into
the PR body or hand it to the maintainer. One comment per review round; do not re-post the same
finding on each push.

## Boundaries

- `pytc-jam-msi` PRs are reviewed only by a model inside the Mindspan perimeter (local, or a
  session DW runs); no cloud review workflow is installed there, by rule.
- You have no authority to merge, close, relabel, or request changes through the forge; the
  recommendation line is the whole output.
- An agent-written PR gets the same review as a human's and the same `close` when it earns it.
