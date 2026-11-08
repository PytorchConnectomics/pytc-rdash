# Governed research goals

This stdlib-only supervisor owns durable execution beside the SLURM scheduler.
The shipped `bv-mn20-auto` goal runs MN20 tissue → calibration after explicit
activation. Offline synthetic tests exercise continuation; a real BC run and
browser validation remain separate verification stages.
The demonstration re-derives an existing calibration and makes no new scientific
claim. It does not segment 758500R.

## Ownership and storage

| Record | Writer |
|---|---|
| `projects/<project>/goals/<goal>/goal.json`, `assignments/*.json` | Human author; CLI creation uses the repository writer lock |
| `$RESEARCH_DASH_CACHE/supervisor/runtime.db` | Supervisor, except command insertion by CLI/board |
| `state.json`, `decisions/*.json` | Supervisor projections through `safety.publish_replace` |
| Attempt `dispatch.json` | Supervisor |
| Attempt `receipt.json` and `out/` | Compute-node wrapper |
| `results/rdash/bv-mn20-auto/calib.json` | Verified calibration projection for the existing card result reader |

**The runtime database is durable operational state, not a disposable cache.**
Back it up with SQLite's backup API, or stop the supervisor before copying the
database and its WAL files. WAL requires a filesystem with working SQLite/POSIX
locking. The board and supervisor must share the same local repository and
runtime location; an SSHFS-mounted second writer is unsupported.

Snapshots hash the exact authored goal and assignment bytes under the existing
`safety.writer_lock`. Reservations read only the imported snapshot, under
`BEGIN IMMEDIATE`, and include held jobs and CPU-hours. The current snapshot is
stored explicitly; revisiting an earlier revision never depends on timestamp
ordering. Editing files does not alter an already imported snapshot mid-pass.
All cooperating authoring tools must use the same lock.

Immediately before submission another transaction applies queued commands and
checks phase, revision, lease generation, authority, and outstanding budget.
A pause committed before this boundary refuses the reservation and releases it;
a pause after this boundary does not cancel a launch already in flight.
The project `.agent-lock` is refreshed while work is active. Foreign locks are
never removed. A known supervisor owner may be replaced only when its process
is proven dead on this host and its lease is present in the intact runtime store.

## Operator commands

From the repository root on BC, with the configured Claude CLI available:

```sh
dashboard/app/rdash_supervisor.sh start
dashboard/app/rdash_supervisor.sh status
python -m dashboard.supervisor.cli activate --project allen-microct-26 --goal bv-mn20-auto
python -m dashboard.supervisor.cli status --project allen-microct-26 --goal bv-mn20-auto
dashboard/app/rdash_supervisor.sh stop
```

`status` reports whether the startup sentinel probe passed. Initial process
creation is not a completed readiness check. `restart` is also supported.
Stopping the supervisor does not cancel SLURM jobs. The launcher is intended for
Linux/BC and checks process ownership through `/proc` before signalling.

`create --project P --goal G --record bundle.json` accepts the authored goal
object with an `assignments` map and creates a paused goal. `activate` imports
its snapshot and queues resume; it never submits directly. For later commands,
copy `goal_revision` from status:

```sh
python -m dashboard.supervisor.cli pause --project P --goal G --revision REVISION
python -m dashboard.supervisor.cli resume --project P --goal G --revision REVISION
python -m dashboard.supervisor.cli resolve --project P --goal G --revision REVISION \
  --decision DECISION_ID --value '99.0'
```

Use real identifiers and the displayed revision in place of placeholders.
`run-once` runs a real service pass; it is not an offline dry run.
The science interpreter and source locations live in authored assignment
configuration. The wrapper checks the actual `data.yaml` source path and HDF5
shape against the reserved source before executing the unchanged science CLI.

## Recovery and accounting

Dispatch identities are UUID requests and unique `rdash-` scheduler names.
Name lookup uses both `squeue` and `sacct`; any transport uncertainty blocks a
fresh submission. A pre-submit name collision refuses the old reservation and
creates a fresh request for a later pass.

Once `submitting` is committed, **the dispatch is never resubmitted**. On
recovery, one matching scheduler identity is adopted; zero or multiple matches
produce `unknown`, retain the reservation, and raise an `ambiguous_submission`
decision. After inspecting the scheduler, resolve that decision with one of:

```json
{"action":"adopt","job_id":"123456"}
{"action":"confirm_not_submitted"}
{"action":"abandon"}
```

These are human attestations. `confirm_not_submitted` releases the reservation
and permits a fresh attempt. `abandon` cancels further goal work and retains the
unknown reservation; it does not pretend the scheduler job stopped.

Missing/corrupt `runtime.db` with outstanding projected dispatches refuses
startup, publishes `decision_required` / `runtime_store_lost`, and requests
restoration or explicit human reconciliation. Scheduler records alone cannot
reconstruct consumed budget. Automatic database reconstruction and a write-off
CLI are not implemented; restoring the intact database is the supported recovery.

