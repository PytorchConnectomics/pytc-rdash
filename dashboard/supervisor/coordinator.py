"""Build bounded coordinator packets and validate proposals against durable ownership."""
import json
import re

from . import dispatch, goals, observe, verify
from .store import Error, encode


def packet(settings, store, goal, generation):
    revision, snapshot = store.snapshot(goal)
    events = store.rows("SELECT * FROM events WHERE goal=? AND consumed_at IS NULL ORDER BY id", (goal,))
    value = dict(goal=snapshot["id"], snapshot_revision=revision, generation=generation, authored=snapshot,
                 state=goals.projection(store, goal), events=events,
                 reply_contract={"fence": "rdash-decision", "fields": ["goal", "snapshot_revision", "generation", "rationale", "action"],
                                 "actions": ["dispatch_assignment", "request_decision", "complete", "stop", "wait"]})
    text = encode(value)
    if len(text.encode()) > settings.coordinator_packet_max_bytes:
        store.event(goal, "packet_too_large", revision)
        raise Error("packet_too_large")
    return text, [row["id"] for row in events]


def parse(reply, goal, revision, generation):
    matches = re.findall(r"^```rdash-decision\s*\n(.*?)^```\s*$", reply, re.M | re.S)
    try:
        if len(matches) != 1:
            raise ValueError()
        value = json.loads(matches[0])
        if (value["goal"] != goal or value["snapshot_revision"] != revision or type(value["generation"]) is not int or value["generation"] != generation
                or not isinstance(value["rationale"], str) or not 1 <= len(value["rationale"]) <= 2000
                or value["action"]["kind"] not in ("dispatch_assignment", "request_decision", "complete", "stop", "wait")):
            raise ValueError()
        action = value["action"]
        for field in (("assignment", "parameter") if action["kind"] == "request_decision" else
                      ("assignment",) if action["kind"] == "dispatch_assignment" else ()):
            if not isinstance(action.get(field), str) or not action[field]:
                raise ValueError()
        for field in ("reason", "question"):
            if field in action and (not isinstance(action[field], str) or len(action[field]) > 2000):
                raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise Error("invalid_coordinator_reply")
    return value


def wake(settings, store, provider, scheduler, goal, generation):
    text, event_ids = packet(settings, store, goal, generation)
    revision, snapshot = store.snapshot(goal)
    run = store.reserve_coordinator_run(goal, generation, len(text.encode()))
    value = None
    failure = None
    try:
        value = parse(provider.invoke(text, run), snapshot["id"], revision, generation)
        with store.transaction() as db:
            store._lease(db, goal, generation)
            current, _ = store._snapshot(db, goal)
            if current != revision:
                raise Error("stale_revision")
            db.execute("UPDATE coordinator_runs SET state='finished',ended=?,reply_valid=1,rationale=? WHERE id=?",
                       (store.clock(), value["rationale"], run))
            for event_id in event_ids:
                db.execute("UPDATE events SET consumed_at=? WHERE id=? AND goal=?", (store.clock(), event_id, goal))
    except (Error, OSError) as exc:
        failure = exc
        with store.transaction() as db:
            db.execute("UPDATE coordinator_runs SET state='failed',ended=?,reply_valid=0 WHERE id=?", (store.clock(), run))
            store._event(db, goal, "coordinator_failed", run)
        failures = store.rows("SELECT state FROM coordinator_runs WHERE goal=? ORDER BY started DESC LIMIT 2", (goal,))
        if len(failures) == 2 and all(row["state"] == "failed" for row in failures):
            observe.decision(store, goal, "coordinator_failed_twice")
    if failure:
        raise failure
    action = value["action"]
    kind = action["kind"]
    if kind != "wait" and kind not in snapshot["authority"]["allowed_actions"]:
        raise Error("action_not_allowed")
    if kind == "dispatch_assignment":
        try:
            row = dispatch.prepare(settings, store, goal, action.get("assignment"), generation, revision)
        except Error as exc:
            if exc.code != "parameter_unresolved":
                raise
            aid = action["assignment"]
            for parameter, spec in snapshot["assignments"][aid]["parameters"].items():
                if spec["authorization"] == "human_decision":
                    resolved = store.rows("SELECT 1 FROM decisions WHERE goal=? AND assignment=? AND parameter=? "
                                          "AND snapshot_revision=? AND state='resolved'", (goal, aid, parameter, revision))
                    if not resolved:
                        observe.decision(store, goal, "parameter_unresolved", aid, parameter,
                                         generation=generation, revision=revision)
                        return None
            raise
        row = dispatch.submit(settings, store, scheduler, row)
        if row["state"] in ("submitting", "submitted"):
            with store.transaction() as db:
                db.execute("UPDATE goal_state SET phase='waiting',waiting_reason='assignment_terminal' WHERE goal=? AND phase='running'", (goal,))
        return row
    if kind == "complete":
        return verify.complete(store, goal, generation, revision)
    if kind == "request_decision":
        return observe.decision(store, goal, "parameter_unresolved", action.get("assignment"), action.get("parameter"), action.get("question"),
                                generation=generation, revision=revision)
    with store.transaction() as db:
        store._commands(db, goal)
        store._lease(db, goal, generation)
        current, _ = store._snapshot(db, goal)
        if current != revision:
            raise Error("stale_revision")
        if store._balance(db, goal)["phase"] == "running":
            db.execute("UPDATE goal_state SET phase=?,waiting_reason=?,updated=? WHERE goal=?",
                       ("waiting" if kind == "wait" else "cancelled", action.get("reason", "assignment_terminal"), store.clock(), goal))
