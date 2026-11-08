# Probe, rloop, and focused research students

Status: scoped coordination implementation; no change to accepted Probe 2.0 or
any project's pinned adoption. Requested by DW on 2026-10-17.

## Diagnosis

Probe is the scientific method and contract layer. It specifies preregistration,
engineering acceptance, measurement validity, outcome classification, and landing.
Its helpers inspect contracts and launch individual agent steps; they do not
implement a persistent scheduler, budget manager, or notification service.

rloop supplies runtime machinery: task selection, bounded workers, durable
checkpoints/handoffs, GPU submission limits, evidence receipts and briefs. Its
focus lane already freezes Action and optional evaluation contracts. The October
17 deployment review records that F-001–003 still lack explicit frozen evaluator
bindings. Notebook activity is therefore not equivalent to verified progress.

Both describe selecting work, executing it, and recording outcomes. The risk is
that rloop's small-step protocol becomes a competing definition of scientific
success, while Probe remains unused prose. The remedy is an adapter: execute the
project's current contract and preserve its adopted method and evaluator identity.
Do not merge the directories or copy the generic protocol into every worker prompt.

## Changes in this scoped trial

The [student-review adapter](../../rloop/focus/REVIEWS.md) derives a daily agenda
from canonical notebooks and runtime receipts. Each student has a reporting
cadence, an existing concrete Next action, and an explicit human-feedback record.
The Mac mini owns communication; hebb owns research execution. No new scientific
thresholds, project adoption, GPU authorization, or automatic feedback acceptance
are introduced by a deadline or Slack message.

## Next scientific improvement

Bind one prospective experiment at a time to its existing Probe-compatible
acceptance and evaluator record. Start with F-002 once stub/oracle agreement and
submission authority are resolved. Freeze the real data split, baseline,
evaluator revision, candidate identity and resource budget before evaluation.
Do not fit the existing paired-mean evaluator schema to AUROC by relabeling fields;
add a domain-appropriate validator with test evidence when the contract needs it.

For F-001 preserve matched update and GPU-hour comparisons plus confirmation.
For F-003 preserve the joint thin-break, merge-harm and NERL criteria. Each needs
its own measurement-validity evidence. A missing adoption revision is recorded
as a gap, not silently replaced by the latest protocol.

## Framework lessons worth adopting

- [autoresearch](https://github.com/karpathy/autoresearch/blob/master/program.md):
  immutable evaluator, explicit baseline and candidate disposition. Its five-minute
  training budget is not a default for these research questions.
- [AIDE](https://github.com/WecoAI/aideml/blob/main/aide/agent.py): preserve candidate
  ancestry and distinguish draft, debug and improvement branches. Avoid repeating
  abandoned code without evidence of a changed assumption.
- [ShinkaEvolve](https://github.com/SakanaAI/ShinkaEvolve): durable evaluation and
  recovery bookkeeping; retain our existing fsubmit resource controls.
- [AI Scientist-v2](https://arxiv.org/html/2504.08066v1): staged feasibility,
  experimental agenda and ablations. Model-written conclusions still need checks.
- [Darwin Gödel Machine](https://arxiv.org/html/2505.22954v1): evaluate changes to the
  agent separately from changes to the scientific candidate. Use held-out workflow
  tasks; never let the self-improvement loop rewrite its own success criteria.

These are design precedents from the preceding source survey, not claims that
those systems have demonstrated productivity on our microscopy problems.

## Evaluate the trial

After five reports, inspect delivered artifacts, verified scientific outcomes,
valid negatives, unresolved blockers, repeated actions, time awaiting input,
and whether human replies actually landed. Count publications, deliveries,
human reviews and applied decisions separately. Report missing cost data as
unknown. Keep this review as evidence; any generic protocol revision requires
explicit adoption and preservation of earlier experiments.
