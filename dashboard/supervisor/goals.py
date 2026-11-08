"""Read authored goal records and publish projections of runtime truth."""
import hashlib
import json
import math
import re

from dashboard.app import safety
from .store import Error, encode


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise Error("invalid_goal_identifier", status=400)
    return value


def key(project, goal):
    return safety.project_id(project) + "/" + identifier(goal)


def directory(settings, project, goal):
    return safety.resolve_within(settings.repo_root, "projects", safety.project_id(project), "goals", identifier(goal))


def read_json(path):
    with path.open("rb") as stream:
        data = stream.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise Error("record_too_large", status=422)
    try:
        value = json.loads(data)
        encode(value)
    except (ValueError, UnicodeError, RecursionError):
        raise Error("invalid_record", status=422)
    if not isinstance(value, dict):
        raise Error("invalid_record", status=422)
    return value, hashlib.sha256(data).hexdigest()


def validate(payload, project, goal):
    try:
        if payload["schema"] != 1 or payload["project"] != project or payload["id"] != goal:
            raise ValueError()
        safety.card_ref(payload["card"])
        if not isinstance(payload["outcome"], str) or not payload["outcome"].strip():
            raise ValueError()
        allowed = payload["authority"]["allowed_actions"]
        if not isinstance(allowed, list) or not set(allowed) <= {"dispatch_assignment", "request_decision", "complete", "stop"}:
            raise ValueError()
        for field in ("jobs", "coordinator_runs"):
            if type(payload["budget"][field]) is not int or payload["budget"][field] < 0:
                raise ValueError()
        cpu = payload["budget"]["cpu_hours"]
        if type(cpu) not in (int, float) or not math.isfinite(cpu) or cpu < 0:
            raise ValueError()
        if type(payload["concurrency"]) is not int or payload["concurrency"] < 1:
            raise ValueError()
        assignments = payload["assignments"]
        if not isinstance(assignments, dict) or not assignments:
            raise ValueError()
        for aid, assignment in assignments.items():
            identifier(aid)
            if assignment["id"] != aid:
                raise ValueError()
            if assignment["step"] not in ("tissue", "calibrate", "harness_sleep"):
                raise ValueError()
            for field in ("python", "volume", "memory", "partition"):
                if not isinstance(assignment[field], str) or not assignment[field] or "\x00" in assignment[field]:
                    raise ValueError()
            if assignment["step"] in ("tissue", "calibrate"):
                if len(assignment["source_shape"]) != 3 or any(type(v) is not int or v <= 0 for v in assignment["source_shape"]):
                    raise ValueError()
            if assignment["step"] == "tissue" and (type(assignment["downsample"]) is not int or assignment["downsample"] <= 0):
                raise ValueError()
            outputs = assignment["outputs"]
            if not isinstance(outputs, list) or not outputs:
                raise ValueError()
            for output in outputs:
                identifier(output["name"])
                if not isinstance(output["filename"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", output["filename"]) or ".." in output["filename"]:
                    raise ValueError()
                if type(output["min_size"]) is not int or output["min_size"] < 0:
                    raise ValueError()
            if len({out["name"] for out in outputs}) != len(outputs) or len({out["filename"] for out in outputs}) != len(outputs):
                raise ValueError()
            for field in ("cpus", "time_limit_s"):
                if type(assignment[field]) is not int or assignment[field] <= 0:
                    raise ValueError()
            criteria = assignment["acceptance"]
            if not isinstance(criteria, list) or not criteria or any(not isinstance(c, str) or not c for c in criteria):
                raise ValueError()
            if len(criteria) != len(set(criteria)):
                raise ValueError()
            dependencies = assignment.get("dependencies", [])
            if not isinstance(dependencies, list) or any(d not in assignments or d == aid for d in dependencies):
                raise ValueError()
            for name, source in assignment["inputs"].items():
                identifier(name)
                if "from" in source:
                    dependency = source["from"]
                    if dependency["assignment"] not in dependencies:
                        raise ValueError()
                    if dependency["output"] not in [out["name"] for out in assignments[dependency["assignment"]]["outputs"]]:
                        raise ValueError()
                    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", source["filename"]) or ".." in source["filename"]:
                        raise ValueError()
                elif not isinstance(source["path"], str) or not source["path"].startswith("/"):
                    raise ValueError()
            for name, parameter in assignment.get("parameters", {}).items():
                identifier(name)
                if parameter["authorization"] == "preauthorized":
                    encode(parameter["value"])
                elif parameter["authorization"] == "human_decision":
                    if not isinstance(parameter["allowed_values"], list) or not parameter["allowed_values"]:
                        raise ValueError()
                else:
                    raise ValueError()
        def visit(aid, stack):
            if aid in stack:
                raise ValueError()
            for dependency in assignments[aid].get("dependencies", []):
                visit(dependency, stack | {aid})
        for aid in assignments:
            visit(aid, set())
        if not payload["acceptance"]:
            raise ValueError()
        for criterion in payload["acceptance"]:
            if criterion["criterion"] not in assignments[criterion["assignment"]]["acceptance"]:
                raise ValueError()
    except (KeyError, TypeError, ValueError, RecursionError, OverflowError):
        raise Error("invalid_goal_record", status=422)
    return payload


def load(settings, project, goal):
    root = directory(settings, project, goal)
    record, digest = read_json(safety.resolve_within(root, "goal.json"))
    payload = dict(record, assignments={})
    digests = {"goal.json": digest}
    assignments = safety.resolve_within(root, "assignments")
    for path in sorted(assignments.glob("*.json")):
        aid = identifier(path.stem)
        assignment, digest = read_json(safety.resolve_within(assignments, path.name))
        payload["assignments"][aid] = assignment
        digests["assignments/" + path.name] = digest
    validate(payload, project, goal)
    revision = hashlib.sha256(encode(digests).encode()).hexdigest()
    return revision, payload


def import_snapshot(settings, store, project, goal):
    with safety.writer_lock(settings):
        revision, payload = load(settings, project, goal)
        store.import_snapshot(key(project, goal), revision, payload)
    return revision


def projection(store, goal):
    # One read transaction prevents a view combining pre- and post-settlement balances.
    with store.connection() as db:
        db.execute("BEGIN")
        revision, snapshot = store._snapshot(db, goal)
        state = store._balance(db, goal)
        dispatches = [dict(row) for row in db.execute("SELECT * FROM dispatches WHERE goal=? ORDER BY created", (goal,))]
        decisions = [dict(row) for row in db.execute("SELECT * FROM decisions WHERE goal=? ORDER BY created", (goal,))]
        runs = [dict(row) for row in db.execute("SELECT * FROM coordinator_runs WHERE goal=? ORDER BY started DESC", (goal,))]
        events = [dict(row) for row in db.execute("SELECT * FROM events WHERE goal=? ORDER BY id DESC LIMIT 20", (goal,))]
        commands = [dict(row) for row in db.execute("SELECT * FROM commands WHERE goal=? ORDER BY created DESC LIMIT 20", (goal,))]
    for row in dispatches:
        for field in ("inputs_digest", "outputs_declared", "command", "parameters"):
            row[field] = json.loads(row[field])
        row["observation_age"] = None if row["observed_at"] is None else max(0, store.clock() - row["observed_at"])
    for row in decisions:
        for field in ("recommendation", "alternatives", "evidence", "expected_cost", "resolved_value"):
            if row[field] is not None:
                row[field] = json.loads(row[field])
    for row in events + commands:
        row["payload"] = json.loads(row["payload"])
    inflight = [row for row in dispatches if row["state"] in ("submitting", "submitted")]
    return dict(state, schema=1, id=snapshot["id"], project=snapshot["project"], card=snapshot["card"],
                goal_revision=revision, budget=snapshot["budget"], dispatches=dispatches,
                assignments=snapshot["assignments"], assignment_in_flight=[row["assignment"] for row in inflight],
                next_event=state["waiting_reason"], decisions=decisions,
                pending_decisions=[row for row in decisions if row["state"] == "open"],
                coordinator_in_flight=any(row["state"] == "running" for row in runs),
                rationale=next((row["rationale"] for row in runs if row["rationale"]), None),
                events=events, commands=commands)


def publish(settings, store, project, goal, generation):
    root = directory(settings, project, goal)
    with safety.writer_lock(settings), store.transaction() as db:
        # Keep the generation check and publication under the same database lock.
        store._lease(db, key(project, goal), generation)
        value = projection(store, key(project, goal))
        from dashboard.app import inspection
        paths = [output["path"] for row in value["dispatches"] for output in row["outputs_declared"]]
        observations, _ = inspection.observe_paths("", paths) if paths else ({}, "ok")
        for row in value["dispatches"]:
            row["artifacts"] = [dict(output, observation=observations[output["path"]], observed_at=store.clock())
                                for output in row["outputs_declared"]]
        decisions_dir = safety.resolve_within(root, "decisions")
        decisions_dir.mkdir(exist_ok=True)
        for decision in value["decisions"]:
            path = safety.resolve_within(decisions_dir, identifier(decision["id"]) + ".json")
            safety.publish_replace(path, (encode(decision) + "\n").encode())
        # The existing result reader permits results/, so publish verified calibration
        # bytes there while retaining attempt paths as the evidence of record.
        from .verify import digest
        for row in value["dispatches"]:
            accepted = db.execute("SELECT digest FROM receipts WHERE attempt=? AND verdict='verified'", (row["attempt"],)).fetchone()
            if not accepted:
                continue
            attempt = safety.resolve_within(root, "assignments", row["assignment"], "attempts", row["attempt"])
            receipt_path = safety.resolve_within(attempt, "receipt.json")
            receipt, receipt_digest = read_json(receipt_path)
            if receipt_digest != accepted[0]:
                raise Error("receipt_conflict")
            for output in row["outputs_declared"]:
                if output.get("publish_result"):
                    results_root = safety.resolve_within(settings.repo_root, "projects", project, "results")
                    target = safety.resolve_within(results_root, output["publish_result"])
                    source = safety.resolve_within(attempt, "out", output["filename"])
                    if digest(source) not in receipt["outputs"]:
                        raise Error("output_changed")
                    if source.stat().st_size <= 1024 * 1024:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        safety.publish_replace(target, source.read_bytes())
        safety.publish_replace(safety.resolve_within(root, "state.json"), (encode(value) + "\n").encode())
    return value
