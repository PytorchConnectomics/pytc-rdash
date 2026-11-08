"""Exercise crash windows without ever submitting a real scheduler job."""
from unittest import mock

from supervisor_fixtures import SupervisorTest
from dashboard.supervisor import dispatch, observe


class RecoveryTests(SupervisorTest):
    def test_accepted_submission_is_adopted_without_resubmit(self):
        row = self.reserve()
        row = self.store.confirm_submittable(row["request_id"])
        scheduler = mock.Mock()
        scheduler.lookup_by_name.return_value = [dict(job_id="456")]
        recovered = observe.recover_identity(self.store, scheduler, row)
        self.assertEqual(recovered["state"], "submitted")
        self.assertEqual(recovered["job_id"], "456")
        self.assertEqual(recovered["submitting_at"], row["submitting_at"])
        scheduler.submit.assert_not_called()

    def test_zero_and_multiple_matches_are_unknown_with_held_budget(self):
        self.payload["concurrency"] = 2
        self.update_snapshot()
        for aid, matches in (("a", []), ("b", [dict(job_id="1"), dict(job_id="2")])):
            with self.store.transaction() as db:
                db.execute("UPDATE goal_state SET phase='running'")
            row = self.reserve(aid)
            row = self.store.confirm_submittable(row["request_id"])
            scheduler = mock.Mock()
            scheduler.lookup_by_name.return_value = matches
            recovered = observe.recover_identity(self.store, scheduler, row)
            self.assertEqual(recovered["state"], "unknown")
            scheduler.submit.assert_not_called()
        self.assertEqual(self.store.balance(self.goal)["held_jobs"], 2)
        self.assertEqual(len(self.store.rows("SELECT * FROM decisions WHERE state='open'")), 2)

    def test_reserved_crash_window_submits_once(self):
        self.assignments["a"].update(memory="32G", partition="short")
        self.update_snapshot()
        row = self.reserve()
        scheduler = mock.Mock()
        scheduler.lookup_by_name.return_value = []
        scheduler.submit.return_value = "123"
        row = dispatch.submit(self.settings, self.store, scheduler, row)
        dispatch.submit(self.settings, self.store, scheduler, row)
        scheduler.submit.assert_called_once()
        self.assertEqual(row["job_id"], "123")

    def test_human_can_adopt_or_confirm_no_submission(self):
        row = self.store.confirm_submittable(self.reserve()["request_id"])
        scheduler = mock.Mock()
        scheduler.lookup_by_name.return_value = []
        observe.recover_identity(self.store, scheduler, row)
        decision = self.store.rows("SELECT id FROM decisions WHERE state='open'")[0]["id"]
        self.store.enqueue(self.goal, "resolve_decision", dict(decision_id=decision, value=dict(action="adopt", job_id="456")), "human", self.revision)
        self.store.apply_commands(self.goal)
        self.assertEqual(self.store.dispatch(row["request_id"])["job_id"], "456")
        self.assertEqual(self.store.balance(self.goal)["held_jobs"], 1)
        scheduler.submit.assert_not_called()

    def test_human_confirmation_releases_ambiguous_reservation(self):
        row = self.store.confirm_submittable(self.reserve()["request_id"])
        scheduler = mock.Mock()
        scheduler.lookup_by_name.return_value = []
        observe.recover_identity(self.store, scheduler, row)
        decision = self.store.rows("SELECT id FROM decisions WHERE state='open'")[0]["id"]
        self.store.enqueue(self.goal, "resolve_decision", dict(decision_id=decision, value=dict(action="confirm_not_submitted")), "human", self.revision)
        self.store.apply_commands(self.goal)
        self.assertEqual(self.store.dispatch(row["request_id"])["state"], "refused")
        self.assertEqual(self.store.balance(self.goal)["held_jobs"], 0)
        self.assertEqual(self.reserve()["state"], "reserved")

    def test_collision_releases_and_requests_fresh_identity(self):
        row = self.reserve()
        scheduler = mock.Mock()
        scheduler.lookup_by_name.return_value = [dict(job_id="unrelated")]
        with mock.patch.object(dispatch, "prepare", return_value=dict(request_id="fresh")) as prepare:
            value = dispatch.submit(self.settings, self.store, scheduler, row)
        self.assertEqual(value["request_id"], "fresh")
        prepare.assert_called_once()
        scheduler.submit.assert_not_called()
        self.assertEqual(self.store.dispatch(row["request_id"])["refuse_reason"], "name_collision")
        self.assertEqual(self.store.balance(self.goal)["held_jobs"], 0)
