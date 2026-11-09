# Improving the research method

Read this directory when reviewing or changing the shared method. Research
sessions use the adopted [protocol](../protocol/PROBE_PROTOCOL.md) and their
project's settings; they do not load this review archive by default.

The method improves through **project evidence → proposed change → scoped trial
when needed → review → accepted protocol revision**. A review records reasoning
and a decision. The accepted procedure has one home in `probe/protocol/`.

## Ownership

| Material | Home |
|---|---|
| Accepted scientific procedure and its reusable templates/tools | `probe/protocol/`, `probe/templates/`, `probe/scripts/` |
| Method observations, proposals, trial findings, and adoption decisions | This directory, linking original evidence |
| Scientific results, experiment decisions, local method settings, and project retrospectives | `projects/<project>/` |
| Personal allocation, dispatch, work in progress, and human review capacity | The dw-os planner's `workflow/` and `ops/` |
| Outside advice and source synthesis | `dw-kb`, with provenance |

Keep mixed historical records intact and link their relevant sections. Extract
the reusable proposal with its scope and limitations; a dated recommendation or
interview opinion does not become an instruction merely by being filed here.

## A review's minimum record

- **Observation and evidence:** what happened, where, and when; distinguish a
  measured failure from an interpretation or an unimplemented suggestion.
- **Proposed change and scope:** the specific method decision to change, who it
  affects, alternatives, and how it could make research worse.
- **Validation:** what would demonstrate improvement or invalidate the proposal;
  use a bounded trial for uncertain behavioral claims. A documentation correction
  can be checked directly without launching a scientific experiment.
- **Decision:** `proposed`, `trial`, `adopted`, `rejected`, or `superseded`, with
  date, authority, rationale, and a link to the relevant protocol revision.
- **Adoption:** which projects explicitly adopt the revision, how existing work
  remains reproducible, and what would trigger reconsideration.

Successful task completion does not authorize a worker to change the shared
method for every project. Within the user's authority, update the canonical
protocol, entry point, affected templates, and adapters together. Record the
decision here; projects adopt the revision explicitly in their existing method
settings. Preserve prior preregistrations and results.

## Records

| Record | Status and use |
|---|---|
| [June 2026 research-agent review](2026-06-26-research-agent-review.md) | Historical evidence and proposals; its deployment claims describe that session |
| [September 2026 method boundary and protocol revision](2026-09-09-method-boundary.md) | Adopted design changes for protocol v2; project adoption remains explicit |
| [Executable checks and first evaluator connection](2026-09-15-executable-checks.md) | Read-only reference inspection, behavior fixtures, and a synthetic NERL evaluator regression connection; no scientific-method migration |
| [Instruction chain A/B](2026-11-08-instruction-chain-ab.md) | Trial: one-screen workbench `CLAUDE.md` of invariants vs. the full procedural chain, judged on two receipts of one frozen plan; protocol unchanged |

Related historical context: [June NISB retrospective](../../projects/nisb-base-26/retrospectives/2026-06-26/README.md).
