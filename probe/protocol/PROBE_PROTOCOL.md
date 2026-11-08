# Probe protocol 2.0

**Accepted method revision: 2.0 · 2026-09-09.** This is the canonical generic procedure for new probe projects. Adoption is versioned; installing this skill does not migrate existing experiments. Method rationale and proposals are indexed in [reviews](../reviews/README.md).

Probe coordinates an empirical question, an authorized experiment, and a recorded conclusion. Its scripts scaffold files and invoke individual agent steps. Selection, validity checks, budget accounting, state transitions, and resumption are coordinator responsibilities; this document does not describe an implemented supervisor.

## 1. Adoption and authority

Read the project spec, `loop.md` or equivalent adoption record, current scientific state, and relevant lessons. Resolve the procedure in this order:

1. **Pinned adoption:** load `probe/protocol/PROBE_PROTOCOL.md` from the recorded dw-research Git revision, or use the recorded immutable protocol snapshot. The checked-out latest file is not a substitute. Project settings and explicit adaptations accompany that revision.
2. **Existing unversioned project:** preserve its recorded local/legacy procedure. Use its source history when needed; the pre-v2 generic protocol is available at dw-research revision `b3e39c09d4a1ff43fbdd097465ac6af1bd8bb6f8`, path `probe/protocol/PROBE_PROTOCOL.md`. Do not infer v2 adoption from the repository move, a missing field, or a new skill installation.
3. **New bootstrap:** use 2.0. Record method name/version, adoption authority/date, and the source Git revision. If adopting an uncommitted method, preserve an immutable content-identified snapshot instead of pretending a commit contains it.

If a required pinned source cannot be recovered, report that missing dependency before work relying on its rules; unrelated read-only inspection can continue. To adopt another revision, record the authorized change and its impact on future runs. Preserve earlier preregistrations, verdicts, and evaluation settings. Resolve conflicts between the adopted generic procedure and a local rule explicitly; do not quietly replace either.

The task contract or user instruction supplies the research scope, allowed actions, execution host/workspace, resource and time budget, review conditions, and stopping conditions. Carry that authority across sessions and count earlier attempts against the same budget. Existing permission to select, implement, execute, review, or land covers those steps within its limits: **do not ask again merely because a checklist reaches an approval point**. Ask only for a consequential unresolved decision or a change beyond the granted authority. A read-only assignment stays read-only; propose a patch when landing is not authorized. `auto` changes interaction frequency, not authority.

The planner owns portfolio priorities and allocation. Research agents return scientific evidence and proposed next work without silently enlarging that allocation.

## 2. The experiment contract

Before spending on an experiment, write the prospective record using [lesson.md](../templates/lesson.md), or equivalent existing project fields. Use a unique run ID for each preregistered experiment; one lever may have multiple runs.

The record identifies:

- **Question and hypothesis:** which uncertainty or objective this test serves; the mechanism being tested. An expected effect may be a justified range or explicitly unknown.
- **Evaluation:** one or several measured properties, or a qualitative observation that discriminates the hypotheses. Identify the fixed dataset/version/split or sample definition, evaluator/version, baseline/control artifacts, applicable seeds/repeats, and measurement uncertainty. Link the configuration/manifest and permitted code/artifact references needed to audit it. Record what may be tuned and what evidence is reserved for final evaluation when relevant.
- **Engineering acceptance:** observable checks that establish the intended code, configuration, data handling, and evaluator were implemented correctly. These checks do not require the hypothesis to win.
- **Scientific decision rules:** what valid observations support, fail to support, or leave the hypothesis unresolved, under which settings. Separate these from operational abort conditions.
- **Gate and continuation:** which project gate applies, what its outcome allows, and any authorized decision to proceed without a preliminary gate.
- **Authority and resources:** the governing task/authorization reference, allowed changes, remaining budget accounting for prior work, and applicable stop/review conditions. Do not invent numeric limits or claim measured consumption when only an estimate exists.

Keep the preregistered record fixed once execution begins. Correct transcription errors transparently; append prospective amendments before any subsequent work that depends on a changed hypothesis, configuration, or evaluation. Do not rewrite the original prediction or decision threshold after seeing the result.

## 3. Gates and experiment selection

### Project-configured gates

