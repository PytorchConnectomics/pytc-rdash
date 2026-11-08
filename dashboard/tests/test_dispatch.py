"""Verify submission boundaries and scheduler accounting with injected adapters."""
from unittest import mock

from supervisor_fixtures import SupervisorTest
from dashboard.supervisor import dispatch, observe
from dashboard.adapters.slurm import Slurm


class DispatchTests(SupervisorTest):
    def test_pending_pause_never_calls_submit(self):
        self.assignments["a"].update(memory="32G", partition="short")
        self.update_snapshot()
        row = self.reserve()
        self.store.enqueue(self.goal, "pause", {}, "human", self.revision)
        scheduler = mock.Mock()
        scheduler.lookup_by_name.return_value = []
        self.error(409, "paused", dispatch.submit, self.settings, self.store, scheduler, row)
        scheduler.submit.assert_not_called()
        self.assertEqual(self.store.balance(self.goal)["held_jobs"], 0)

    def submitted(self):
        row = self.reserve()
        self.store.confirm_submittable(row["request_id"])
        observe.adopt(self.store, row["request_id"], "123")
        return self.store.dispatch(row["request_id"])

    def test_unknown_observation_and_missing_accounting_stay_held(self):
        row = self.submitted()
        scheduler = mock.Mock()
        scheduler.settle.return_value = None
        probe = lambda *args: ({123: dict(reduced="unknown")}, "failed")
        observed = observe.reconcile(self.store, scheduler, row, probe=probe)
        self.assertEqual(observed["state"], "submitted")
        self.assertEqual(observed["observed_state"], "unknown")
        self.now += 901
        observed = observe.reconcile(self.store, scheduler, observed, probe=probe)
        self.assertEqual(observed["refuse_reason"], "unsettled")
        self.assertEqual(self.store.balance(self.goal)["held_jobs"], 1)
        self.assertEqual(self.store.balance(self.goal)["consumed_jobs"], 0)

    def test_allocation_overrun_charged_once(self):
        row = self.submitted()
        scheduler = mock.Mock()
        scheduler.settle.return_value = dict(state="COMPLETED", cpu_hours=13, alloc_cpus=48)
        probe = lambda *args: ({123: dict(reduced="COMPLETED")}, "ok")
        row = observe.reconcile(self.store, scheduler, row, probe=probe)
        observe.reconcile(self.store, scheduler, row, probe=probe)
        balance = self.store.balance(self.goal)
        self.assertEqual(balance["consumed_cpu_hours"], 13)
        self.assertEqual(balance["consumed_jobs"], 1)
        self.assertEqual(balance["held_jobs"], 0)
        self.assertEqual(balance["phase"], "exhausted")

    def test_sacct_main_record_only_and_elapsed(self):
        exchange = mock.Mock(return_value=(b"123.batch|COMPLETED|00:10:00|100\n123.extern|COMPLETED|00:10:00|100\n123|FAILED|00:30:00|8\n", "ok"))
        row = Slurm("test", exchange).settle("123")
        self.assertEqual(row["state"], "FAILED")
        self.assertEqual(row["cpu_hours"], 4)
        exchange.return_value = (b"123.batch|COMPLETED|00:10:00|100\n", "ok")
        self.assertIsNone(Slurm("test", exchange).settle("123"))

    def test_retry_limit_applies_inside_reserve(self):
        row = self.submitted()
        with self.store.transaction() as db:
            db.execute("UPDATE dispatches SET state='terminal',observed_state='TIMEOUT'")
            db.execute("UPDATE reservations SET released=1")
        second = self.reserve()
        with self.store.transaction() as db:
            db.execute("UPDATE dispatches SET state='terminal',observed_state='NODE_FAIL'")
            db.execute("UPDATE reservations SET released=1")
        self.error(409, "retry_not_allowed", self.reserve)
