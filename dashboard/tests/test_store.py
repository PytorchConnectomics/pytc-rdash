"""Exercise authority and budget races against real SQLite transactions."""
import concurrent.futures
import sqlite3
import threading

from supervisor_fixtures import SupervisorTest
from dashboard.supervisor.store import Error, Store


class StoreTests(SupervisorTest):
    def test_schema_integrity_wal_and_forward_version_refusal(self):
        self.store.initialize()
        with self.store.connection() as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            db.execute("UPDATE schema_version SET version=2")
        self.error(503, "unsupported_schema", self.store.initialize)
        self.assertEqual(self.store.rows("SELECT version FROM schema_version"), [dict(version=2)])

    def race(self, budget, reason):
        self.payload["concurrency"] = 2
        self.payload["budget"].update(budget)
        self.update_snapshot()
        barrier = threading.Barrier(2)
        def run(aid):
            barrier.wait(timeout=5)
            try:
                return self.reserve(aid)["state"]
            except Error as exc:
                return exc.code
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            answers = list(pool.map(run, ("a", "b")))
        self.assertCountEqual(answers, ["reserved", reason])
        self.assertEqual(self.store.balance(self.goal)["held_jobs"], 1)
        self.assertEqual(self.store.balance(self.goal)["held_cpu_hours"], 3)

    def test_concurrent_cpu_reservations(self):
        self.race(dict(cpu_hours=3), "budget_cpu_hours")

    def test_concurrent_job_reservations_count_held(self):
        self.race(dict(jobs=1), "budget_jobs")

    def test_concurrency_is_enforced(self):
        self.reserve()
        self.error(409, "concurrency", self.reserve, "b")

    def test_duplicate_request_and_name_leave_one_reservation(self):
        self.payload["concurrency"] = 2
        self.update_snapshot()
        row = self.reserve()
        self.error(409, "duplicate_identity", self.reserve, "b", request_id=row["request_id"])
        self.error(409, "duplicate_identity", self.reserve, "b", job_name=row["job_name"])
        self.assertEqual(len(self.store.rows("SELECT * FROM dispatches")), 1)
        self.assertEqual(self.store.balance(self.goal)["held_jobs"], 1)

    def test_pending_pause_commits_even_when_reservation_refused(self):
        command = self.store.enqueue(self.goal, "pause", {}, "human", self.revision)
        self.error(409, "paused", self.reserve)
        self.assertEqual(self.store.balance(self.goal)["phase"], "paused")
        self.assertEqual(self.store.rows("SELECT state FROM commands WHERE id=?", (command,))[0]["state"], "applied")
        self.assertEqual(self.store.rows("SELECT payload FROM events WHERE kind='dispatch_refused'")[0]["payload"], '{"reason":"paused"}')

    def test_confirm_pause_releases_without_submitting(self):
        row = self.reserve()
        self.store.enqueue(self.goal, "pause", {}, "human", self.revision)
        self.error(409, "paused", self.store.confirm_submittable, row["request_id"])
        refused = self.store.dispatch(row["request_id"])
        self.assertEqual(refused["state"], "refused")
        self.assertIsNone(refused["submitting_at"])
        self.assertEqual(self.store.balance(self.goal)["held_jobs"], 0)

    def test_confirm_snapshot_and_lease_refuse(self):
        row = self.reserve()
        self.payload["budget"]["cpu_hours"] = 11
        self.update_snapshot()
        self.error(409, "stale_revision", self.store.confirm_submittable, row["request_id"])
        row = self.reserve()
        self.now += 301
        self.error(409, "stale_generation", self.store.confirm_submittable, row["request_id"])
        self.assertEqual(self.store.balance(self.goal)["held_jobs"], 0)

    def test_confirm_commits_boundary_and_never_confirms_twice(self):
        row = self.reserve()
        confirmed = self.store.confirm_submittable(row["request_id"])
        self.assertEqual(confirmed["state"], "submitting")
        self.assertEqual(confirmed["submitting_at"], self.now)
        self.error(409, "not_reserved", self.store.confirm_submittable, row["request_id"])
        self.assertEqual(self.store.balance(self.goal)["held_jobs"], 1)

    def test_dependency_parameter_and_authority_refusals(self):
        self.assignments["b"]["dependencies"] = ["a"]
        self.assignments["a"]["parameters"] = {"pct": dict(authorization="human_decision", allowed_values=[99.0])}
        self.update_snapshot()
        self.error(409, "dependency_unverified", self.reserve, "b")
        self.error(409, "parameter_unresolved", self.reserve)
        decision = self.decision()
        self.store.enqueue(self.goal, "resolve_decision", dict(decision_id=decision, value=99.0), "human", self.revision)
        row = self.reserve()
        self.assertEqual(row["parameters"], dict(pct=99.0))
        self.error(409, "already_dispatched", self.reserve)

    def test_stale_generation_and_expired_lease(self):
        self.error(409, "stale_generation", self.reserve, generation=0)
        self.error(409, "lease_held", self.store.acquire_lease, self.goal, "other")
        self.now += 301
        generation = self.store.acquire_lease(self.goal, "other")
        self.assertGreater(generation, self.generation)
        self.error(409, "stale_generation", self.reserve)

    def test_durable_reopen_and_event_coalescing(self):
        row = self.reserve()
        reopened = Store(self.store.path)
        self.assertEqual(reopened.dispatch(row["request_id"])["state"], "reserved")
        self.store.event(self.goal, "observation", "a")
        self.store.event(self.goal, "observation", "a")
        self.assertEqual(len(self.store.rows("SELECT * FROM events WHERE kind='observation'")), 1)

    def test_authority_is_required(self):
        self.payload["authority"]["allowed_actions"] = []
        self.update_snapshot()
        self.error(409, "action_not_allowed", self.reserve)


