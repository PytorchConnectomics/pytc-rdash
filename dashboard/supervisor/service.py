"""Own the supervisor lifecycle and advance goals only on durable external events."""
import json
import fcntl
import os
import signal
import socket
import sqlite3
import time
import uuid
from datetime import datetime, timezone

from dashboard.app import safety, inspection
from . import coordinator, dispatch, goals, observe, verify
from .store import Error, Store, encode


class ProjectLock:
    def __init__(self, settings, project, owner, store=None):
        self.settings, self.owner = settings, owner
        self.store, self.project = store, project
        self.path = safety.resolve_within(settings.repo_root, "projects", project, ".agent-lock")
        self.held = False

    def acquire(self):
        with safety.writer_lock(self.settings):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                old = json.loads(self.path.read_text())
                known = self.store.rows("SELECT goal FROM leases WHERE owner=? AND goal LIKE ?",
                                        (old.get("session_id"), self.project + "/%")) if self.store else []
                pid = old.get("pid")
                if not known or old.get("task") != "rdash supervisor" or old.get("host") != socket.gethostname() or type(pid) is not int or pid <= 1:
                    raise Error("project_locked", status=423)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    # A dead, known local owner plus an intact store permits reconciliation;
                    # age alone never permits taking a foreign project's lock.
                    with self.store.transaction() as db:
                        db.execute("UPDATE leases SET expires=? WHERE owner=? AND goal LIKE ?",
                                   (self.store.clock(), old["session_id"], self.project + "/%"))
                    self.path.unlink()
                    fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                else:
                    raise Error("project_locked", status=423)
            with os.fdopen(fd, "wb") as stream:
                stream.write(self._data())
                stream.flush()
                os.fsync(stream.fileno())
            self.held = True

    def _data(self):
        return encode(dict(session_id=self.owner, started=datetime.now(timezone.utc).isoformat(),
                           task="rdash supervisor", pid=os.getpid(), host=socket.gethostname())).encode()

    def refresh(self):
        with safety.writer_lock(self.settings):
            if json.loads(self.path.read_text()).get("session_id") != self.owner:
                self.held = False
                raise Error("project_lock_lost")
            safety.publish_replace(self.path, self._data())

    def release(self):
        if self.held:
            with safety.writer_lock(self.settings):
                if self.path.exists() and json.loads(self.path.read_text()).get("session_id") == self.owner:
                    self.path.unlink()
            self.held = False


