"""Exercise guarded goal routes through HTTP bytes without binding a socket."""
import io
import json
from unittest import mock

from supervisor_fixtures import SupervisorTest
from dashboard.app import server
from dashboard.supervisor import goals


class GoalApiTests(SupervisorTest):
    def setUp(self):
        super().setUp()
        goals.publish(self.settings, self.store, "alpha", "demo", self.generation)
        self.handlers = []
        self.server = mock.Mock(server_address=("127.0.0.1", 8766))
        def make(address, handler):
            self.handlers.append(handler)
            return self.server
        with mock.patch.object(server, "ThreadingHTTPServer", side_effect=make):
            server.make_server(self.settings)

    def request(self, method, path, data=None, host="localhost:8766", origin=None, header=True):
        body = json.dumps(data).encode() if data else b""
        headers = [method + " " + path + " HTTP/1.0", "Host: " + host,
                   "Content-Type: application/json", "Content-Length: " + str(len(body))]
        if header:
            headers.append("X-Rdash: 1")
        if origin:
            headers.append("Origin: " + origin)
        class Connection:
            def __init__(self):
                self.input = io.BytesIO(("\r\n".join(headers) + "\r\n\r\n").encode() + body)
                self.output = bytearray()
            def makefile(self, *args, **kwargs):
                return self.input
            def sendall(self, value):
                self.output.extend(value)
            def settimeout(self, timeout):
                pass
        connection = Connection()
        self.handlers[0](connection, ("127.0.0.1", 1), self.server)
        response, raw = bytes(connection.output).split(b"\r\n\r\n", 1)
        return int(response.split()[1]), json.loads(raw)

    def test_get_and_revision_bound_command(self):
        status, value = self.request("GET", "/api/goal?project=alpha&goal=demo")
        self.assertEqual(status, 200)
        self.assertIn("assignment_in_flight", value)
        self.assertIn("next_event", value)
        data = dict(project="alpha", goal="demo", kind="pause", goal_revision=self.revision)
        self.assertEqual(self.request("POST", "/api/goal/command", data)[0], 200)
        data["goal_revision"] = "stale"
        self.assertEqual(self.request("POST", "/api/goal/command", data)[0], 409)

    def test_routes_keep_host_origin_and_mutation_header_guards(self):
        for method, path in (("GET", "/api/goal?project=alpha&goal=demo"), ("POST", "/api/goal/command")):
            self.assertEqual(self.request(method, path, host="evil.example")[0], 403)
            self.assertEqual(self.request(method, path, origin="https://evil.example")[0], 403)
        self.assertEqual(self.request("POST", "/api/goal/command", {}, header=False)[0], 403)

    def test_out_of_range_decision_value_is_rejected(self):
        self.assignments["a"]["parameters"] = dict(pct=dict(authorization="human_decision", allowed_values=[99.0]))
        self.update_snapshot()
        decision = self.decision()
        data = dict(project="alpha", goal="demo", kind="resolve_decision", goal_revision=self.revision,
                    payload=dict(decision_id=decision, value=98.0))
        status, result = self.request("POST", "/api/goal/command", data)
        self.assertEqual((status, result["error"]), (400, "value_not_allowed"))

    def test_resolution_is_bound_to_displayed_goal_revision(self):
        self.assignments["a"]["parameters"] = dict(pct=dict(authorization="human_decision", allowed_values=[99.0]))
        self.update_snapshot()
        decision = self.decision()
        data = dict(project="alpha", goal="demo", kind="resolve_decision", goal_revision="stale",
                    payload=dict(decision_id=decision, value=99.0))
        status, result = self.request("POST", "/api/goal/command", data)
        self.assertEqual((status, result["error"]), (409, "stale_revision"))
        data["goal_revision"] = self.revision
        status, result = self.request("POST", "/api/goal/command", data)
        self.assertEqual((status, result["state"]), (200, "pending"))
        self.store.apply_commands(self.goal)
        resolved = self.store.rows("SELECT state,resolved_value FROM decisions WHERE id=?", (decision,))[0]
        self.assertEqual((resolved["state"], json.loads(resolved["resolved_value"])), ("resolved", 99.0))

    def test_goal_free_card_keeps_exact_existing_sessions_and_shape(self):
        from dashboard.app import cards, jobs
        (self.root_goal / "state.json").unlink()
        self.card.write_text(self.card.read_text() + '\n```probe-status\n{"sessions":[{"label":"Authored session","provider":"claude"}]}\n```\n')
        card = cards.read_card(self.settings, "alpha", "question.md")
        expected = jobs.declared_sessions(card["body"])
        actual = server.enrich(self.settings, "alpha", [card])[0]
        self.assertEqual(json.dumps(actual["sessions"]), json.dumps(expected))
        self.assertNotIn("goal", actual)
