# F-NNN iter-NN — plan

Author: Fable 5.1 · Date: YYYY-MM-DD · Status: draft | frozen (Opus started YYYY-MM-DD HH:MM)
Notebook: `research/projects/<project>/focus/F-NNN.md` · Previous: `iter-MM/interpret.md` or none

## Context for the implementer
<!-- 3–6 lines. What Opus needs to know and would otherwise not: goal, current best, why this iteration. -->

## Hypothesis
<!-- One sentence. What should change, and why. -->

## Change
<!-- Exactly one change. Files/functions to touch, or "new script <path>". -->

## Frozen evaluation
- Data: <manifest path; dev vs held-out IDs>
- Metric: <name, convention, threshold; e.g. axon completeness, nERL at t=…>
- Baseline: <run / file it is compared against>
- Confidence thresholds, queue sizes and other knobs: <fixed values; never tuned on held-out>

## Run
- Host / env: <e.g. cajal, conda env>
- Launch: <rdash card to create or reuse>
- Budget: <GPU-hours, wall time, max attempts>

## Deliverable
<!-- Exact output files Opus must produce, with paths. -->

## Stop rule
<!-- When Opus stops and writes the receipt even without a success. -->

## Out of scope
<!-- What Opus must not do in this iteration. -->

## Review checks

S1 Data: read <manifest path> and split <dev IDs>, with no other data path. Evidence path: <code path to inspect>.
S2 Freeze: write evaluation config <path> before opening results. Evidence path: <code path to inspect>.
S3 Held-out: read <held-out IDs> only once, through <final-score entry point>. Evidence path: <code path to inspect>.
S4 Receipt: write outputs at <paths> for receipt.md to cite. Evidence path: <code path to inspect>.

At plan review, each requirement must be frozen with concrete manifest, split, config and output paths, no placeholders, and an evidence path the code must show. At code review, verify each requirement with code evidence at file:line in the diff or relevant unchanged code pasted by the planner into the CCC task. An unmet or unverifiable requirement at its applicable stage is a [major] finding and prevents approval.
