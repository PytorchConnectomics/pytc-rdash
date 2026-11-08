"""Transactional authority, reservations, and execution accounting."""
import json
import math
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from dashboard.app.safety import Error as SafetyError


class Error(SafetyError):
    def __init__(self, code, message=None, status=409, **details):
        super().__init__(status, code, message or code.replace("_", " "), **details)
        self.code = code


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


SCHEMA = """
CREATE TABLE schema_version(version INTEGER NOT NULL);
INSERT INTO schema_version VALUES (1);
CREATE TABLE goal_snapshots(goal TEXT, revision TEXT, payload TEXT NOT NULL,
 imported_at REAL NOT NULL, PRIMARY KEY(goal, revision));
CREATE TABLE goal_state(goal TEXT PRIMARY KEY, phase TEXT NOT NULL,
 next_action TEXT, waiting_reason TEXT, last_progress REAL,
 consumed_cpu_hours REAL NOT NULL DEFAULT 0, consumed_jobs INTEGER NOT NULL DEFAULT 0,
 coordinator_runs_used INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL,
 snapshot_revision TEXT NOT NULL);
CREATE TABLE events(id INTEGER PRIMARY KEY, goal TEXT NOT NULL, kind TEXT NOT NULL,
 subject TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL, consumed_at REAL);
CREATE UNIQUE INDEX pending_event ON events(goal, kind, subject) WHERE consumed_at IS NULL;
CREATE TABLE leases(goal TEXT PRIMARY KEY, owner TEXT NOT NULL, generation INTEGER NOT NULL,
 acquired REAL NOT NULL, expires REAL NOT NULL);
CREATE TABLE dispatches(request_id TEXT PRIMARY KEY, goal TEXT NOT NULL,
 assignment TEXT NOT NULL, attempt TEXT UNIQUE NOT NULL, snapshot_revision TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('reserved','submitting','submitted','terminal','unknown','refused')),
 job_name TEXT UNIQUE NOT NULL, job_id TEXT, cpus INTEGER NOT NULL, time_limit_s INTEGER NOT NULL,
 inputs_digest TEXT NOT NULL, outputs_declared TEXT NOT NULL, created REAL NOT NULL,
 submitting_at REAL, submitted_at REAL, observed_state TEXT, observed_at REAL,
 terminal_at REAL, refuse_reason TEXT, generation INTEGER NOT NULL,
 command TEXT NOT NULL, parameters TEXT NOT NULL);
CREATE TABLE reservations(request_id TEXT PRIMARY KEY REFERENCES dispatches(request_id),
 goal TEXT NOT NULL, cpu_hours REAL NOT NULL, jobs INTEGER NOT NULL,
 settled_cpu_hours REAL, released INTEGER NOT NULL DEFAULT 0);
CREATE TABLE decisions(id TEXT PRIMARY KEY, goal TEXT NOT NULL, assignment TEXT,
 parameter TEXT, question TEXT NOT NULL, recommendation TEXT, alternatives TEXT NOT NULL,
 evidence TEXT NOT NULL, expected_cost TEXT NOT NULL, snapshot_revision TEXT NOT NULL,
 created REAL NOT NULL, state TEXT NOT NULL CHECK(state IN ('open','resolved','withdrawn')),
 resolved_value TEXT, resolved_by TEXT, resolved_at REAL, reason TEXT);
CREATE TABLE commands(id TEXT PRIMARY KEY, goal TEXT NOT NULL, kind TEXT NOT NULL,
 payload TEXT NOT NULL, author TEXT NOT NULL, goal_revision TEXT NOT NULL,
 created REAL NOT NULL, state TEXT NOT NULL, applied_at REAL, reason TEXT);
CREATE TABLE receipts(attempt TEXT PRIMARY KEY, request_id TEXT NOT NULL,
 digest TEXT NOT NULL, imported_at REAL NOT NULL, verdict TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE evidence(id INTEGER PRIMARY KEY, goal TEXT NOT NULL, assignment TEXT NOT NULL,
 criterion TEXT NOT NULL, status TEXT NOT NULL, receipt_attempt TEXT NOT NULL REFERENCES receipts(attempt),
 checked_at REAL NOT NULL, detail TEXT NOT NULL,
 UNIQUE(goal, assignment, criterion, receipt_attempt));
CREATE TABLE coordinator_runs(id TEXT PRIMARY KEY, goal TEXT NOT NULL,
 generation INTEGER NOT NULL, started REAL NOT NULL, ended REAL, state TEXT NOT NULL,
 exit_code INTEGER, reply_valid INTEGER, rationale TEXT, packet_bytes INTEGER NOT NULL);
"""