class CoordinatorReservationTests(SupervisorTest):
    def test_every_invocation_spends_before_reply_and_crash_still_counts(self):
        run = self.store.reserve_coordinator_run(self.goal, self.generation, 42)
        self.assertEqual(self.store.balance(self.goal)["coordinator_runs_used"], 1)
        self.store.recover_coordinators()
        self.assertEqual(self.store.rows("SELECT state FROM coordinator_runs WHERE id=?", (run,))[0]["state"], "crashed")
        self.assertEqual(self.store.balance(self.goal)["coordinator_runs_used"], 1)

    def test_rate_interval_inflight_and_exhaustion(self):
        run = self.store.reserve_coordinator_run(self.goal, self.generation, 42)
        self.error(409, "coordinator_in_flight", self.store.reserve_coordinator_run, self.goal, self.generation, 42)
        with self.store.transaction() as db:
            db.execute("UPDATE coordinator_runs SET state='finished' WHERE id=?", (run,))
        self.error(409, "wake_interval", self.store.reserve_coordinator_run, self.goal, self.generation, 42)
        self.now += 31
        self.error(409, "wake_rate", self.store.reserve_coordinator_run, self.goal, self.generation, 42, wakes_per_hour=1)
        self.payload["budget"]["coordinator_runs"] = 1
        self.update_snapshot()
        self.error(409, "coordinator_runs", self.store.reserve_coordinator_run, self.goal, self.generation, 42)
        self.assertEqual(self.store.balance(self.goal)["phase"], "exhausted")

    def test_waiting_and_consumed_events_do_not_wake(self):
        with self.store.transaction() as db:
            db.execute("UPDATE events SET consumed_at=?", (self.now,))
        self.error(409, "no_events", self.store.reserve_coordinator_run, self.goal, self.generation, 42)
        with self.store.transaction() as db:
            db.execute("UPDATE goal_state SET phase='waiting'")
        self.error(409, "waiting", self.store.reserve_coordinator_run, self.goal, self.generation, 42)
