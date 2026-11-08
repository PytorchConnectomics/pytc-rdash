"""Materialize and submit one authorized, attempt-isolated assignment."""
import base64
import json
import uuid
from pathlib import Path

from dashboard.app import safety
from . import goals, observe, verify
from .store import Error, encode


def attempt_directory(settings, row):
    project, goal = row["goal"].split("/", 1)
    return safety.resolve_within(goals.directory(settings, project, goal), "assignments", row["assignment"], "attempts", row["attempt"])


def prepare(settings, store, goal, aid, generation, revision):
    current, snapshot = store.snapshot(goal)
    if current != revision:
        raise Error("stale_revision")
    assignment = snapshot["assignments"].get(aid)
    if assignment is None:
        raise Error("unknown_assignment")
    request = uuid.uuid4()
    name = "rdash-" + base64.b32encode(request.bytes).decode().lower()[:12]
    row = dict(goal=goal, assignment=aid, attempt=str(request))
    root = attempt_directory(settings, row)
    outputs = [dict(spec, path=str(safety.resolve_within(root, "out", spec["filename"]))) for spec in assignment["outputs"]]
    inputs = {}
    for label, source in assignment["inputs"].items():
        if "from" in source:
            dependency = source["from"]
            with store.connection() as db:
                if not store._verified(db, goal, dependency["assignment"], snapshot["assignments"][dependency["assignment"]]):
                    raise Error("dependency_unverified")
            found = store.rows("SELECT d.request_id FROM dispatches d JOIN receipts r ON d.attempt=r.attempt "
                               "WHERE d.goal=? AND d.assignment=? AND r.verdict='verified' ORDER BY d.created DESC LIMIT 1",
                               (goal, dependency["assignment"]))
            if not found:
                raise Error("dependency_unverified")
            prior = store.dispatch(found[0]["request_id"])
            path = next(out["path"] for out in prior["outputs_declared"] if out["name"] == dependency["output"])
            receipt, sha = goals.read_json(safety.resolve_within(attempt_directory(settings, prior), "receipt.json"))
            imported = store.rows("SELECT digest FROM receipts WHERE attempt=? AND verdict='verified'", (prior["attempt"],))
            if not imported or imported[0]["digest"] != sha or verify.digest(path) not in receipt["outputs"]:
                raise Error("dependency_changed")
        else:
            path = source["path"]
        inputs[label] = verify.digest(path)
    with store.connection() as db:
        parameters = store._parameters(db, goal, aid, assignment, revision)
    project_root = safety.resolve_within(settings.repo_root, "projects", snapshot["project"])
    command = [assignment["python"], "-u", str(safety.resolve_within(project_root, "04_bv_volume.py")),
               assignment["step"], "--vol", assignment["volume"]]
    for parameter, value in parameters.items():
        command.extend(["--" + parameter, str(value)])
    return store.reserve(goal, aid, generation, str(request), name, str(request), inputs, outputs, command, revision)


def submit(settings, store, scheduler, row):
    if row["state"] != "reserved":
        return observe.recover_identity(store, scheduler, row)
    found = scheduler.lookup_by_name(row["job_name"], row["created"])
    if found:
        with store.transaction() as db:
            current = db.execute("SELECT state FROM dispatches WHERE request_id=?", (row["request_id"],)).fetchone()
            if current is None or current[0] != "reserved":
                raise Error("not_reserved")
            db.execute("UPDATE dispatches SET state='refused',refuse_reason='name_collision' WHERE request_id=? AND state='reserved'", (row["request_id"],))
            db.execute("UPDATE reservations SET released=1 WHERE request_id=?", (row["request_id"],))
            store._event(db, row["goal"], "dispatch_refused", row["request_id"], {"reason": "name_collision"})
        return prepare(settings, store, row["goal"], row["assignment"], row["generation"], row["snapshot_revision"])
    revision, snapshot = store.snapshot(row["goal"])
    assignment = snapshot["assignments"][row["assignment"]]
    root = attempt_directory(settings, row)
    root.mkdir(parents=True, exist_ok=True)
    manifest = safety.resolve_within(root, "dispatch.json")
    record = dict(row, step=assignment["step"], assignment_record=assignment,
                  output_dir=str(root / "out"), receipt_path=str(root / "receipt.json"))
    safety.publish_replace(manifest, (encode(record) + "\n").encode())
    confirmed = store.confirm_submittable(row["request_id"])
    project_root = safety.resolve_within(settings.repo_root, "projects", snapshot["project"])
    try:
        job_id = scheduler.submit(confirmed, safety.resolve_within(project_root, "05_bv_step.sbatch"), manifest,
                                  project_root, assignment["memory"], assignment["partition"])
    except (Error, OSError):
        return observe.recover_identity(store, scheduler, confirmed)
    observe.adopt(store, row["request_id"], job_id)
    return store.dispatch(row["request_id"])