class Service:
    def __init__(self, settings, provider, scheduler, store=None, probe=inspection.probe_jobs):
        self.settings, self.provider, self.scheduler = settings, provider, scheduler
        self.store = store or Store(settings.supervisor_db)
        self.owner = "rdash-" + uuid.uuid4().hex
        self.locks = {}
        self.started = False
        self.stopping = False
        self.probe = probe
        self.runtime_lock = None

    def authored(self):
        for path in sorted((self.settings.repo_root / "projects").glob("*/goals/*/goal.json")):
            project, goal = path.parents[2].name, path.parent.name
            goals.directory(self.settings, project, goal)
            yield project, goal

    def start(self):
        lock_path = safety.cache_path(self.settings, "supervisor", "service.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_lock = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.runtime_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self.runtime_lock)
            self.runtime_lock = None
            raise Error("supervisor_already_running")
        lost = not self.store.path.exists()
        if not lost:
            try:
                with self.store.connection() as db:
                    lost = db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            except sqlite3.DatabaseError:
                lost = True
        if lost:
            outstanding = []
            for project, goal in self.authored():
                path = safety.resolve_within(goals.directory(self.settings, project, goal), "state.json")
                if path.exists():
                    value, _ = goals.read_json(path)
                    if any(row["state"] not in ("terminal", "refused") for row in value.get("dispatches", [])):
                        outstanding.append((path, value))
            if outstanding:
                with safety.writer_lock(self.settings):
                    for path, value in outstanding:
                        value.update(phase="decision_required", waiting_reason="runtime_store_lost",
                                     pending_decisions=[dict(reason="runtime_store_lost", question="Restore runtime.db or explicitly reconcile and write off outstanding work.")])
                        safety.publish_replace(path, (encode(value) + "\n").encode())
                raise Error("runtime_store_lost", status=503)
            if self.store.path.exists():
                raise Error("runtime_store_lost", status=503)
        self.store.initialize()
        self.provider.probe()
        self.store.recover_coordinators()
        self.started = True
        safety.publish_replace(safety.cache_path(self.settings, "supervisor", "ready.json"),
                               encode(dict(pid=os.getpid(), owner=self.owner, probe="pass", started=self.store.clock())).encode())

    def pass_once(self):
        if not self.started:
            self.start()
        for project, goal_id in self.authored():
            goal = goals.key(project, goal_id)
            try:
                try:
                    goals.import_snapshot(self.settings, self.store, project, goal_id)
                except Error as exc:
                    if exc.code != "submission_in_flight":
                        raise
                self.store.apply_commands(goal)
                state = self.store.balance(goal)
                outstanding = self.store.rows("SELECT request_id FROM dispatches WHERE goal=? AND state NOT IN ('terminal','refused')", (goal,))
                if project not in self.locks:
                    lock = ProjectLock(self.settings, project, self.owner, self.store)
                    lock.acquire()
                    self.locks[project] = lock
                self.locks[project].refresh()
                generation = self.store.acquire_lease(goal, self.owner, self.settings.coordinator_timeout_s + 120)
                for item in outstanding:
                    row = self.store.dispatch(item["request_id"])
                    if row["state"] == "reserved":
                        try:
                            with self.store.transaction() as db:
                                self.store._lease(db, goal, generation)
                                db.execute("UPDATE dispatches SET generation=? WHERE request_id=? AND state='reserved'", (generation, row["request_id"]))
                            row = self.store.dispatch(row["request_id"])
                            row = dispatch.submit(self.settings, self.store, self.scheduler, row)
                            if row["state"] in ("submitting", "submitted"):
                                with self.store.transaction() as db:
                                    db.execute("UPDATE goal_state SET phase='waiting',waiting_reason='assignment_terminal' WHERE goal=? AND phase='running'", (goal,))
                        except Error as exc:
                            self.store.event(goal, "dispatch_refused", row["request_id"], {"reason": exc.code})
                    else:
                        row = observe.reconcile(self.store, self.scheduler, row, probe=self.probe, settle_window=self.settings.settle_window_s)
                _, snapshot = self.store.snapshot(goal)
                terminals = self.store.rows("SELECT d.request_id FROM dispatches d LEFT JOIN receipts r ON r.attempt=d.attempt "
                                            "WHERE d.goal=? AND d.state='terminal' AND r.attempt IS NULL AND NOT EXISTS "
                                            "(SELECT 1 FROM dispatches newer WHERE newer.goal=d.goal AND newer.assignment=d.assignment "
                                            "AND newer.rowid>d.rowid AND newer.state!='refused')", (goal,))
                for item in terminals:
                    row = self.store.dispatch(item["request_id"])
                    receipt = dispatch.attempt_directory(self.settings, row) / "receipt.json"
                    if row["observed_state"] in ("TIMEOUT", "NODE_FAIL"):
                        count = self.store.rows("SELECT COUNT(*) AS n FROM dispatches WHERE goal=? AND assignment=? AND state='terminal'", (goal, row["assignment"]))[0]["n"]
                        if count < 2:
                            with self.store.transaction() as db:
                                db.execute("UPDATE goal_state SET phase='running' WHERE goal=? AND phase='waiting'", (goal,))
                            continue
                    if not receipt.is_file():
                        observe.decision(self.store, goal, "receipt_missing", row["assignment"])
                        continue
                    verdict = verify.import_receipt(self.store, row, snapshot["assignments"][row["assignment"]], receipt)
                    if verdict != "verified":
                        observe.decision(self.store, goal, "evidence_rejected", row["assignment"])
                    else:
                        with self.store.transaction() as db:
                            db.execute("UPDATE goal_state SET phase='running',waiting_reason=NULL,last_progress=? WHERE goal=? AND phase='waiting'", (self.store.clock(), goal))
                if self.store.balance(goal)["phase"] == "running":
                    try:
                        coordinator.wake(self.settings, self.store, self.provider, self.scheduler, goal, generation)
                    except Error as exc:
                        if exc.code not in ("wake_interval", "wake_rate", "no_events", "coordinator_runs", "coordinator_failed", "invalid_coordinator_reply", "budget_jobs", "budget_cpu_hours"):
                            observe.decision(self.store, goal, exc.code)
                goals.publish(self.settings, self.store, project, goal_id, generation)
                final_state = self.store.balance(goal)
                if final_state["phase"] in ("paused", "achieved", "cancelled", "exhausted", "decision_required") and not final_state["held_jobs"]:
                    self.locks.pop(project).release()
            except (Error, safety.Error, OSError, ValueError) as exc:
                if self.store.rows("SELECT goal FROM goal_state WHERE goal=?", (goal,)):
                    self.store.event(goal, "supervisor_error", getattr(exc, "code", type(exc).__name__), {"message": str(exc)})

    def close(self):
        for lock in self.locks.values():
            lock.release()
        self.locks.clear()
        ready = safety.cache_path(self.settings, "supervisor", "ready.json")
        if ready.is_file() and json.loads(ready.read_text()).get("owner") == self.owner:
            ready.unlink()
        if self.runtime_lock is not None:
            os.close(self.runtime_lock)
            self.runtime_lock = None

    def run(self):
        def stop(signum, frame):
            self.stopping = True
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            self.start()
            while not self.stopping:
                self.pass_once()
                time.sleep(self.settings.supervisor_poll_s)
        finally:
            self.close()