Choose a gate that can inform this project's next decision. Record its cost estimate and units, why that expenditure is justified, its validity/calibration evidence, applicability, limitations, and continuation rule. Relevant resources can include compute, instrument access, samples, and human time. There is **no universal cost fraction or exactness requirement**.

| Gate type | What must be clear |
|---|---|
| Exact evaluator shortcut | Which evaluator and reference cases it reproduces, with what numerical tolerance and scope |
| Empirical proxy or pilot | Evidence relating the proxy to the target, uncertainty, and where the relationship may fail |
| Diagnostic or necessary-condition check | Which failure mode or prerequisite it tests, and precisely what failure implies |
| No preliminary gate | Why the direct experiment is the informative option, its bounded cost, and authority to proceed |

A short training run, selected image region, simulation, or oracle analysis need not predict the final experiment exactly. State its limited claim. Do not manufacture an exact surrogate or fabricate calibration to satisfy a template.

For each outcome:

- **Pass:** follow the authorized continuation rule. Passing a gate is not a positive scientific verdict.
- **Valid fail:** stop or narrow the work as the preregistered continuation rule requires. Record a scoped negative only if the valid gate actually decides the stated scientific question; otherwise record an unresolved question or failure of this candidate under the tested settings.
- **Invalid or inconclusive gate:** do not interpret it as evidence against the hypothesis. Diagnose or collect more evidence only within the authorized budget and retry conditions.

A gate-required experiment cannot silently bypass its failed gate. An authorized direct experiment or documented exception does not need a newly invented gate. If changing the continuation rule requires new authority, return that decision before proceeding.

### Select useful work without invented precision

Use the stated intuition when provided. Otherwise compare candidate tests by decision relevance, evidence, expected information or benefit, cost, dependencies, and review burden. Respect project constraints and planner allocation.

`headroom × P(realizable) / cost` is optional advisory input **only** when the candidates share a meaningful comparable objective, the bound and current value have compatible definitions, cost is positive with a common unit, and the probability estimate has an explicit basis. Missing ceilings, probabilities, or costs remain unknown. Do not manufacture them or compare scores across unlike objectives. A transparent qualitative recommendation is valid. A deterministic scoring engine is not implemented by probe.

## 4. Implement, execute, and inspect validity

Use the selected implementation backend only when code is needed and implementation is authorized. Give the implementer the intended behavior, engineering acceptance checks, environment, allowed changes, and evidence it must return. **A scientific failure/stop criterion is not a coding acceptance test.** A faithful implementation can produce a valid negative result.

Run the configured gate and experiment in the recorded environment, preserving commands, configuration and evaluator identities, process/job identifiers when available, and outputs. Gate implementation may itself require code; do not claim the gate ran before that implementation exists and passes its checks.

First assess execution and engineering checks; then assess measurement validity; only then apply the scientific decision rules. Inspect suspiciously good outcomes and known failure modes as well as disappointing ones. Review depth should match the cost of accepting an incorrect claim. If a required validity check is missing, keep the conclusion unresolved rather than substituting an agent's confident report.

Track resource use and apply the task's stop conditions across attempts and sessions. Use actual scheduler/process controls where available and authorized; the launcher itself provides no budget enforcement, timeout, host routing, environment provisioning, monitoring, or automatic restart.

## 5. Verdicts and scientific constraints

Record execution, measurement, and scientific outcome separately:

| Dimension | Values and meaning |
|---|---|
| Execution | `pending`, `completed`, `failed`; a failed attempt can leave usable partial evidence, which must be qualified |
| Measurement | `pending`, `valid`, `invalid`; invalid data/evaluation cannot decide the scientific hypothesis |
| Scientific verdict | `pending`, `positive`, `negative`, `inconclusive`, `not_evaluated` |

- **Positive:** valid evidence meets the preregistered support criterion within its stated scope.
- **Negative:** valid evidence meets the preregistered negative criterion under the tested settings. This is a successful experimental deliverable when the assignment was to test the hypothesis; it does not imply the broader research goal was achieved.
- **Inconclusive:** the evidence does not distinguish the relevant alternatives or lacks the required precision/coverage. State what would discriminate them.
- **Not evaluated:** execution failure, invalid measurement, or another unmet prerequisite prevented a scientific assessment. Record the operational/measurement failure without calling the hypothesis false.