class Store:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.clock = clock

    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise Error("runtime_store_lost", status=503)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            try:
                found = db.execute("SELECT 1 FROM sqlite_master WHERE name='schema_version'").fetchone()
                if not found:
                    # executescript commits implicitly; individual statements keep migration atomic.
                    for statement in SCHEMA.split(";"):
                        if statement.strip():
                            db.execute(statement)
                version = db.execute("SELECT version FROM schema_version").fetchall()
                if len(version) != 1 or version[0][0] != 1:
                    raise Error("unsupported_schema", status=503)
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @contextmanager
    def connection(self):
        db = self.connect()
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def rows(self, query, args=()):
        with self.connection() as db:
            return [dict(row) for row in db.execute(query, args)]

    def _snapshot(self, db, goal):
        row = db.execute("SELECT s.* FROM goal_snapshots s JOIN goal_state g "
                         "ON s.goal=g.goal AND s.revision=g.snapshot_revision WHERE g.goal=?", (goal,)).fetchone()
        if row is None:
            raise Error("unknown_goal", status=404)
        return row["revision"], json.loads(row["payload"])

    def snapshot(self, goal):
        with self.connection() as db:
            return self._snapshot(db, goal)

    def _event(self, db, goal, kind, subject, payload=None):
        db.execute("INSERT OR IGNORE INTO events(goal,kind,subject,payload,created) VALUES(?,?,?,?,?)",
                   (goal, kind, subject, encode(payload or {}), self.clock()))

    def event(self, goal, kind, subject, payload=None):
        with self.transaction() as db:
            self._event(db, goal, kind, subject, payload)

    def import_snapshot(self, goal, revision, payload):
        with self.transaction() as db:
            old = db.execute("SELECT snapshot_revision FROM goal_state WHERE goal=?", (goal,)).fetchone()
            if old and old[0] == revision:
                return
            if db.execute("SELECT 1 FROM dispatches WHERE goal=? AND state='submitting'", (goal,)).fetchone():
                raise Error("submission_in_flight")
            now = self.clock()
            db.execute("INSERT OR IGNORE INTO goal_snapshots VALUES(?,?,?,?)", (goal, revision, encode(payload), now))
            db.execute("INSERT INTO goal_state(goal,phase,updated,snapshot_revision) VALUES(?,'paused',?,?) "
                       "ON CONFLICT(goal) DO UPDATE SET snapshot_revision=excluded.snapshot_revision,updated=excluded.updated",
                       (goal, now, revision))
            db.execute("UPDATE decisions SET state='open',snapshot_revision=?,resolved_value=NULL,"
                       "resolved_by=NULL,resolved_at=NULL,reason='snapshot_changed' "
                       "WHERE goal=? AND parameter IS NOT NULL AND state IN ('open','resolved')", (revision, goal))
            db.execute("UPDATE decisions SET snapshot_revision=? WHERE goal=? AND parameter IS NULL AND state='open'", (revision, goal))
            if db.execute("SELECT 1 FROM decisions WHERE goal=? AND state='open'", (goal,)).fetchone():
                db.execute("UPDATE goal_state SET phase='decision_required' WHERE goal=? AND phase!='paused'", (goal,))
            self._event(db, goal, "snapshot_changed", revision)

    def acquire_lease(self, goal, owner, duration=300):
        with self.transaction() as db:
            self._snapshot(db, goal)
            now = self.clock()
            old = db.execute("SELECT * FROM leases WHERE goal=?", (goal,)).fetchone()
            if old and old["expires"] > now and old["owner"] != owner:
                raise Error("lease_held")
            generation = old["generation"] if old and old["owner"] == owner and old["expires"] > now else (old["generation"] + 1 if old else 1)
            db.execute("INSERT INTO leases VALUES(?,?,?,?,?) ON CONFLICT(goal) DO UPDATE SET "
                       "owner=excluded.owner,generation=excluded.generation,acquired=excluded.acquired,expires=excluded.expires",
                       (goal, owner, generation, now, now + duration))
            return generation

    def _lease(self, db, goal, generation):
        row = db.execute("SELECT * FROM leases WHERE goal=?", (goal,)).fetchone()
        if row is None or row["generation"] != generation or row["expires"] <= self.clock():
            raise Error("stale_generation")

    def enqueue(self, goal, kind, payload, author, revision):
        if kind not in ("pause", "resume", "resolve_decision"):
            raise Error("invalid_command", status=400)
        with self.transaction() as db:
            current, snapshot = self._snapshot(db, goal)
            if revision != current:
                raise Error("stale_revision")
            if kind == "resolve_decision":
                self._resolution(db, goal, current, snapshot, payload)
            identifier = str(uuid.uuid4())
            db.execute("INSERT INTO commands VALUES(?,?,?,?,?,?,?,'pending',NULL,NULL)",
                       (identifier, goal, kind, encode(payload), author, revision, self.clock()))
            return identifier

    def _resolution(self, db, goal, revision, snapshot, payload):
        row = db.execute("SELECT * FROM decisions WHERE id=? AND goal=?", (payload.get("decision_id"), goal)).fetchone()
        if row is None or row["state"] != "open":
            raise Error("decision_not_open")
        if row["snapshot_revision"] != revision:
            raise Error("stale_revision")
        if row["reason"] == "ambiguous_submission":
            value = payload.get("value")
            if not isinstance(value, dict) or value.get("action") not in ("adopt", "confirm_not_submitted", "abandon"):
                raise Error("value_not_allowed", status=400)
            if value["action"] == "adopt" and not re.fullmatch(r"[1-9][0-9]*", str(value.get("job_id", ""))):
                raise Error("value_not_allowed", status=400)
            if not db.execute("SELECT 1 FROM dispatches WHERE goal=? AND assignment=? AND state='unknown'",
                              (goal, row["assignment"])).fetchone():
                raise Error("no_unknown_dispatch")
            return row
        parameter = snapshot["assignments"].get(row["assignment"], {}).get("parameters", {}).get(row["parameter"], {})
        if parameter.get("authorization") != "human_decision":
            raise Error("decision_requires_reconciliation")
        if "value" not in payload or encode(payload["value"]) not in [encode(v) for v in parameter["allowed_values"]]:
            raise Error("value_not_allowed", status=400)
        return row

    def _commands(self, db, goal):
        revision, snapshot = self._snapshot(db, goal)
        for cmd in db.execute("SELECT * FROM commands WHERE goal=? AND state='pending' ORDER BY created,rowid", (goal,)).fetchall():
            reason = None
            try:
                if cmd["goal_revision"] != revision:
                    raise Error("stale_revision")
                phase = db.execute("SELECT phase FROM goal_state WHERE goal=?", (goal,)).fetchone()[0]
                if phase in ("achieved", "cancelled"):
                    raise Error("terminal_goal")
                if cmd["kind"] == "pause":
                    db.execute("UPDATE goal_state SET phase='paused' WHERE goal=?", (goal,))
                elif cmd["kind"] == "resume":
                    if db.execute("SELECT 1 FROM decisions WHERE goal=? AND state='open'", (goal,)).fetchone():
                        raise Error("decision_required")
                    db.execute("UPDATE goal_state SET phase='running' WHERE goal=?", (goal,))
                else:
                    payload = json.loads(cmd["payload"])
                    row = self._resolution(db, goal, revision, snapshot, payload)
                    db.execute("UPDATE decisions SET state='resolved',resolved_value=?,resolved_by=?,resolved_at=? WHERE id=?",
                               (encode(payload["value"]), cmd["author"], self.clock(), row["id"]))
                    if row["reason"] == "ambiguous_submission":
                        unknown = db.execute("SELECT request_id FROM dispatches WHERE goal=? AND assignment=? AND state='unknown'",
                                             (goal, row["assignment"])).fetchone()[0]
                        action = payload["value"]["action"]
                        if action == "adopt":
                            db.execute("UPDATE dispatches SET state='submitted',job_id=?,submitted_at=?,refuse_reason=NULL WHERE request_id=?",
                                       (str(payload["value"]["job_id"]), self.clock(), unknown))
                        elif action == "confirm_not_submitted":
                            db.execute("UPDATE dispatches SET state='refused',refuse_reason='human_confirmed_not_submitted' WHERE request_id=?", (unknown,))
                            db.execute("UPDATE reservations SET released=1 WHERE request_id=?", (unknown,))
                        else:
                            db.execute("UPDATE goal_state SET phase='cancelled',waiting_reason='abandoned_unknown_dispatch' WHERE goal=?", (goal,))
                    if not db.execute("SELECT 1 FROM decisions WHERE goal=? AND state='open'", (goal,)).fetchone():
                        db.execute("UPDATE goal_state SET phase='running' WHERE goal=? AND phase='decision_required'", (goal,))
                        if db.execute("SELECT 1 FROM dispatches WHERE goal=? AND state IN ('submitting','submitted')", (goal,)).fetchone():
                            db.execute("UPDATE goal_state SET phase='waiting',waiting_reason='assignment_terminal' WHERE goal=? AND phase='running'", (goal,))
                self._event(db, goal, "command_applied", cmd["id"])
            except Error as exc:
                reason = exc.code
            db.execute("UPDATE commands SET state=?,applied_at=?,reason=? WHERE id=?",
                       ("rejected" if reason else "applied", self.clock(), reason, cmd["id"]))
        db.execute("UPDATE goal_state SET updated=? WHERE goal=?", (self.clock(), goal))

    def apply_commands(self, goal):
        with self.transaction() as db:
            self._commands(db, goal)

    def _parameters(self, db, goal, aid, assignment, revision):
        values = {}
        for name, spec in assignment.get("parameters", {}).items():
            if spec["authorization"] == "preauthorized" and "value" in spec:
                values[name] = spec["value"]
            elif spec["authorization"] == "human_decision":
                row = db.execute("SELECT resolved_value FROM decisions WHERE goal=? AND assignment=? AND parameter=? "
                                 "AND snapshot_revision=? AND state='resolved' ORDER BY resolved_at DESC LIMIT 1",
                                 (goal, aid, name, revision)).fetchone()
                if row is None or row[0] not in [encode(v) for v in spec["allowed_values"]]:
                    raise Error("parameter_unresolved")
                values[name] = json.loads(row[0])
            else:
                raise Error("parameter_unresolved")
        return values

    def _verified(self, db, goal, aid, assignment):
        criteria = set(assignment["acceptance"])
        # All criteria must belong to ONE accepted receipt, not fragments of failed attempts.
        attempts = db.execute("SELECT e.receipt_attempt,e.criterion FROM evidence e JOIN receipts r ON r.attempt=e.receipt_attempt "
                              "WHERE e.goal=? AND e.assignment=? AND e.status='verified' AND r.verdict='verified'", (goal, aid))
        grouped = {}
        for row in attempts:
            grouped.setdefault(row[0], set()).add(row[1])
        return bool(criteria) and any(criteria <= found for found in grouped.values())

    def _balance(self, db, goal):
        state = dict(db.execute("SELECT * FROM goal_state WHERE goal=?", (goal,)).fetchone())
        held = db.execute("SELECT COALESCE(SUM(cpu_hours),0),COALESCE(SUM(jobs),0) FROM reservations "
                          "WHERE goal=? AND released=0", (goal,)).fetchone()
        unsettled = db.execute("SELECT COALESCE(SUM(r.cpu_hours),0) FROM reservations r JOIN dispatches d ON d.request_id=r.request_id "
                               "WHERE r.goal=? AND r.released=0 AND d.refuse_reason='unsettled'", (goal,)).fetchone()[0]
        return dict(state, held_cpu_hours=held[0], held_jobs=held[1], unsettled_cpu_hours=unsettled)

    def balance(self, goal):
        with self.connection() as db:
            self._snapshot(db, goal)
            return self._balance(db, goal)

    def reserve(self, goal, aid, generation, request_id, job_name, attempt,
                inputs, outputs, command, revision):
        error = None
        with self.transaction() as db:
            self._commands(db, goal)
            try:
                current, snapshot = self._snapshot(db, goal)
                state = self._balance(db, goal)
                if state["phase"] != "running":
                    raise Error(state["phase"])
                self._lease(db, goal, generation)
                if revision != current:
                    raise Error("stale_revision")
                if "dispatch_assignment" not in snapshot["authority"]["allowed_actions"]:
                    raise Error("action_not_allowed")
                assignment = snapshot["assignments"].get(aid)
                if assignment is None:
                    raise Error("unknown_assignment")
                if self._verified(db, goal, aid, assignment):
                    raise Error("already_verified")
                if db.execute("SELECT 1 FROM dispatches WHERE goal=? AND assignment=? AND state NOT IN ('terminal','refused')", (goal, aid)).fetchone():
                    raise Error("already_dispatched")
                prior = db.execute("SELECT observed_state FROM dispatches WHERE goal=? AND assignment=? AND state='terminal'", (goal, aid)).fetchall()
                if len(prior) >= 2 or any(row[0] not in ('TIMEOUT', 'NODE_FAIL') for row in prior):
                    raise Error("retry_not_allowed")
                for dependency in assignment.get("dependencies", []):
                    if not self._verified(db, goal, dependency, snapshot["assignments"][dependency]):
                        raise Error("dependency_unverified")
                parameters = self._parameters(db, goal, aid, assignment, current)
                cpus, seconds = assignment["cpus"], assignment["time_limit_s"]
                reserved = cpus * seconds / 3600
                if not math.isfinite(reserved) or reserved <= 0:
                    raise Error("invalid_resources")
                if state["consumed_jobs"] + state["held_jobs"] + 1 > snapshot["budget"]["jobs"]:
                    raise Error("budget_jobs")
                if state["consumed_cpu_hours"] + state["held_cpu_hours"] + reserved > snapshot["budget"]["cpu_hours"]:
                    raise Error("budget_cpu_hours")
                if state["held_jobs"] >= snapshot["concurrency"]:
                    raise Error("concurrency")
                db.execute("INSERT INTO dispatches(request_id,goal,assignment,attempt,snapshot_revision,state,job_name,"
                           "cpus,time_limit_s,inputs_digest,outputs_declared,created,generation,command,parameters) "
                           "VALUES(?,?,?,?,?,'reserved',?,?,?,?,?,?,?,?,?)",
                           (request_id, goal, aid, attempt, current, job_name, cpus, seconds, encode(inputs), encode(outputs),
                            self.clock(), generation, encode(command), encode(parameters)))
                db.execute("INSERT INTO reservations(request_id,goal,cpu_hours,jobs) VALUES(?,?,?,1)", (request_id, goal, reserved))
                self._event(db, goal, "reserved", request_id)
            except (Error, sqlite3.IntegrityError) as exc:
                error = exc if isinstance(exc, Error) else Error("duplicate_identity")
                if error.code in ("budget_jobs", "budget_cpu_hours"):
                    db.execute("UPDATE goal_state SET phase='exhausted',waiting_reason=? WHERE goal=?", (error.code, goal))
                self._event(db, goal, "dispatch_refused", request_id, {"reason": error.code})
        if error:
            raise error
        return self.dispatch(request_id)

    def dispatch(self, request_id):
        rows = self.rows("SELECT * FROM dispatches WHERE request_id=?", (request_id,))
        if not rows:
            raise Error("unknown_dispatch", status=404)
        row = rows[0]
        for name in ("inputs_digest", "outputs_declared", "command", "parameters"):
            row[name] = json.loads(row[name])
        return row

    def confirm_submittable(self, request_id):
        error = None
        with self.transaction() as db:
            row = db.execute("SELECT * FROM dispatches WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise Error("unknown_dispatch", status=404)
            if row["state"] != "reserved":
                raise Error("not_reserved")
            self._commands(db, row["goal"])
            try:
                current, snapshot = self._snapshot(db, row["goal"])
                state = self._balance(db, row["goal"])
                if state["phase"] != "running":
                    raise Error(state["phase"])
                if current != row["snapshot_revision"]:
                    raise Error("stale_revision")
                self._lease(db, row["goal"], row["generation"])
                if "dispatch_assignment" not in snapshot["authority"]["allowed_actions"]:
                    raise Error("action_not_allowed")
                for field in ("jobs", "cpu_hours"):
                    if state["consumed_" + field] + state["held_" + field] > snapshot["budget"][field]:
                        raise Error("budget_" + field)
                db.execute("UPDATE dispatches SET state='submitting',submitting_at=? WHERE request_id=?", (self.clock(), request_id))
            except Error as exc:
                error = exc
                db.execute("UPDATE dispatches SET state='refused',refuse_reason=? WHERE request_id=?", (exc.code, request_id))
                db.execute("UPDATE reservations SET released=1 WHERE request_id=?", (request_id,))
                self._event(db, row["goal"], "dispatch_refused", request_id, {"reason": exc.code})
        if error:
            raise error
        return self.dispatch(request_id)

    def reserve_coordinator_run(self, goal, generation, packet_bytes,
                                min_seconds_between_wakes=30, wakes_per_hour=12):
        error = None
        identifier = str(uuid.uuid4())
        with self.transaction() as db:
            self._commands(db, goal)
            try:
                self._lease(db, goal, generation)
                _, snapshot = self._snapshot(db, goal)
                state = self._balance(db, goal)
                if state["phase"] != "running":
                    raise Error(state["phase"])
                if not db.execute("SELECT 1 FROM events WHERE goal=? AND consumed_at IS NULL", (goal,)).fetchone():
                    raise Error("no_events")
                if state["coordinator_runs_used"] >= snapshot["budget"]["coordinator_runs"]:
                    db.execute("UPDATE goal_state SET phase='exhausted',waiting_reason='coordinator_runs' WHERE goal=?", (goal,))
                    raise Error("coordinator_runs")
                now = self.clock()
                runs = db.execute("SELECT started,state FROM coordinator_runs WHERE goal=? AND started>?", (goal, now - 3600)).fetchall()
                if db.execute("SELECT 1 FROM coordinator_runs WHERE goal=? AND state='running'", (goal,)).fetchone():
                    raise Error("coordinator_in_flight")
                if runs and now - max(row[0] for row in runs) < min_seconds_between_wakes:
                    raise Error("wake_interval")
                if len(runs) >= wakes_per_hour:
                    raise Error("wake_rate")
                db.execute("INSERT INTO coordinator_runs(id,goal,generation,started,state,packet_bytes) VALUES(?,?,?,?,'running',?)",
                           (identifier, goal, generation, now, packet_bytes))
                db.execute("UPDATE goal_state SET coordinator_runs_used=coordinator_runs_used+1,updated=? WHERE goal=?", (now, goal))
            except Error as exc:
                error = exc
        if error:
            raise error
        return identifier

    def recover_coordinators(self):
        with self.transaction() as db:
            for row in db.execute("SELECT * FROM coordinator_runs WHERE state='running'").fetchall():
                db.execute("UPDATE coordinator_runs SET state='crashed',ended=? WHERE id=?", (self.clock(), row["id"]))
                self._event(db, row["goal"], "coordinator_crashed", row["id"])
