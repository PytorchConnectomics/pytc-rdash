---
id: PROJECT-SLUG
title: Research question
project: PROJECT
track: model
stage: idea
state: working
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# Research question

## Question and rationale

What is uncertain, why does it matter, and what motivates this idea?

## Proposed hypothesis

State a falsifiable claim and its mechanism. Label alternatives explicitly.

## Proposed probe

Prediction, cheapest discriminating experiment, baseline, evaluation criteria,
and proposed budget. Once adopted, replace the working definition with a link
to the canonical project probe record; retain dated proposal history.

## Acceptance

- [ ] Record the result and its scope against the stated baseline.
- [ ] Record limitations and claims this probe must not make.

Only a person settles an item, with a trailing ` — evidence: <references>` and
an appended dated discussion entry. Optional frontmatter `verdict` is `open`,
`met`, `failed`, or `inconclusive`; record the human rationale in discussion.
Job completion and artifact presence never establish acceptance or verdict.

## Connections

- Literature:
- Project record:
- Probes and run IDs:
- Agent sessions (source, ID/link, date, short summary):
- Evidence (source, observation date, validity):

## Ideas and discussion

- YYYY-MM-DD — Author/source: original idea, question, or proposed revision.

## Next decision

What evidence or human input would determine the next step?

## Needs you

Present only while frontmatter `state: needs-you`. One to three numbered options and
a `Recommendation:` line; the board treats anything else as a malformed bell. A
session stops in a waiting state only by writing this block; otherwise `state` is
`working`, `paused` (parked by a person) or `done`.

1. <option, one line, with what it costs>
2. <option>
Recommendation: <which one and why, one line>

## Optional live measurements

Add `results` inside the existing `probe-status` JSON object, for example:

```json
"results": [{"name": "val NERL", "path": "results/metric.json", "key": "nerl",
             "baseline": 0.604428, "direction": "higher",
             "source": "contract baseline reference"}]
```

Copy the actual contract baseline; omit it if no baseline is declared. The
example is illustrative, not a measurement for a new card. The board reads
JSON data only (at most 1 MiB), never generators. Missing and unreadable results
are not zero. Relative paths use the project's results/ or logs/ root; external
content requires operator roots documented in dashboard/README.md. Generated
`radd-status` blocks remain handoff snapshots; the board collapses and age-labels
them below the live artifact table. Refresh the snapshot with `--write` for a
handoff, not to refresh the board. Health and session attach remain deferred.