Do not promote a single failed run into a permanent class-level exclusion. A reusable scientific constraint needs linked evidence, explicit assumptions/applicability and limitations, reopening conditions, and a review appropriate to its consequence. For broad or persistent exclusions, obtain an independent check of the measurement/inference or proof before adoption; a second agent's agreement alone is not independent evidence. If verification is unavailable, retain a proposed constraint and the next check needed. Restrict candidate selection only within a constraint's validated scope; changed data, evaluator, representation, or assumptions may reopen it.

Keep the constraint once in `state.yaml` or its canonical project record, linked to the detailed lesson. Do not mirror an editable list into `loop.md` or treat old empirical observations as unconditional laws.

## 6. Landing and resume

Within the authorized landing scope, produce:

1. `lessons/lesson_<run_id>.md` or the project's equivalent: original preregistration, validity assessment, verdict, evidence references, limitations, resource use, and next decision/action.
2. An entry in `lessons/lessons.md`, linking that record. Preserve the historical meaning of existing index columns; include explicit outcome dimensions when an old summary column is ambiguous.
3. The corresponding project-state update: close the active run, update a current result only when it is valid and comparable, and add or revise only supported constraints. Invalid or inconclusive results do not erase a valid baseline. A negative outcome does not automatically eliminate the whole lever family.
4. A concise return to the planner: task/run ID, outcome, evidence, changes landed or proposed, consumed/remaining budget as known, and the exact decision or next action needed.

`runs/<run_id>/.done` may mark a **closed and landed record**, including a valid negative, invalid result, or execution failure. It is not a scientific-success signal. Write it only after the evidence and authorized state updates agree; if approval is still needed, leave the run in review with a proposed patch. Large or private artifacts stay in their owning storage; this directory may hold permitted references and lightweight records.

On resume, inspect the run record, state, artifacts, remaining authority/budget, and any recorded process/job state before launching work. A missing sentinel does not prove a job stopped, and a sentinel without its expected record is a discrepancy. Do not relaunch a live job or duplicate a closed run merely because a session restarted. New experiments use new run IDs; resume or retry existing work only under its recorded conditions. These are operator duties, not guarantees supplied by the shell scripts.

## 7. Actions and helpers

| Action | Behavior |
|---|---|
| An intuition | Form and run its contract when authorized; otherwise return the ready proposal or missing decision |
| No action / `status` | Read state and relevant run records; show results, open work, evidence gaps, and next decisions without launching or modifying science |
| `next` | Recommend useful next work using §3; execute only when selection and execution are authorized |
| `bootstrap` | Read existing project context, fill only needed unresolved fields, and adopt v2 for a new project; do not automatically upgrade an existing one |
| `lesson [run-or-name]` | Resolve the intended run, inspect its actual evidence, and land or propose the result under §6; if the name matches multiple runs, resolve that ambiguity before modifying state |

For a new bootstrap, `scripts/probe-init.sh <project-directory>` copies the current `state.yaml` and `loop.md` templates only if absent, creates an index when absent, and makes its standard directories. It does not validate readiness or migrate existing content. Fill the templates from known project context; ask only for consequential missing information. The copied `loop.md` holds a method revision and local evaluation/gate/authority settings, not another generic procedure. A per-run record snapshots settings actually used.

Resolve `implement=` first, then `PROBE_IMPLEMENT`, otherwise `none`:

| Backend | Invocation and scope |
|---|---|
| `none` | Coordinator performs authorized analysis/diagnostics; when implementation is needed, resolve the implementation choice before delegating code changes |
| `full-claude` | `scripts/probe-run-agent.sh claude <prompt-file-or-> <output-file>`; one noninteractive Claude step |
| `full-codex` | `scripts/probe-run-agent.sh codex <prompt-file-or-> <output-file>`; one noninteractive Codex step |
| `ccc-duet` | Use the separately available CCC skill/backend with a self-contained task and engineering acceptance checks; optional, not shipped or implemented by this launcher |

The launcher's first argument is `claude` or `codex`, not the `full-*` selector. Its second argument is a **prompt filename** or `-` for stdin. Invoke its absolute path from the intended code workspace; it inherits the current working directory and environment. The output file contains the final agent response, which must be verified against artifacts; it is not proof of correct execution or scientific success.

`auto` permits fewer routine check-ins within the task's existing authority. It does not bypass a project's explicit gates, expand budgets, authorize external actions, or turn proposals into accepted state. Changing backend also does not alter the project's adopted scientific protocol.
