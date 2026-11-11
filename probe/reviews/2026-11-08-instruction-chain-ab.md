# Instruction chain A/B: invariants only vs. the full procedural chain

**Status:** `trial` (opened 2026-11-08 by the operator on DW's instruction; DW decides adoption).
**Scope:** the workbench-level `CLAUDE.md` of `pytc-jam` and `pytc-jam-msi`, and what a probe or
planner-loop session reads before its first action. The protocol itself is not changed by this record.

## Observation

Measured on 2026-11-08 (`wc -w`), a probe step on `pytc-jam/projects/nisb-base-26` started from a
`dw-os` checkout reads 12 files and 11,446 words (about 15k tokens) before acting:

| File | Words |
|---|---:|
| `dw-os/CLAUDE.md` (auto-loaded as an ancestor) | 1,949 |
| `dw-os/SOUL.md` (read on instruction) | 2,294 |
| `research/CLAUDE.md` | 156 |
| `pytc-jam/CLAUDE.md` | 273 |
| `projects/nisb-base-26/CLAUDE.md` | 554 |
| `projects/nisb-base-26/spec.md` | 370 |
| `projects/nisb-base-26/loop.md` | 972 |
| `pytc-jam/skills/rdash/SKILL.md` | 389 |
| `rdash/probe/SKILL.md` | 416 |
| `rdash/probe/protocol/PROBE_PROTOCOL.md` | 2,227 |
| `rdash/standards.md` | 1,283 |
| `rdash/rloop/focus/planner-loop/README.md` | 563 |

A student's session started from a bare `pytc-jam` clone skips the first two rows (7,203 words
fewer), so DW's own sessions carry the longest chain. Most of the remainder is procedure (how to
lock, how to launch, how to write a card), restated in several files. The invariants that must
never be lost fit on one screen: research integrity, the BC/Mindspan boundary, frozen evaluation,
one writer per card, one GPU host per project, PRs only.

## Source and claim

DHH, Lex Fridman #501 (2026-08-26), around 0:56: the Claude Code system prompt shrank by roughly
80% because over-prescription made the agent worse ("damaged by overly prescriptive humans").
This is a vendor anecdote relayed by a practitioner, not a measurement on our tasks; hence a trial,
not an adoption. Converging local evidence: `kb/news/_inbox.md` row 20 (keep `CLAUDE.md` to
repeated failure modes) and the 2026-11-06 shift note.

## Proposed change

Each workbench `CLAUDE.md` becomes one screen of invariants plus pointers (done on the
`dhh-2026-11-08` branches of `pytc-jam` and `pytc-jam-msi`; the previous texts are at
`pytc-jam@4b1ad86` and `pytc-jam-msi@5bfefb6`). Procedure stays where it is executed: the
`rdash` skills, the planner-loop templates, `docs/contributing.md`. Nothing in `probe/protocol/`
changes.

## Validation (the trial)

Two arms, one frozen plan, same implementer model, same budget:

- **Arm A, full chain:** the workbench checked out at the pre-change revision above.
- **Arm B, invariants only:** the workbench at the `dhh-2026-11-08` revision.

Procedure: take the next frozen `plan.md` in either workbench (the plan must pass
`rloop/focus/planner-loop/check_plan.py`). Run the implement step once per arm in a fresh session
from a bare workbench clone (not from `dw-os`), writing `receipt-A.md` and `receipt-B.md`. A
model from a different vendor reviews both receipts against the plan and answers three questions
with evidence lines: did what ran match the plan; what was claimed without a file; which of the
six invariants, if any, was violated. Record both reviews under the notebook's `iter-NN/`.

Decision rule, fixed before the run: adopt arm B if its receipt has no invariant violation and no
more unsupported claims than arm A. Any invariant violation in arm B rejects the change regardless
of the rest. One pair is a smoke test, not proof; the result is recorded as such.

## What could make research worse

A shorter chain can drop a rule an agent was silently relying on (lock discipline, the
`FILL:` convention, results roots). The trial's third question exists to catch that. If a
dropped rule shows up as a violation, it is an invariant and goes back on the one screen; if it
never shows up, it was procedure and belongs with the command that needs it.

## Decision

Pending DW. Adoption means: keep the short `CLAUDE.md` files, record the two receipts and reviews
here, and move any rediscovered invariant onto the screen.
