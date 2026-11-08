"""Goal read failures, conflicts, and per-refresh projection I/O."""
import json
from unittest import mock

from supervisor_fixtures import SupervisorTest
from dashboard.app import attention, cards, goals, server
from dashboard.supervisor import goals as records


class GoalCardTests(SupervisorTest):
    def setUp(self):
        super().setUp()
        self.projection = records.publish(self.settings, self.store, "alpha", "demo", self.generation)

    def test_corrupt_or_mismatched_projection_is_unknown_and_human_owned(self):
        for raw in ("{broken", json.dumps(dict(self.projection, id="other"))):
            with self.subTest(raw=raw):
                (self.root_goal / "state.json").write_text(raw)
                goal = goals.for_card(self.settings, "alpha", "question.md")
                self.assertEqual((goal["id"], goal["phase"]), ("demo", "unknown"))
                for verdict in (None, "met"):
                    result = attention.owner_and_next(dict(goal=goal, verdict=verdict))
                    self.assertEqual((result["owner"], result["next"]), ("you", "unknown"))

    def test_unreadable_binding_still_surfaces_on_project_cards(self):
        (self.root_goal / "state.json").write_text("broken")
        (self.root_goal / "goal.json").write_text("broken")
        goal = goals.for_card(self.settings, "alpha", "question.md")
        self.assertEqual(goal["phase"], "unknown")

    def test_conflicting_goals_carry_both_ids_and_project(self):
        other = self.root_goal.parent / "other"
        other.mkdir()
        (other / "state.json").write_text(json.dumps(dict(self.projection, id="other")))
        goal = goals.for_card(self.settings, "alpha", "question.md")
        self.assertEqual(goal["phase"], "decision_required")
        self.assertEqual(goal["project"], "alpha")
        self.assertEqual(goal["goal_ids"], ["demo", "other"])
        self.assertEqual([g["id"] for g in goal["goals"]], goal["goal_ids"])

    def test_enrich_reads_each_state_once_independent_of_card_count(self):
        for count in (1, 8):
            with self.subTest(count=count):
                batch = [cards.read_card(self.settings, "alpha", "question.md") for _ in range(count)]
                with mock.patch.object(records, "read_json", wraps=records.read_json) as read:
                    server.enrich(self.settings, "alpha", batch)
                states = [call for call in read.call_args_list if call.args[0].name == "state.json"]
                self.assertEqual(len(states), 1)
                self.assertTrue(all(card["goal"]["id"] == "demo" for card in batch))
