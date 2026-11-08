"""Verify snapshot isolation, decision revision binding, and atomic projections."""
import json
from unittest import mock

from supervisor_fixtures import SupervisorTest
from dashboard.supervisor import goals


class GoalRecordTests(SupervisorTest):
    def test_authored_edit_does_not_change_imported_authority(self):
        self.payload["authority"]["allowed_actions"] = []
        self.write_records()
        row = self.reserve()
        self.assertEqual(row["snapshot_revision"], self.revision)
        self.store.confirm_submittable(row["request_id"])
        self.error(409, "submission_in_flight", goals.import_snapshot, self.settings, self.store, "alpha", "demo")

    def test_changed_revision_reopens_resolution_and_rejects_stale_command(self):
        self.assignments["a"]["parameters"] = {"pct": dict(authorization="human_decision", allowed_values=[98.0, 99.0])}
        self.update_snapshot()
        decision = self.decision()
        self.store.enqueue(self.goal, "resolve_decision", dict(decision_id=decision, value=99.0), "human", self.revision)
        self.store.apply_commands(self.goal)
        stale = self.revision
        pending = self.store.enqueue(self.goal, "pause", {}, "human", stale)
        self.payload["outcome"] += " with revised authority"
        self.update_snapshot()
        value = self.store.rows("SELECT * FROM decisions WHERE id=?", (decision,))[0]
        self.assertEqual(value["state"], "open")
        self.assertIsNone(value["resolved_value"])
        self.assertEqual(value["reason"], "snapshot_changed")
        self.assertEqual(value["snapshot_revision"], self.revision)
        self.store.apply_commands(self.goal)
        self.assertEqual(self.store.rows("SELECT reason FROM commands WHERE id=?", (pending,))[0]["reason"], "stale_revision")
        self.error(409, "stale_revision", self.store.enqueue, self.goal, "resolve_decision", dict(decision_id=decision, value=99.0), "human", stale)
        self.error(400, "value_not_allowed", self.store.enqueue, self.goal, "resolve_decision", dict(decision_id=decision, value=97.0), "human", self.revision)

    def test_publish_is_regenerated_and_stale_owner_cannot_publish(self):
        row = self.reserve()
        self.store.confirm_submittable(row["request_id"])
        value = goals.publish(self.settings, self.store, "alpha", "demo", self.generation)
        self.assertEqual(value["assignment_in_flight"], ["a"])
        self.assertEqual(value["held_cpu_hours"], 3)
        state = self.root_goal / "state.json"
        original = state.read_bytes()
        with mock.patch.object(goals.safety, "publish_replace", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                goals.publish(self.settings, self.store, "alpha", "demo", self.generation)
        self.assertEqual(state.read_bytes(), original)
        state.unlink()
        goals.publish(self.settings, self.store, "alpha", "demo", self.generation)
        self.assertEqual(state.read_bytes(), original)
        self.now += 301
        self.store.acquire_lease(self.goal, "replacement")
        self.error(409, "stale_generation", goals.publish, self.settings, self.store, "alpha", "demo", self.generation)
        self.assertEqual(state.read_bytes(), original)

    def test_invalid_records_and_symlinks_fail_closed(self):
        for value in (-1, float("nan"), True):
            self.payload["budget"]["cpu_hours"] = value
            self.write_records()
            with self.assertRaises(goals.safety.Error):
                goals.import_snapshot(self.settings, self.store, "alpha", "demo")
        path = self.root_goal / "goal.json"
        path.unlink()
        path.symlink_to(self.card)
        self.error(400, "unsafe_path", goals.load, self.settings, "alpha", "demo")

    def test_dependency_cycles_and_empty_acceptance_fail_closed(self):
        self.assignments["a"]["dependencies"] = ["b"]
        self.assignments["b"]["dependencies"] = ["a"]
        self.write_records()
        self.error(422, "invalid_goal_record", goals.load, self.settings, "alpha", "demo")
        self.assignments["a"]["dependencies"] = []
        self.assignments["a"]["acceptance"] = []
        self.write_records()
        self.error(422, "invalid_goal_record", goals.load, self.settings, "alpha", "demo")
