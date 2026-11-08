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
