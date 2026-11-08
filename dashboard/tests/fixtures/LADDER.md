# The P0 ladder — the overall view

*One rung a month, a whole P0 mouse brain by 2027-03. This table is the team's gantt chart: a
rung is a deliverable, and a month passes only when all three gates are met. Numbers come from
the files named in the last column, never from this table. Proposal rows are DW's dated proposals,
not agreed targets, until a decision entry says otherwise.*

## Gates

| Gate | Question | Recorded in |
|---|---|---|
| **G1 — it ran** | the rung's volume is segmented end to end | the card's job receipt |
| **G2 — quality** | axon nERL at the frozen threshold, GT-backed, per volume, with split and merge reported separately; errors per mm beside the percentage | the evaluation card's result file |
| **G3 — cost** | proofreader-minutes per mm of reconstructed neurite to reach G2 | the CAVE queue record |

Gate tags: `[met]`, `[open]`, and `[failed]` record observed gate state; change a tag only with evidence in the file named in the same row. Untagged cells are targets.

G1 is plumbing. G2 without G3 cannot support the flat-cost claim; G3 without G2 is meaningless.

## Rungs

| Month | Rung | Data | G1 | G2 | G3 | Notebook / question | Status |
|---|---|---|---|---|---|---|---|
| 2026-09 | 20 µm | 10 GB | [met] ran | [open] not logged | — | — | ran, unmeasured |
| 2026-10 | 20 µm | 10 GB | [met] ran | [open] baseline only: axon nERL 0.769 / 0.734 (32x_1), 0.618 / 0.709 (32x_2), job 807 | — | `example-liconn-20um-26` Q-011, `example-proofreading-26` F-005 | baseline logged, bar not met |
| 2026-11 | 20 µm iteration | 10 GB | — | target 99 % axon nERL (waypoint; A+ is 99.8 %) | — | F-005 | iter-01 closed negative on dev |
| 2026-11 | 50 µm | 100 GB | [met] ran (36 / 63 nm whole-volume decode) | [open] no held-out GT yet | — | `example-liconn-50um-26` Q-011, F-006 | plumbing only |
| 2026-11 | 100 µm | 1 TB | — | same bar | cost/mm logged: the curve's left anchor | — | proposal 10/23 |
| 2026-12 | 250 µm | 15 TB | — | same bar | within 1.5× of the anchor | — | proposal 10/23 |
| 2027-01 | 500 µm | 100 TB | — | same bar | within 2× of the anchor | — | proposal 10/23 |
| 2027-02 | 1 mm | 1 PB | — | same bar | within 2× of the anchor | — | proposal 10/23; where the flat-cost claim passes or fails |
| 2027-03 | 5 mm | 100 PB | — | same bar | reported | — | delivery |

**The bar does not move.** If the threshold or the denominator changes at any rung, every earlier
number stops being comparable and is re-scored.

## How the loop changes as the rungs grow

Every rung runs the same loop: data + proofreading → model → evaluation → data. What changes is
which leg a human can still do:

| Leg | Stops working at | Replaced by |
|---|---|---|
| complete proofreading | ~50–100 µm | sampled audit |
| real training labels | 50 µm onward | simulated training data |
| human evaluation | ~250 µm – 1 mm | a GT-free quality signal |

Each replacement has to exist one rung before it is needed, because the rung that needs it cannot
test it. That is what the questions under each rung are for.

## Weekly and daily

- **Weekly:** each notebook's `Next` list is the todo. Thursday review reads the standing report
  blocks, not this table.
- **Daily:** the board's attention list (decisions owed, jobs failed, receipts missing). If a
  notebook's block says `Decision needed: none`, nobody is waiting on you.
