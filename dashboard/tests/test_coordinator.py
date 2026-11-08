"""Exercise bounded coordinator invocations and reply ownership checks offline."""
import json
from dataclasses import replace
from unittest import mock

from supervisor_fixtures import SupervisorTest
from dashboard.adapters.claude_cli import Claude
from dashboard.supervisor import coordinator
from dashboard.supervisor.store import Error


class CoordinatorTests(SupervisorTest):
    def test_configuration_directories_and_host_allowlist_reach_provider(self):
        from dashboard.app.config import Settings
        env = dict(RDASH_REPO_ROOT=str(self.repo), RESEARCH_DASH_CACHE=str(self.cache), CLAUDE_CONFIG_DIR="/tmp/claude-alt",
                   XDG_CONFIG_HOME="/tmp/config", COORDINATOR_ENV_ALLOWLIST="HOST_AUTH",
                   HOST_AUTH="fixture", UNTRUSTED="excluded")
        settings = Settings.from_env(env)
        run = mock.Mock(return_value=mock.Mock(returncode=0, stdout="ok"))
        Claude(settings, run=run, env=env).invoke("packet", "environment-test")
        actual = run.call_args.kwargs["env"]
        for name in ("CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "HOST_AUTH"):
            self.assertEqual(actual[name], env[name])
        self.assertNotIn("UNTRUSTED", actual)

    def test_provider_invocation_and_refusal_errors_are_distinct(self):
        run = mock.Mock(side_effect=FileNotFoundError("claude missing"))
        self.error(503, "provider_invocation_failed", Claude(self.settings, run=run).invoke, "packet", "missing")
        run = mock.Mock(return_value=mock.Mock(returncode=1))
        error = self.error(503, "provider_refused", Claude(self.settings, run=run).invoke, "packet", "refused")
        self.assertIn("status 1", str(error))

    def reply(self, **changes):
        value = dict(goal="demo", snapshot_revision=self.revision, generation=self.generation,
                     rationale="Wait for evidence", action=dict(kind="wait"))
        value.update(changes)
        return "```rdash-decision\n" + json.dumps(value) + "\n```\n"

    def test_invalid_wrong_goal_revision_and_generation(self):
        for reply in ("not JSON", self.reply(goal="wrong"), self.reply(snapshot_revision="stale"),
                      self.reply(generation=0), self.reply() + self.reply()):
            self.error(409, "invalid_coordinator_reply", coordinator.parse, reply, "demo", self.revision, self.generation)

    def test_wait_and_invalid_invocations_count(self):
        provider = mock.Mock()
        provider.invoke.return_value = self.reply()
        coordinator.wake(self.settings, self.store, provider, mock.Mock(), self.goal, self.generation)
        self.assertEqual(self.store.balance(self.goal)["phase"], "waiting")
        self.assertEqual(self.store.balance(self.goal)["coordinator_runs_used"], 1)
        self.store.enqueue(self.goal, "resume", {}, "human", self.revision)
        self.store.apply_commands(self.goal)
        self.now += 31
        provider.invoke.return_value = "bad"
        self.error(409, "invalid_coordinator_reply", coordinator.wake, self.settings, self.store, provider, mock.Mock(), self.goal, self.generation)
        self.assertEqual(self.store.balance(self.goal)["coordinator_runs_used"], 2)

    def test_packet_ceiling_is_error_not_truncation(self):
        settings = replace(self.settings, coordinator_packet_max_bytes=1)
        self.error(409, "packet_too_large", coordinator.packet, settings, self.store, self.goal, self.generation)
        self.assertEqual(self.store.balance(self.goal)["coordinator_runs_used"], 0)
        self.assertEqual(len(self.store.rows("SELECT * FROM events WHERE kind='packet_too_large'")), 1)

    def test_decision_request_counts_before_action(self):
        self.assignments["a"]["parameters"] = dict(pct=dict(authorization="human_decision", allowed_values=[99.0]))
        self.update_snapshot()
        provider = mock.Mock()
        provider.invoke.return_value = self.reply(action=dict(kind="request_decision", assignment="a", parameter="pct", question="Choose pct"))
        coordinator.wake(self.settings, self.store, provider, mock.Mock(), self.goal, self.generation)
        self.assertEqual(self.store.balance(self.goal)["coordinator_runs_used"], 1)
        self.assertEqual(self.store.balance(self.goal)["phase"], "decision_required")

    def test_stale_owner_cannot_publish_reply(self):
        provider = mock.Mock()
        def invoke(*args):
            self.now += 301
            self.store.acquire_lease(self.goal, "replacement")
            return self.reply()
        provider.invoke.side_effect = invoke
        self.error(409, "stale_generation", coordinator.wake, self.settings, self.store, provider, mock.Mock(), self.goal, self.generation)
        self.assertEqual(self.store.rows("SELECT rationale FROM coordinator_runs")[0]["rationale"], None)

    def test_cli_contract_scrubbed_environment_and_probe_not_goal_run(self):
        run = mock.Mock(return_value=mock.Mock(returncode=0, stdout="RDASH_NO_TOOLS"))
        provider = Claude(self.settings, run=run, env=dict(PATH="/bin", HOME="/tmp", UNTRUSTED="no"))
        provider.probe()
        provider.probe()
        self.assertEqual(run.call_count, 1)
        argv = run.call_args.args[0]
        self.assertEqual(argv[-2:], ["--tools", ""])
        self.assertNotIn("UNTRUSTED", run.call_args.kwargs["env"])
        self.assertNotEqual(run.call_args.kwargs["cwd"], str(self.repo))
        self.assertEqual(run.call_args.kwargs["timeout"], 180)
        self.assertEqual(self.store.balance(self.goal)["coordinator_runs_used"], 0)

    def test_sentinel_violation_refuses_startup(self):
        def run(argv, **kwargs):
            sentinel = next((self.cache / "supervisor").glob("sentinel-*"))
            return mock.Mock(returncode=0, stdout=sentinel.read_text())
        self.error(503, "sentinel_probe_failed", Claude(self.settings, run=run).probe)