Reservation = requested CPUs × time limit. Settlement uses only the main
`sacct` record and charges allocated CPUs × elapsed time, including failed jobs.
The CPU-hour budget is enforced on reservations at launch, **not as a billing
guarantee**. An `AllocCPUS` overrun is charged and moves the goal to `exhausted`.
Unavailable accounting retains the reservation; after the settlement window it
is marked `unsettled` and remains in the displayed resource balance. Budget
reductions do not erase existing commitments. Only `TIMEOUT` and `NODE_FAIL`
permit one retry; every retry has a new identity and spends another job.

## Evidence and coordinator bounds

Every attempt has isolated outputs. Receipt identity, exact command, authorized
parameters, input digests, output paths/digests, exit status, freshness, and
step structure must all verify. A criterion set must come from one accepted
receipt, never fragments of failed attempts. A differing receipt digest is a
conflict, not an overwrite. Completion is refused without verified acceptance
and without settling outstanding reservations.

Inputs/outputs up to 64 MiB are SHA-256 bound. Larger inputs, including the
32 GB source volume, are bound by path, size and mtime only; an in-place change
preserving those metadata is not detected. HDF5 structure is reported by the
compute-node wrapper using the existing science environment; dashboard code
has no HDF5 dependency. The supervisor verifies that summary against the
authored source shape. SIGKILL, node loss, or an unwriteable filesystem may
prevent receipt publication; absence never counts as successful evidence.

Claude runs with `--print --output-format text --no-session-persistence
--tools ""`, a fresh cache working directory, a scrubbed environment allowlist,
and a hard timeout. `--tools ""` is a CLI contract, not a kernel sandbox. A
service-start sentinel probe must pass before any goal advances, and does not
spend a goal invocation. Invocation reservations count before spawning, including
waits, decision requests, invalid replies, and crashes. Two coordinator failures
require a decision. Replies must contain one `rdash-decision` JSON fence with
the authored goal ID, revision, generation, rationale and action.

Defaults: 120000-byte packet ceiling, 180-second coordinator timeout, 30 seconds
between wakes, 12 wakes/hour, 15-second polling, and 900-second settlement
window. Packet overflow is an error, never truncation. Environment overrides:
`COORDINATOR_PACKET_MAX_BYTES`, `COORDINATOR_TIMEOUT_S`,
`RDASH_SUPERVISOR_POLL_S`, `RDASH_SETTLE_WINDOW_S`.

The coordinator environment allowlist includes `CLAUDE_CONFIG_DIR` and
`XDG_CONFIG_HOME` so host-specific authentication locations survive scrubbing.
`Settings.coordinator_env_allowlist` controls the list; the comma-separated
`COORDINATOR_ENV_ALLOWLIST` environment setting extends its defaults without a
code change. Unlisted variables remain excluded. `provider_invocation_failed`
means the process could not be launched or completed (including timeout);
`provider_refused` reports a provider nonzero exit with its exit status and
configuration guidance. Provider output and credential values are not echoed.

## Board integration and remaining work

`GET /api/goal?project=P&goal=G` returns the published phase, assignments in
flight, next permitting event, observations, budget, pending decisions,
coordinator rationale, command acknowledgments, and recent events.
`POST /api/goal/command` accepts `project`, `goal`, `kind`, `goal_revision` and
optional `payload`; kinds are `pause`, `resume`, and `resolve_decision`. Existing
Host, Origin, and mutation `X-Rdash: 1` guards apply unchanged.

Parsed session declarations are preserved. Observed goal activity appends
`source: goal` entries; merely having a running/waiting goal does not invent
process liveness. The existing `in_session` attention rule handles actual goal
activity, below unknown artifacts, verdicts and live declared scheduler jobs.
Human-owned goal rules cover decision-required, paused, exhausted, and unknown.
Consequently a paused or decision-required goal with an authored terminal
verdict now reports owner `you` rather than `closed`. Owner and Next remain
canonical in `attention.py`.

Each refresh indexes goal projections once. Unreadable or identity-mismatched
projections show an unknown goal using the authored card binding, including on
cards with terminal verdicts. If the authored binding is also unreadable, all
project cards show the warning. Conflicts carry every goal ID; correct their
authored card bindings rather than resolving a nonexistent synthetic decision.

The card detail panel shows assignment in flight, the event permitting
continuation, phase, resource balance (unsettled is included in held), pending
decisions, and rationale, without duplicating Owner/Next. Parameter decisions
and ambiguous submissions have revision-bound resolution controls. Pause/resume
also carry the displayed revision. Commands are queued, not reported as applied;
Refresh goal fetches current projections and command acknowledgments. A stale
revision is shown as an error and requires refreshing before retrying.
The optional decision demonstration and CLI job cancellation are omitted.
General steering, 758500R goal records, multi-attempt volume segmentation,
cross-project allocation, Codex adapters, `/probe` selection, notifications,
log tails, and board activation/cancellation remain unimplemented.

The service currently requires an operator to diagnose and amend/recover
non-parameter operational decisions such as invalid evidence or a lost runtime
store; the decision-resolution command directly supports parameter choices and
ambiguous submissions only. No live BC execution or science result is claimed
by offline tests.
