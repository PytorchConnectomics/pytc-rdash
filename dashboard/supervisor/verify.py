"""Bind receipt evidence to a dispatch before accepting any completion claim."""
import hashlib
import json
import math
from pathlib import Path

from dashboard.app import inspection, safety
from .store import Error, encode


CHECKS = ("receipt_identity", "exit_zero", "outputs_present", "inputs_match", "params_authorized", "structure")
CALIB_KEYS = {"vol", "shape", "block", "halo", "sigmas", "tissue_thr", "pct", "cut",
              "n_blocks_sampled", "n_score_samples", "percentiles", "seconds"}


def digest(path):
    path = Path(path)
    stat = path.stat()
    result = dict(path=str(path.absolute()), size=stat.st_size, mtime=stat.st_mtime)
    if stat.st_size <= 64 * 1024 * 1024:
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                hasher.update(chunk)
        result["sha256"] = hasher.hexdigest()
    else:
        result["sha256_omitted"] = "over_64_mib"
    after = path.stat()
    if (stat.st_size, stat.st_mtime_ns, stat.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise Error("input_changed")
    return result


def check_receipt(row, assignment, receipt, observe_paths=inspection.observe_paths):
    detail = {name: False for name in CHECKS}
    if not isinstance(receipt, dict):
        return detail
    try:
        identity = {"attempt": row["attempt"], "request_id": row["request_id"], "goal": row["goal"],
                    "assignment": row["assignment"], "job_name": row["job_name"], "slurm_job_id": row["job_id"],
                    "command": row["command"]}
        expected = row["outputs_declared"]
        paths = [out["path"] for out in expected]
        actual = receipt["outputs"]
        detail["receipt_identity"] = (receipt.get("schema") == 1 and all(receipt.get(k) == v for k, v in identity.items())
                                      and [out["path"] for out in actual] == paths)
        detail["exit_zero"] = type(receipt.get("exit_code")) is int and receipt["exit_code"] == 0
        detail["inputs_match"] = receipt.get("inputs") == row["inputs_digest"]
        detail["params_authorized"] = receipt.get("parameters") == row["parameters"]
        observed, status = observe_paths("", paths)
        present = status == "ok" and bool(paths) and row["submitting_at"] is not None
        for output, written in zip(expected, actual):
            path = output["path"]
            state = observed[path]
            safety.resolve_within(Path(path).anchor, *Path(path).parts[1:])
            present = (present and state["state"] == "present" and state.get("kind") == "file"
                       and state["size"] >= output["min_size"] and state["mtime"] >= row["submitting_at"]
                       and digest(path) == written)
        detail["outputs_present"] = bool(present) and len(expected) == len(actual)
        if assignment["step"] == "tissue":
            summary = receipt.get("summary", {})
            detail["structure"] = (summary.get("dataset") == "main" and summary.get("rank") == 3
                                   and summary.get("dtype") == "uint8"
                                   and summary.get("shape") == [v // assignment["downsample"] for v in assignment["source_shape"]])
        elif assignment["step"] == "calibrate" and detail["outputs_present"]:
            path = next(out["path"] for out in expected if out["name"] == "calib")
            with open(path, "rb") as stream:
                raw = stream.read(1024 * 1024 + 1)
            value = json.loads(raw) if len(raw) <= 1024 * 1024 else {}
            cut = value.get("cut")
            detail["structure"] = (CALIB_KEYS <= value.keys() and type(cut) in (int, float)
                                   and math.isfinite(cut) and 0 < cut < 1
                                   and value["vol"] == assignment["volume"] and value["shape"] == assignment["source_shape"]
                                   and value["pct"] == row["parameters"]["pct"])
        elif assignment["step"] == "harness_sleep":
            detail["structure"] = True
    except (OSError, ValueError, TypeError, KeyError, StopIteration, Error, safety.Error):
        pass
    return detail


def import_receipt(store, row, assignment, path, observe_paths=inspection.observe_paths):
    path = Path(path)
    with path.open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise Error("receipt_too_large")
    sha = hashlib.sha256(raw).hexdigest()
    try:
        receipt = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        receipt = {}
    checks = check_receipt(row, assignment, receipt, observe_paths)
    verdict = "verified" if all(checks.values()) else "rejected"
    with store.transaction() as db:
        old = db.execute("SELECT digest,verdict FROM receipts WHERE attempt=?", (row["attempt"],)).fetchone()
        if old:
            if old[0] == sha:
                return old[1]
            store._event(db, row["goal"], "receipt_conflict", row["attempt"])
            db.execute("UPDATE receipts SET verdict='conflict' WHERE attempt=?", (row["attempt"],))
            db.execute("UPDATE evidence SET status='conflict' WHERE receipt_attempt=?", (row["attempt"],))
            db.execute("UPDATE goal_state SET phase='decision_required',waiting_reason='receipt_conflict' WHERE goal=?", (row["goal"],))
            return "conflict"
        db.execute("INSERT INTO receipts VALUES(?,?,?,?,?,?)", (row["attempt"], row["request_id"], sha, store.clock(), verdict, encode(checks)))
        for criterion, valid in checks.items():
            db.execute("INSERT INTO evidence(goal,assignment,criterion,status,receipt_attempt,checked_at,detail) VALUES(?,?,?,?,?,?,?)",
                       (row["goal"], row["assignment"], criterion, "verified" if valid else "rejected", row["attempt"], store.clock(), encode({})))
        store._event(db, row["goal"], "receipt_" + verdict, row["attempt"], checks)
    return verdict


def complete(store, goal, generation, revision):
    error = None
    with store.transaction() as db:
        store._commands(db, goal)
        store._lease(db, goal, generation)
        current, snapshot = store._snapshot(db, goal)
        if revision != current:
            raise Error("stale_revision")
        if "complete" not in snapshot["authority"]["allowed_actions"]:
            raise Error("action_not_allowed")
        if store._balance(db, goal)["phase"] != "running":
            raise Error("not_running")
        for criterion in snapshot["acceptance"]:
            if not store._verified(db, goal, criterion["assignment"], snapshot["assignments"][criterion["assignment"]]):
                error = Error("acceptance_unverified")
        if store._balance(db, goal)["held_jobs"]:
            error = Error("outstanding_dispatches")
        if error:
            store._event(db, goal, "complete_refused", revision, {"reason": error.code})
        else:
            db.execute("UPDATE goal_state SET phase='achieved',waiting_reason=NULL,updated=? WHERE goal=?", (store.clock(), goal))
    if error:
        from .observe import decision
        decision(store, goal, error.code)
        raise error
