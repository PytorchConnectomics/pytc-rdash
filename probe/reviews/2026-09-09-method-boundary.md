# Method boundary and protocol v2 — 2026-09-09

**Decision:** adopted for the shared method, authorized by Donglai's request to
implement the proposed boundary and corrections on 2026-09-09. This records a
procedure and documentation revision, not a scientific result or an automatic
upgrade of existing projects.

## Evidence and problem

The former `research/meta/` mixed project evidence, dated priorities, reusable
method advice, and interview synthesis. Its blanket historical-NISB label hid
that distinction. The old protocol also repeated general rules in project
templates and in the KB preregistration skill.

- The [June process retrospective](../../projects/nisb-base-26/retrospectives/2026-06-26/research_process.md)
  records repeated diagnosis, silent execution failures, and fragmented work.
  Its measurements and causal interpretations are historical claims, not newly
  verified observations.
- The [June agent review](2026-06-26-research-agent-review.md) distinguishes
  proposed mechanisms from implemented and unwired ones. Preserve that
  distinction when extracting method changes.
- The [June 27 BC plan](../../../pm/bc/archive/2026-06-27-research-plan.md)
  ([standalone-checkout link](https://github.com/donglaiw/dw-pm/blob/main/bc/archive/2026-06-27-research-plan.md))
  uses a short training gate costing up to 20% of a full run. That historical
  example does not fit a universal exact, less-than-1% surrogate requirement.
- The pre-v2 protocol used the scientific kill criterion as coding acceptance
  and treated gate failure as a negative result. Those rules can reward a
  desired result or prune a hypothesis after an invalid measurement.

The pre-v2 procedure is preserved in Git at
`b3e39c09d4a1ff43fbdd097465ac6af1bd8bb6f8:probe/protocol/PROBE_PROTOCOL.md`.

## Accepted changes

| Decision | Intended effect |
|---|---|
| `probe/protocol/` owns accepted procedure; `probe/reviews/` owns method-change evidence and decisions | Reviews remain discoverable without becoming default instructions |
| Project method settings identify the adopted revision, local evaluator/gates, and explicit deviations | General rules have one maintained owner; old work keeps its context |
| Gate cost, fidelity, and escalation conditions are justified per project | The gate answers a relevant decision without requiring a fictitious exact surrogate |
| Engineering acceptance, scientific outcomes, and resource stop conditions are separate | A correct implementation may yield a useful negative; a broken run yields no scientific verdict |
| Negative findings retain tested scope, evidence, uncertainty, and reopening conditions | A failed instance does not silently become a permanent class-wide prohibition |
| Selection estimates are advisory and use only meaningful, available quantities | Unknown ceilings or probabilities remain unknown |
| Existing authorization and project-specific adoption govern execution | A revised shared skill does not silently change existing experiments or budgets |

The [protocol](../protocol/PROBE_PROTOCOL.md) is the maintained procedure. This
table records why its revision was adopted; it is not a second operator checklist.

## Validation and limits

Validation passed for the probe skill and both KB adapters, template YAML,
bootstrap initialization and preservation of existing method/state/lessons, and
shell syntax. All five relocated source bodies match their original hashes.
Current local reference checks exclude the explicitly preserved historical
bodies, whose old link mappings are supplied in their provenance banners.

A fresh independent agent applied a protocol/skill snapshot to four
offline synthetic cases:

| Case | Observed behavior |
|---|---|
| Correct implementation, valid measured decline | Closed as a scoped negative; kept the prior best result and added no class-wide exclusion |
| Exit code zero, corrupt input and all-zero output, exhausted budget | Reported failed execution/invalid measurement and `not_evaluated`; proposed no retry or scientific rejection |
| Authorized 20% instrument-time pilot, approximate proxy, multiple objectives | Accepted the pilot design within its existing authority, required the actual predefined checks before spending, and did not authorize a full experiment or invent a ceiling |
| Existing project pinned to pre-v2, running job without a sentinel | Read the pinned source, preserved its local gate/adoption, and proposed no duplicate launch or state change |

These checks validate document structure and behavior on the supplied cases.
They establish no experiment-performance improvement, deployed hook, scheduled
supervisor, or automatic runtime enforcement.

Existing projects keep their current local method and scientific state. New
projects may adopt v2; migrating an existing project requires an explicit
recorded choice. Revisit these rules if trials show gates wrongly reject useful
work, bookkeeping displaces evidence gathering, or operators cannot distinguish
execution failure from scientific findings.
