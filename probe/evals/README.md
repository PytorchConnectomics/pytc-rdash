# Research-agent behavior cases

[cases.json](cases.json) contains small, fictional offline cases for comparing
research-agent behavior. The first four preserve the situations in the
[September 9 trial](../reviews/2026-09-09-method-boundary.md#validation-and-limits);
the remaining cases challenge evidence identity and unsupported completion.
They are engineering evaluation inputs, not scientific project evidence.

## Run a comparison

Give a fresh agent the selected protocol snapshot and each case's `task` and
`observations`. Keep `expected` and `forbidden` out of its input. Ask it for
the next action, outcome dimensions where applicable, supporting evidence, and
any missing decision. No actual project, remote tool, or experiment is needed.

An independent reviewer compares the response and any observed tool actions
with all expected and forbidden behaviors. Record `pass`, `fail`, or
`inconclusive` per case with specific evidence. An intended tool action is not
proof it ran; a well-worded response alone does not validate runtime enforcement.
Record model, prompt/protocol hashes, settings, date, and cost when available.

Use the same cases, input context, and budgets when comparing changes. Keep
separate held-out variations so tuning does not reduce to memorizing this bank.
The bank is deliberately small and is not a comprehensive autonomy score.

For deterministic readiness-check tests, run from `research/`:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s probe/tests -v
```

For an actual evaluator connection, use the
[NISB CPU regression example](../examples/nisb/README.md). Agent behavior,
evaluator correctness on fixtures, and scientific performance on real data are
separate claims and require separate evidence.

## Failure-replay tasks

`failure-replay/<id>/` holds replayable engine-behavior tasks absorbed from the
former root `evals/` of `dw-os` on 2026-11-08 (design review
`workflow/reviews/2026-11-08-superagent-design.md` there). Each task tests
whether an agent picks the safe action for a real failure, from its log alone.

```
failure-replay/<id>/
  task.md         the packet the agent receives (all it may see)
  meta.yaml       split (public|private), family, expert_minutes, source
  expected.json   reference answer (agents never see it)
  verify.sh       exit 0 if the agent's answer.json passes
```

Run one task: give the agent `task.md`, collect its `answer.json`, then
`bash failure-replay/<id>/verify.sh answer.json`. The shared checker is
`verify_failure_replay.py`.

Answer enums: `cause` ∈ `empty_path_at_submit`, `missing_permission`,
`nccl_p2p_hang`, `oom`, `disk_full`, `data_missing`, `code_bug`, `unknown`;
`action` ∈ `retry`, `retry_with_fix`, `pause_and_notify`, `mark_failed`;
`notify` is `true` when DW should hear about it even if the agent can continue.

Growing the bank: every run that ends in `needs-you` is a candidate task, with
DW's fix as the reference answer; keep about a third of tasks `private`. Like
`cases.json`, these are engineering evaluation inputs, not scientific evidence,
and they are not the evaluator of any project's science.

**Ownership.** DW owns everything under `probe/evals/`. A self-improvement or
research loop may run these cases and must never edit tasks, expected answers,
verifiers, or recorded scores; see `standards.md`, *Evaluation bank*.
