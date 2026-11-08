"""Reconcile dispatch identities and observations without retrying ambiguous launches."""
import uuid

from dashboard.app import inspection
from dashboard.adapters.slurm import TERMINAL
from .store import Error, encode


def decision(store, goal, reason, assignment=None, parameter=None, question=None, generation=None, revision=None):
    with store.transaction() as db:
        current, snapshot = store._snapshot(db, goal)
        if generation is not None:
            store._commands(db, goal)
            store._lease(db, goal, generation)
            if revision != current:
                raise Error("stale_revision")
            if store._balance(db, goal)["phase"] != "running":
                raise Error("not_running")
        revision = current
        existing = db.execute("SELECT id FROM decisions WHERE goal=? AND reason=? AND state='open' "
                              "AND assignment IS ? AND parameter IS ?", (goal, reason, assignment, parameter)).fetchone()
        if existing:
            return existing[0]
        spec = snapshot["assignments"].get(assignment, {}).get("parameters", {}).get(parameter, {})
        identifier = str(uuid.uuid4())
        db.execute("INSERT INTO decisions(id,goal,assignment,parameter,question,recommendation,alternatives,evidence,"
                   "expected_cost,snapshot_revision,created,state,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,'open',?)",
                   (identifier, goal, assignment, parameter, question or reason.replace("_", " "),
                    encode(spec.get("recommendation")), encode(spec.get("allowed_values", [])), encode([]), encode({}),
                    revision, store.clock(), reason))
        db.execute("UPDATE goal_state SET phase='decision_required',waiting_reason=?,updated=? "
                   "WHERE goal=? AND phase NOT IN ('paused','exhausted','achieved','cancelled')", (reason, store.clock(), goal))
        store._event(db, goal, "decision_required", identifier)
        return identifier


def adopt(store, request_id, job_id):
    with store.transaction() as db:
        db.execute("UPDATE dispatches SET state='submitted',job_id=?,submitted_at=? "
                   "WHERE request_id=? AND state='submitting'", (str(job_id), store.clock(), request_id))


def recover_identity(store, scheduler, row):
    if row["state"] != "submitting":
        return row
    try:
        found = scheduler.lookup_by_name(row["job_name"], row["created"])
    except Error:
        found = []
    if len(found) == 1:
        adopt(store, row["request_id"], found[0]["job_id"])
    else:
        with store.transaction() as db:
            db.execute("UPDATE dispatches SET state='unknown',observed_state='unknown',observed_at=?,"
                       "refuse_reason='ambiguous_submission' WHERE request_id=? AND state='submitting'",
                       (store.clock(), row["request_id"]))
        decision(store, row["goal"], "ambiguous_submission", row["assignment"],
                 question="Reconcile scheduler identity: adopt <job_id>, confirm_not_submitted, or abandon; reservation remains held.")
    return store.dispatch(row["request_id"])


def reconcile(store, scheduler, row, probe=inspection.probe_jobs, settle_window=900):
    if row["state"] == "submitting":
        return recover_identity(store, scheduler, row)
    if row["state"] != "submitted":
        return row
    job_id = row["job_id"]
    observations, status = probe("", [int(job_id)])
    observed = observations.get(int(job_id), {}).get("reduced", "unknown") if status == "ok" else "unknown"
    try:
        settlement = scheduler.settle(job_id)
    except Error:
        settlement = None
    if settlement:
        observed = settlement["state"]
    now = store.clock()
    with store.transaction() as db:
        db.execute("UPDATE dispatches SET observed_state=?,observed_at=? WHERE request_id=?", (observed, now, row["request_id"]))
        if settlement:
            reservation = db.execute("SELECT * FROM reservations WHERE request_id=?", (row["request_id"],)).fetchone()
            if not reservation["released"]:
                cost = settlement["cpu_hours"]
                db.execute("UPDATE reservations SET released=1,settled_cpu_hours=? WHERE request_id=?", (cost, row["request_id"]))
                db.execute("UPDATE dispatches SET state='terminal',terminal_at=? WHERE request_id=?", (now, row["request_id"]))
                db.execute("UPDATE goal_state SET consumed_jobs=consumed_jobs+1,consumed_cpu_hours=consumed_cpu_hours+?,"
                           "last_progress=?,updated=? WHERE goal=?", (cost, now, now, row["goal"]))
                _, snapshot = store._snapshot(db, row["goal"])
                if store._balance(db, row["goal"])["consumed_cpu_hours"] > snapshot["budget"]["cpu_hours"]:
                    db.execute("UPDATE goal_state SET phase='exhausted',waiting_reason='allocation_overrun' WHERE goal=?", (row["goal"],))
                store._event(db, row["goal"], "assignment_terminal", row["request_id"], settlement)
        elif observed == "unknown" or observed in TERMINAL:
            # Missing accounting never releases money or establishes execution failure.
            missing = db.execute("SELECT created FROM events WHERE goal=? AND kind='accounting_missing' AND subject=? "
                                 "ORDER BY id LIMIT 1", (row["goal"], row["request_id"])).fetchone()
            store._event(db, row["goal"], "accounting_missing", row["request_id"])
            if missing and now - missing[0] >= settle_window:
                db.execute("UPDATE dispatches SET refuse_reason='unsettled' WHERE request_id=?", (row["request_id"],))
    return store.dispatch(row["request_id"])
