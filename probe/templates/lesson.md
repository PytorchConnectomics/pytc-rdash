---
# Fill the identifying fields before execution. The source method must be resolvable.
run_id: null
lever_id: null
protocol_version: "2.0"
protocol_source_revision_or_snapshot: null
phase: preregistered  # preregistered | gated | running | review | closed
execution_status: pending  # pending | completed | failed
measurement_status: pending  # pending | valid | invalid
scientific_verdict: pending  # pending | positive | negative | inconclusive | not_evaluated
---

# Experiment — title

## Preregistration

- **Question / hypothesis:** What uncertainty does this test address, and which mechanism or alternative is being tested?
- **Expected observation:** A justified effect/range or discriminating observation; write unknown when it is unknown.
- **Evaluation snapshot:** Data/sample definition and version, split/controls, baseline artifact, evaluator and code/configuration identities, applicable repetitions and uncertainty. Link permitted evidence locations. State what may be tuned and what remains reserved for final evaluation where relevant.
- **Engineering acceptance:** Checks proving the intended implementation, data handling, and evaluator are correct, independent of whether the hypothesis wins.
- **Scientific decision rules:** Which valid observations support the hypothesis, count as a scoped negative, or leave it inconclusive?
- **Gate settings / continuation:** Gate type, configuration, validity/calibration evidence, cost and units, what a failure implies, and what each outcome permits. If no preliminary gate applies, record why direct execution is appropriate and authorized.
- **Task / authority:** Source of the authorized scope, allowed actions, execution host/workspace, and landing/review permissions.
- **Budget / operational stops:** Applicable task limits, earlier consumption and remaining budget as known, expected cost, retry limits, and conditions to stop or return a decision. Include relevant compute, instrument/sample, and human time; do not invent quantities.

Keep this prospective record unchanged after execution starts. Append any correction or prospective amendment with its date and rationale before work using the changed settings.

## Execution and gate evidence

Commands/configuration and artifact references; job/process identity when applicable; engineering checks and gate observations. Record gate outcome and measurement validity separately. A gate pass permits only its defined next step.

## Verdict

- **Execution:** Completed or failed, with the actual checks and any partial evidence.
- **Measurement validity:** Valid or invalid, with the check supporting that assessment.
- **Scientific verdict:** Positive, negative, inconclusive, or not evaluated; compare valid observations with the preregistered rules and state the scope/limitations.
- **Resources:** Known consumption and remaining task budget; label estimates.
- **State change:** Which current result, active-run entry, or project question changes? Link the landed update or proposed patch.
- **Next action / decision:** What should the researcher or planner attend to, and why?

## Constraint proposal, when warranted

Record the proposed constraint, linked evidence, applicability/assumptions, limitations, reopening conditions, and independent check required or completed. Keep an unverified broad exclusion proposed; one failed run does not establish a permanent class-level rule. The accepted constraint has one canonical entry in project state, linked to this reasoning.
