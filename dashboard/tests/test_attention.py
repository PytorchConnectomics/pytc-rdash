import unittest

from dashboard.app.attention import owner_and_next


def record(**overrides):
    base = dict(read_only=False, verdict=None, jobs=[], artifacts=[],
                contract=dict(declared=True, structure="pass", missing_facts=0),
                acceptance=dict(declared=True, total=2, settled=2),
                sessions=dict(declared=False))
    base.update(overrides)
    return base


class AttentionTests(unittest.TestCase):
    def next(self, **overrides):
        derived = owner_and_next(record(**overrides))
        return derived["next"], derived["owner"]

    def test_unresolved_contract_outranks_every_later_signal(self):
        # A settled acceptance list on an unresolved contract is not a verdict
        # prompt: the references it rests on have not resolved.
        self.assertEqual(
            self.next(contract=dict(declared=True, structure="fail", missing_facts=0)),
            ("fix_contract", "agent"))

    def test_settled_acceptance_asks_a_person_for_the_verdict(self):
        self.assertEqual(self.next(), ("record_verdict", "you"))

    def test_running_job_belongs_to_the_scheduler(self):
        self.assertEqual(self.next(jobs=[dict(state="RUNNING")]), ("wait", "scheduler"))

    def test_unknown_job_state_needs_a_person_not_the_scheduler(self):
        # An unreachable scheduler is a real answer and must not sort as closed.
        self.assertEqual(self.next(jobs=[dict(state="unknown")],
                                   acceptance=dict(declared=True, total=2, settled=1)),
                         ("unknown", "you"))

    def test_finished_job_does_not_settle_acceptance(self):
        self.assertEqual(self.next(jobs=[dict(state="COMPLETED")],
                                   acceptance=dict(declared=True, total=2, settled=1)),
                         ("read_evidence", "agent"))

    def test_verdict_closes_the_row_only_when_execution_state_is_resolved(self):
        self.assertEqual(self.next(verdict="met"), ("closed", "none"))
        self.assertEqual(self.next(verdict="met", jobs=[dict(state="RUNNING")]),
                         ("verdict_recorded_state_unresolved", "you"))

    def test_prose_acceptance_is_not_checkable(self):
        self.assertEqual(self.next(acceptance=dict(declared=False, total=0, settled=0)),
                         ("make_acceptance_checkable", "you"))

    def test_unreadable_frontmatter_comes_first(self):
        self.assertEqual(self.next(read_only=True,
                                   contract=dict(declared=True, structure="fail", missing_facts=0)),
                         ("fix_frontmatter", "agent"))

    def test_declared_session_does_not_hide_missing_facts_or_claim_liveness(self):
        self.assertEqual(self.next(
            contract=dict(declared=True, structure="pass", missing_facts=1),
            acceptance=dict(declared=True, total=2, settled=0),
            sessions=dict(declared=True, items=[dict(label="Old worker")])),
            ("supply_facts", "agent"))
        self.assertEqual(self.next(
            acceptance=dict(declared=True, total=2, settled=0),
            sessions=dict(declared=True, items=[dict(label="Old worker")])),
            ("read_evidence", "agent"))

    def test_routing_evidence_work_does_not_approve_a_verdict_or_new_criteria(self):
        self.assertEqual(self.next(
            acceptance=dict(declared=True, total=2, settled=1)),
            ("read_evidence", "agent"))
        self.assertEqual(self.next(), ("record_verdict", "you"))
        self.assertEqual(self.next(acceptance=dict(declared=False)),
                         ("make_acceptance_checkable", "you"))


class GoalAttentionTests(unittest.TestCase):
    def test_three_human_rules_and_contract_precedence(self):
        for phase, action in (("decision_required", "resolve_decision"), ("paused", "resume_or_redirect"),
                              ("exhausted", "raise_budget_or_close")):
            value = record(goal=dict(phase=phase), jobs=[dict(state="RUNNING")])
            self.assertEqual(owner_and_next(value)["next"], action)
            self.assertEqual(owner_and_next(value)["owner"], "you")
            value["contract"]["structure"] = "unknown"
            self.assertEqual(owner_and_next(value)["next"], "contract_unknown")

    def test_running_goal_preserves_existing_mixed_state_order(self):
        from dashboard.app.goals import augment_sessions
        goal = dict(phase="running", coordinator_in_flight=True)
        value = record(goal=goal, acceptance=dict(declared=True, total=2, settled=0),
                       sessions=augment_sessions(dict(declared=False), goal))
        self.assertEqual(owner_and_next(value)["next"], "in_session")
        value["artifacts"] = [dict(state="unknown")]
        self.assertEqual(owner_and_next(value)["next"], "unknown")
        value["verdict"] = "met"
        self.assertEqual(owner_and_next(value)["next"], "verdict_recorded_state_unresolved")
        value["artifacts"] = []
        self.assertEqual(owner_and_next(value)["next"], "closed")
        value["verdict"] = None
        value["jobs"] = [dict(state="RUNNING")]
        self.assertEqual(owner_and_next(value), dict(next="wait", owner="scheduler", reason="Jobs are running or queued"))

    def test_declared_sessions_are_preserved_and_waiting_is_not_liveness(self):
        import json
        from dashboard.app.goals import augment_sessions
        from dashboard.app.jobs import declared_sessions
        for body in ('', '```probe-status\n{"sessions":[{"label":"existing"}]}\n```'):
            parsed = declared_sessions(body)
            before = json.dumps(parsed)
            self.assertIs(augment_sessions(parsed, None), parsed)
            self.assertEqual(json.dumps(parsed), before)
            mixed = augment_sessions(parsed, dict(phase="running", coordinator_in_flight=True))
            self.assertEqual(mixed["items"][:-1], parsed["items"])
            self.assertEqual(mixed["items"][-1]["source"], "goal")
            self.assertTrue(mixed["running"])
            self.assertFalse(augment_sessions(parsed, dict(phase="waiting"))["running"])
            self.assertEqual(json.dumps(parsed), before)


if __name__ == "__main__":
    unittest.main()
