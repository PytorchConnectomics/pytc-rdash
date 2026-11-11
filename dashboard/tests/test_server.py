import http.client
import concurrent.futures
import json
import socket
import threading
from dataclasses import replace
from urllib.parse import urlencode

from fixtures import RepoTest
from dashboard.app.server import make_server


class ServerTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.start_server()
        self.addCleanup(self.stop_server)

    def start_server(self):
        self.server = make_server(self.settings)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, data=None, headers=None, raw=None):
        body = json.dumps(data) if raw is None and data is not None else raw
        values = {"Content-Type": "application/json", "X-Rdash": "1"}
        if headers:
            values.update(headers)
        values = {key: value for key, value in values.items() if value is not None}
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=values)
            response = connection.getresponse()
            content = response.read()
            self.assertIsNone(response.getheader("Access-Control-Allow-Origin"))
            return response.status, content
        finally:
            connection.close()

    def test_endpoints_and_persistent_restart(self):
        for path in ("/", "/static/index.html", "/static/app.js", "/static/styles.css", "/api/health", "/api/projects", "/api/cards?project=alpha", "/api/card?project=alpha&card=question.md"):
            self.assertEqual(self.request("GET", path)[0], 200, path)
        status, raw = self.request("POST", "/api/idea", dict(project="beta", title="New question"))
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)["metadata"]["project"], "beta")
        status, raw = self.request("GET", "/api/card?project=alpha&card=question.md")
        card = json.loads(raw)
        request = dict(project="alpha", card=card["card"], revision=card["revision"], stage="probing")
        self.assertEqual(self.request("POST", "/api/stage", request)[0], 200)
        self.assertEqual(self.request("POST", "/api/stage", request)[0], 409)
        self.stop_server()
        self.start_server()
        status, raw = self.request("GET", "/api/card?project=alpha&card=question.md")
        self.assertEqual(json.loads(raw)["metadata"]["stage"], "probing")
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_plan_and_summary_routes(self):
        for path in ("/plan/ladder", "/plan/daily", "/plan/weekly", "/plan/daily?d=2026-11-05", "/plan/weekly?w=bad", "/summary", "/static/planner.css", "/static/planner.js"):
            status, raw = self.request("GET", path)
            self.assertEqual(status, 200, path)
        self.assertIn(b'<nav class="modes">', self.request("GET", "/")[1])
        self.assertEqual(self.request("GET", "/summary/view?p=../LADDER.md")[0], 400)
        self.assertEqual(self.request("GET", "/summary/view?p=plan/summary/none.md")[0], 404)
        day = "plan/days/2026-11-09.md"
        self.assertEqual(self.request("POST", "/api/plan/new", dict(path=day, projects=["alpha"]))[0], 200)
        self.assertEqual(self.request("POST", "/api/plan/new", dict(path=day, projects="alpha"))[0], 400)
        self.assertEqual(self.request("POST", "/api/plan/new", dict(path="plan/days/../x.md"))[0], 400)
        self.assertEqual(self.request("POST", "/api/plan/new", dict(path=day), {"X-Rdash": None})[0], 403)
        (self.repo / day).write_text((self.repo / day).read_text() + "- [ ] item\n")
        line = (self.repo / day).read_text().split("\n").index("- [ ] item")
        self.assertEqual(self.request("POST", "/api/plan/edit", dict(path=day, line=line, orig="- [ ] item", op="toggle"))[0], 200)
        self.assertEqual(self.request("POST", "/api/plan/edit", dict(path=day, line=line, orig="- [ ] item", op="toggle"))[0], 409)
        self.assertIn(b'data-orig="- [x] item"', self.request("GET", "/plan/daily?d=2026-11-09")[1])

    def test_request_guards(self):
        for method in ("GET", "POST"):
            for host in ("evil.example", "127.0.0.1:1", "localhost:1"):
                self.assertEqual(self.request(method, "/api/health", {}, {"Host": host})[0], 403)
            for origin in ("http://evil.example", "http://127.0.0.1:1", "null"):
                self.assertEqual(self.request(method, "/api/health", {}, {"Origin": origin})[0], 403)
        self.assertEqual(self.request("GET", "/api/health", headers={"Origin": "http://localhost:" + str(self.port)})[0], 200)
        # Read the wire: http.client deliberately hides illegal HEAD bodies.
        for host in ("127.0.0.1:" + str(self.port), "evil.example"):
            with socket.create_connection(("127.0.0.1", self.port), timeout=5) as sock:
                sock.sendall(("HEAD /api/health HTTP/1.0\r\nHost: " + host + "\r\n\r\n").encode())
                with sock.makefile("rb") as response:
                    headers, body = response.read().split(b"\r\n\r\n", 1)
            self.assertTrue(headers.startswith(b"HTTP/1.0 403"))
            self.assertEqual(body, b"")
        self.assertEqual(self.request("OPTIONS", "/api/idea")[0], 403)
        self.assertEqual(self.request("PUT", "/api/idea")[0], 403)
        self.assertEqual(self.request("TRACE", "/api/health")[0], 403)
        self.assertEqual(self.request("CONNECT", "/api/health", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("POST", "/api/idea", {}, {"X-Rdash": None})[0], 403)
        self.assertEqual(self.request("POST", "/api/idea", {}, {"Content-Type": "text/plain"})[0], 400)
        self.assertEqual(self.request("POST", "/api/idea", raw="x" * 65536)[0], 400)
        self.assertEqual(self.request("POST", "/api/idea", raw="{")[0], 400)
        self.assertEqual(self.request("POST", "/api/idea", raw="[" * 1500 + "]" * 1500)[0], 400)
        self.assertEqual(self.request("POST", "/api/idea", data=[])[0], 400)
        self.assertEqual(self.request("POST", "/api/idea", data={"project": [], "title": "Title"})[0], 400)

    def test_eight_simultaneous_http_saves(self):
        _, raw = self.request("GET", "/api/card?project=alpha&card=question.md")
        revision = json.loads(raw)["revision"]
        barrier = threading.Barrier(8)
        def save(_):
            barrier.wait(timeout=5)
            return self.request("POST", "/api/stage", dict(project="alpha", card="question.md", revision=revision, stage="probing"))[0]
        with concurrent.futures.ThreadPoolExecutor(8) as pool:
            statuses = list(pool.map(save, range(8)))
        self.assertEqual(statuses.count(200), 1)
        self.assertTrue(all(status in (200, 409, 503) for status in statuses))

    def test_path_whitelist_and_project_isolation(self):
        for path in ("/static/../server.py", "/static/no.js", "/projects/alpha/cards/question.md", "/static/%2e%2e/server.py"):
            self.assertEqual(self.request("GET", path)[0], 404)
        self.assertEqual(self.request("GET", "/api/card?project=beta&card=question.md")[0], 404)
        self.assertEqual(self.request("GET", "/api/cards?project=../alpha")[0], 400)
        self.assertEqual(self.request("GET", "/api/card?project=alpha&card=inbox/../../question.md")[0], 400)
        self.assertEqual(self.request("GET", "/api/cards?project=alpha&project=beta")[0], 400)

    def test_evidence_preview_feedback_and_stale_revision(self):
        from dashboard.app import cards
        self.stop_server()
        self.settings = replace(self.settings, stat_local=True)
        self.start_server()
        artifact = self.repo / "projects/alpha/results/qc.md"
        artifact.parent.mkdir()
        artifact.write_text("# Boundary QC\nInspect the false merge.\n")
        self.card.write_text(self.card.read_text() + "\n```probe-status\n" +
                             json.dumps(dict(artifacts={"QC": str(artifact)})) + "\n```\n")
        revision = cards.read_card(self.settings, "alpha", "question.md")["revision"]
        request = dict(project="alpha", card="question.md", revision=revision, label="QC")
        url = "/api/evidence?" + urlencode(request)
        status, raw = self.request("GET", url)
        self.assertEqual(status, 200, raw)
        preview = json.loads(raw)
        self.assertEqual(preview["text"], artifact.read_text())
        status, raw = self.request("POST", "/api/evidence/feedback", dict(request,
            artifact_revision=preview["artifact_revision"], text="Please inspect the boundary."))
        self.assertEqual(status, 200, raw)
        updated = json.loads(raw)
        self.assertIn("Evidence feedback", updated["body"])
        self.assertIn("attention", updated)
        self.assertNotEqual(updated["revision"], revision)
        self.assertEqual(self.request("GET", url)[0], 409)
        self.assertEqual(self.request("GET", "/api/evidence?" + urlencode(dict(request, path="/etc/passwd")))[0], 409)

    def test_evidence_image_content_keeps_same_origin_security_headers(self):
        from dashboard.app import cards
        from test_evidence import png
        self.stop_server()
        self.settings = replace(self.settings, stat_local=True)
        self.start_server()
        artifact = self.repo / "projects/alpha/results/qc.png"
        artifact.parent.mkdir()
        artifact.write_bytes(png())
        self.card.write_text(self.card.read_text() + "\n```probe-status\n" +
                             json.dumps(dict(artifacts={"QC": str(artifact)})) + "\n```\n")
        revision = cards.read_card(self.settings, "alpha", "question.md")["revision"]
        _, raw = self.request("GET", "/api/evidence?" + urlencode(dict(project="alpha", card="question.md", revision=revision, label="QC")))
        preview = json.loads(raw)
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("GET", preview["content_url"])
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"), "image/png")
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
            self.assertIn("default-src 'self'", response.getheader("Content-Security-Policy"))
            self.assertEqual(response.read(), artifact.read_bytes())
        finally:
            connection.close()
        self.assertEqual(self.request("GET", preview["content_url"], headers={"Origin": "http://evil.example"})[0], 403)


class HandlerInspectionTests(RepoTest):
    """Exercise HTTP bytes through the real handler without a listening socket."""
    def test_ladder_focus_and_health_owner(self):
        import io
        from unittest import mock
        import dashboard.app.server as module

        (self.repo / 'LADDER.md').write_text(
            '## Rungs\n| Month | Rung | G1 | G2 | G3 |\n'
            '| --- | --- | --- | --- | --- |\n'
            '| 2026-11 | 50um | [met] ran | target | — |\n')
        focus = self.repo / 'projects/alpha/focus/F-001.md'
        focus.parent.mkdir()
        focus.write_text('# Notebook\nDecision needed: inspect\n## Next\n- [ ] review\n')
        config = self.repo / 'projects/config'
        config.mkdir()
        (config / 'rdash-owner.json').write_text('{"require_owner": true}')
        self.settings = replace(self.settings, owner='alice')
        captured = []
        class DummyServer:
            server_address = ('127.0.0.1', 8766)
        def construct(address, handler):
            captured.append(handler)
            return DummyServer()
        with mock.patch.object(module, 'ThreadingHTTPServer', side_effect=construct):
            server = module.make_server(self.settings)
        class Connection:
            def __init__(self, path):
                self.input = io.BytesIO(('GET ' + path + ' HTTP/1.0\r\nHost: localhost:8766\r\n\r\n').encode())
                self.output = bytearray()
            def makefile(self, *args, **kwargs):
                return self.input
            def sendall(self, value):
                self.output.extend(value)
        def get(path):
            connection = Connection(path)
            captured[0](connection, ('127.0.0.1', 1), server)
            headers, raw = bytes(connection.output).split(b'\r\n\r\n', 1)
            self.assertTrue(headers.startswith(b'HTTP/1.0 200'), raw)
            return json.loads(raw)
        ladder = get('/api/ladder')
        self.assertFalse(ladder['missing'])
        self.assertEqual(ladder['rows'][0]['gates_met'], 1)
        notebook = get('/api/focus?project=alpha')['notebooks'][0]
        self.assertEqual((notebook['id'], notebook['decision']), ('F-001', 'inspect'))
        self.assertEqual(notebook['next'], [dict(text='review', done=False)])
        health = get('/api/health')
        self.assertEqual((health['owner'], health['require_owner']), ('alice', True))

    def test_api_observation_matrix_and_declared_code_never_executes(self):
        import io
        import itertools
        from dataclasses import replace
        from unittest import mock
        from dashboard.app import inspection
        import dashboard.app.server as module
        self.settings = replace(self.settings, stat_local=True)
        metric = self.repo / 'projects/alpha/results/script.json'
        metric.parent.mkdir()
        marker = self.root / 'executed'
        metric.write_text('#!/bin/sh\ntouch ' + str(marker))
        metric.chmod(0o700)
        self.card.write_text(self.card.read_text().replace('stage: idea', 'stage: idea\nverdict: met') +
            '\n## Acceptance\n- [x] Done — evidence: results/script.json\n' +
            '<!-- radd-status:begin -->\nold snapshot\n<!-- radd-status:end -->\n' +
            '```probe-status\n' + json.dumps(dict(jobs=[123, '1;touch ' + str(marker)],
                artifacts={'blocker':'/fixture/blocker'}, results=[dict(name='script', path='results/script.json', key='x')])) + '\n```\n')
        original = self.card.read_bytes()
        captured = []
        class DummyServer:
            server_address = ('127.0.0.1', 8766)
        def construct(address, handler):
            captured.append(handler)
            return DummyServer()
        with mock.patch.object(module, 'ThreadingHTTPServer', side_effect=construct):
            server = module.make_server(self.settings)
        class Connection:
            def __init__(self, raw):
                self.input = io.BytesIO(raw)
                self.output = bytearray()
            def makefile(self, *args, **kwargs):
                return self.input
            def sendall(self, value):
                self.output.extend(value)
        for job, artifact in itertools.product(('COMPLETED','FAILED','unknown'), ('present','absent','unknown')):
            inspection._cache.clear()
            original_channel = inspection._channel
            def channel(host, kind, items, **kwargs):
                if kind == 'content':
                    return original_channel(host, kind, items, **kwargs)
                return ([dict(tasks={'123':dict(state=job, elapsed='', reason='')}, reduced=job) if kind == 'jobs'
                         else dict(state=artifact) for _ in items], 'ok')
            for path in ('/api/cards?project=alpha', '/api/card?project=alpha&card=question.md'):
                connection = Connection(('GET ' + path + ' HTTP/1.0\r\nHost: localhost:8766\r\n\r\n').encode())
                with mock.patch.object(inspection, '_channel', side_effect=channel):
                    captured[0](connection, ('127.0.0.1', 1), server)
                headers, raw = bytes(connection.output).split(b'\r\n\r\n', 1)
                self.assertTrue(headers.startswith(b'HTTP/1.0 200'), raw)
                value = json.loads(raw)
                card = value[0] if isinstance(value, list) else value
                self.assertEqual([j['id'] for j in card['jobs']], [123])
                self.assertEqual(card['results'][0]['reason'], 'invalid_json')
                self.assertEqual(card['verdict'], 'met')
                self.assertTrue(card['acceptance']['items'][0]['checked'])
                self.assertEqual(self.card.read_bytes(), original)
                self.assertFalse(marker.exists())
