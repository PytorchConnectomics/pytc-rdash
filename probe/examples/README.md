# Historical example — NISB connectomics decoding

For the executable, synthetic evaluator regression connection, see
[nisb/README.md](nisb/README.md). That example checks real evaluator behavior;
the benchmark values below remain historical and are not reproduced by its tests.

`probe` was extracted from the NISB research workspace. This table preserves the
historical case behind the method. Numbers and lesson counts describe the
extraction-era source, not a current benchmark report or v2 defaults.

| Concept | Historical NISB instance |
|---|---|
| Objective | NERL on the seed101 frozen benchmark |
| Exact evaluator shortcut | Node-LUT scoring sampled predictions at about 791k skeleton nodes and reproduced the corresponding full-decode NERL, such as 0.601431, at less than 1% cost |
| Tracks | False merge, false split, and coverage fill, with project-specific measured current values and oracle bounds |
| Oracle probes | Branch-merge oracle 0.772 and fill oracle 0.685; bounds rather than realized results |
| Preregistration and lessons | About 14 lessons at extraction, relating hypotheses and gate/stop criteria to recorded verdicts |
| Historical invariants | Claims such as a frozen-label-map ceiling, carrying the original project's assumptions and scope |
| Implementation handoff | Training-stage changes implemented in the owning code repository and evaluated against the project's objective |

Active memory lives in
[projects/nisb-base-26/](../../projects/nisb-base-26/), including its
[state](../../projects/nisb-base-26/state.yaml),
[local loop](../../projects/nisb-base-26/loop.md), and
[lessons](../../projects/nisb-base-26/lessons/lessons.md).
The [project spec](../../projects/nisb-base-26/spec.md) identifies the owning
code repository and runtime/evidence locations. Read the current project files
for its current results and adopted rules; this method update does not adopt
v2 on that project's behalf or rewrite its historical experiments.

## Applying the lesson in v2

The reusable insight is to use evidence that is appropriate and economical for
the decision. NISB's exact shortcut is one instance. A microscopy project might
instead configure an empirical pilot, a diagnostic check, or an authorized
bounded direct experiment, with explicit validity and continuation rules. The
accepted [v2 protocol](../protocol/PROBE_PROTOCOL.md) does not require every gate
to reproduce the final metric exactly or cost less than 1%.

Similarly, preserve the evidence behind an old invariant without promoting it
into an unconditional rule for a different dataset, representation, or imaging
setup. A new constraint needs bounded applicability, reopening conditions, and
review appropriate to its consequence. Distinguish successful engineering,
valid scientific negatives, and invalid/inconclusive evidence when adapting the
method. [Method reviews](../reviews/README.md) record proposals and their adoption.

The source workspace originated at `dev/nisb/` in PyTorch-Connectomics, and its
memory moved through `pytc-agent` / `dw-proj` into `dw-research`. Those historical
locations do not imply that runtime artifacts were moved with the method.
