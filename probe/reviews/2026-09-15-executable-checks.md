# Executable task checks and evaluator evidence

**Decision:** adopted as supporting tools, 2026-09-15, under Donglai's request
to implement the proposed checker, fixtures, and one evaluator connection.
The scientific protocol remains v2, and existing projects retain their adopted
versions. No scheduler, autonomous research job, or method migration is activated.

## Observation and scope

The initializer copied templates but described the workspace as ready; the
launcher recorded an agent response without validating its evidence. Project
records differ: NISB has rich legacy science, LICoNN deployment has engineering
acceptance, and other projects have unresolved task definitions. A universal
state migration or keyword-based readiness score would misrepresent them.

## Implemented change

- `check_readiness.py` reads an optional reference-only JSON contract in an
  existing spec/task file. It reports local-reference presence, missing or
  inconsistent structure, and uninspected external references. It performs no
  experiment, network operation, lock mutation, or scientific interpretation.
- The project template adds acceptance, evidence, and authority/limits sections.
  Source references remain canonical; old projects need not acquire new files.
- A NISB example connects to the actual PyTC NERL adapter and `em_erl` backend
  using explicit, tiny synthetic fixtures. Receipts bind code, backend, input,
  parameters, and observations. Their scientific verdict is `not_evaluated`.
- Six fictional behavior cases preserve the earlier four trial situations and
  add wrong-checkpoint and unsupported-completion cases. They support future
  controlled comparisons and do not claim measured agent improvement.
- Lock guidance now exempts read-only inspection and requires exclusive
  ownership for mutation. This is guidance, not a distributed lock service.
  The initializer now accurately describes its output as an unvalidated scaffold.

## Validation

The checker found all five references in the
[NISB engineering task](../../projects/nisb-base-26/research_plan/2026-09-15_evaluator-regression.md).
Authority and evidence verification remain explicitly unknown. The legacy NISB
spec returns unknown without a contract; the unfilled template returns exit 1
for its missing authority reference. These are the intended results, not claims
that an experiment is ready.

The CPU regression uses the actual local PyTC metric module and a tracked-source
export of `PytorchConnectomics/em_erl` at
`b1504f2c3edbece34efc417c395432692d54e14d`. The source export, provenance manifest,
and receipt are retained under the execution host's
`~/.local/state/dw-os/probe-validation/2026-09-15/`. Nothing was installed into
the Python environment or copied into the shared research or PyTC repositories.
Source identities in the receipt include worktree bytes rather than relying on
a clean Git checkout.

The complete suite passed **25 tests, with no skips**, using Python 3.11.14 in
the existing `pytc` environment and explicit `NERL_TEST_CODE_REPO` and
`NERL_TEST_BACKEND_REPO` paths:

```bash
python -B -m unittest discover -s probe/tests -v
```

This includes 19 checker tests, five adapter boundary tests, and one real CPU
integration test covering all five evaluator cases and receipt verification.
Tests cover legacy preservation, no writes during inspection, path/contract
ambiguity, hidden Markdown content, missing dependencies, empty fixtures,
receipt overwrite refusal, and altered results with recomputed checksums.
The shell helper passed `bash -n`; changed-file whitespace, local documentation
link targets, and the six-case JSON bank also passed their checks.

A separate explicit `--run --receipt` invocation retained `nerl-receipt.json`;
`--verify-receipt` passed with current sources and inputs matching, recorded
assertions consistent, and no source changes during scoring. Verification output
is retained in `nerl-verification.json` alongside it.

| Actual evaluator check | Observed result | Outcome |
|---|---|---|
| Perfect | NERL 1 | Pass |
| Split | NERL 0.65625 | Pass |
| False merge | NERL 0 | Pass |
| Strict one-node overlap | NERL 0.28125 | Pass |
| Invalid 2D input | Expected `ValueError` | Pass |

The run used NumPy 2.4.6, NetworkX 3.6.1, and imageio 2.37.4. Retained receipt
checksum: `8fafb418b1179ce9395d4252760119f7c53410addfc8974540e21812939f62f9`.
Aggregate manifest for the adapter, fixtures, actual metric module, and six
backend source files: `513232b13edc97beabf7bd0045334972301af8e71e115377a717388ba0167760`.

Synthetic evaluator results must not be cited as a reproduction of the
historical NISB score, a trained-checkpoint result, or an experiment win.

### Informal behavior trial

One in-session agent answered the six fictional scenarios using the actual
protocol; expected/forbidden fields were withheld from the supplied scenarios.
A separate reviewer compared the responses against every criterion. Under
strict coverage scoring, the result was **one pass, five inconclusive, zero
observed forbidden behaviors**. Omissions were not inferred to be satisfied.

| Case | Response evidence and missing coverage | Result |
|---|---|---|
| Valid negative | Correct completed/valid/negative judgment and baseline preservation; did not explicitly limit the conclusion to tested settings | Inconclusive |
| Invalid measurement, exhausted budget | Stopped and withheld a scientific verdict; did not explicitly return the budget decision needed for further execution | Inconclusive |
| Authorized instrument pilot | Preserved 20% pilot authority and required preflight; omitted both measured objectives and the calibrated proxy's uncertainty/limitations | Inconclusive |
| Legacy running job | Reported observed running status, retained the pinned method, and prohibited mutation/relaunch | Pass |
| Wrong checkpoint | Flagged A/B mismatch and withheld promotion; omitted explicit baseline preservation and the specific evidence needed next | Inconclusive |
| Unsupported completion | Distinguished the worker claim from execution evidence; omitted the authority boundary for obtaining the receipt | Inconclusive |

This is an informal response-coverage check, not an isolated model comparison or
a demonstration of runtime enforcement. No scenario action was performed.
The full inherited prompt, model settings, and token cost were not captured.
The evaluated protocol's SHA-256 is
`f104611b8e2f393c623712e04eab586fa6c215a5ea7d9fce4ae7132e245e16d6`;
the case bank's is `5030ac15cbe298298d3d2cc98948faa38ffe070239072da76720e86caf5c3063`.
The omissions identify concrete future evaluation targets. They do not justify
silently changing an existing project's scientific method.

## Tradeoffs and reconsideration

Explicit contract references add a small mapping burden. Use them only when a
task benefits; don't copy full science into another schema. A structurally valid
record can still be wrong or stale. Exit zero is not execution authority, and a
hash match is not independent scientific evidence or a signed attestation.

The first adapter tests an evaluator rather than operating a full experiment.
Broader monitoring/resume support should follow successful use on a selected
real task with its own resources and review conditions. Reconsider the schema
if it forces duplicate state, blocks legitimate qualitative research, or costs
more human time than it saves. Changes to scientific procedure still follow
the separate method review/adoption process.
