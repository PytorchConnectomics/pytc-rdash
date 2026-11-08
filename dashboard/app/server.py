"""Loopback-only HTTP API. Run directly or import make_server in tests."""
import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.app import attention, cards, inspection, contract, jobs, receipts, results
from dashboard.app import evidence, goals, questions, tracks, ladder, focus
from dashboard.app.config import Settings
from dashboard.app.projects import list_projects
from dashboard.app.safety import Error, cache_path


def enrich(settings, project, records):
    receipts.annotate(records, settings, project)
    inspection.annotate_status(records, settings, project)
    results.annotate(records, settings, project)
    goal_index = goals.card_index(settings, project)
    for record in records:
        record["contract"] = contract.report(settings, project, record)
        record["sessions"] = jobs.declared_sessions(record["body"])
        goal = goals.for_card(settings, project, record["card"], goal_index)
        if goal is not None:
            record["goal"] = goal
            record["sessions"] = goals.augment_sessions(record["sessions"], goal)
        record["attention"] = attention.owner_and_next(record)
    return records


def make_server(settings):
    cache_path(settings).mkdir(parents=True, exist_ok=True)
    static = Path(__file__).parent / "static"
    assets = {name: (static / name).read_bytes() for name in ("index.html", "app.js", "styles.css")}

    class Handler(BaseHTTPRequestHandler):
        def __getattr__(self, name):
            if name.startswith("do_"):
                return self.handle_request
            raise AttributeError(name)

        def log_message(self, format, *args):
            # Avoid recording attacker-controlled request paths or bodies.
            pass

        def send_data(self, status, data, content_type="application/json"):
            if content_type == "application/json":
                data = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type + ("; charset=utf-8" if not content_type.startswith("image/") else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def guard(self):
            port = self.server.server_address[1]
            hosts = ("127.0.0.1:" + str(port), "localhost:" + str(port))
            if len(self.headers.get_all("Host", [])) != 1 or self.headers.get("Host") not in hosts:
                raise Error(403, "forbidden_host", "Host is not this loopback server")
            origins = self.headers.get_all("Origin", [])
            if origins and (len(origins) != 1 or origins[0] not in tuple("http://" + host for host in hosts)):
                raise Error(403, "forbidden_origin", "Origin is not this loopback server")

        def handle_request(self):
            try:
                self.guard()
                if self.command not in ("GET", "POST"):
                    raise Error(403, "forbidden_method", "Method is not allowed")
                url = urlsplit(self.path)
                if url.scheme or url.netloc:
                    raise Error(400, "invalid_request", "Expected a relative request target")
                path = url.path
                query = parse_qs(url.query, keep_blank_values=True)

                def arg(name):
                    values = query.get(name, [])
                    if len(values) != 1:
                        raise Error(400, "invalid_query", "Expected one " + name)
                    return values[0]

                if self.command == "GET":
                    name = "index.html" if path == "/" else path[len("/static/"):] if path.startswith("/static/") else None
                    if name in assets:
                        kind = {"index.html": "text/html", "app.js": "text/javascript", "styles.css": "text/css"}[name]
                        return self.send_data(200, assets[name], kind)
                    if path == "/api/health":
                        result = dict(ok=True, port=self.server.server_address[1], repo_root_name=settings.repo_root.name, pid=os.getpid(), owner=settings.owner, require_owner=settings.require_owner)
                    elif path == "/api/ladder":
                        result = ladder.read(settings)
                    elif path == "/api/focus":
                        result = focus.read(settings, arg("project"))
                    elif path == "/api/stages":
                        # The board reads its columns from here, so adding a stage
                        # in cards.STAGES is enough -- no HTML edit required.
                        result = list(cards.STAGES)
                    elif path == "/api/projects":
                        result = list_projects(settings)
                    elif path == "/api/cards":
                        result = enrich(settings, arg("project"), cards.list_cards(settings, arg("project")))
                    elif path == "/api/card":
                        result = enrich(settings, arg("project"), [cards.read_card(settings, arg("project"), arg("card"))])[0]
                    elif path == "/api/tracks":
                        result = tracks.read(settings, arg("project"))
                    elif path == "/api/runs":
                        refresh = query.get("refresh", ["0"]) == ["1"]
                        result = receipts.runs_view(settings, arg("project"), refresh=refresh)
                    elif path == "/api/questions":
                        result = questions.read(settings, arg("project"))
                    elif path == "/api/goal":
                        result = goals.read(settings, arg("project"), arg("goal"))
                    elif path == "/api/evidence":
                        result = evidence.preview(settings, arg("project"), arg("card"), arg("revision"), arg("label"))
                    elif path == "/api/evidence/content":
                        body, kind = evidence.content(settings, arg("project"), arg("card"), arg("revision"), arg("label"), arg("artifact_revision"))
                        return self.send_data(200, body, kind)
                    else:
                        raise Error(404, "not_found", "Unknown endpoint")
                    return self.send_data(200, result)
                if self.headers.get("X-Rdash") != "1":
                    raise Error(403, "missing_header", "X-Rdash: 1 is required")
                if self.headers.get("Content-Type") != "application/json":
                    raise Error(400, "invalid_content_type", "Content-Type must be application/json")
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or not lengths[0].isdigit() or self.headers.get("Transfer-Encoding"):
                    raise Error(400, "invalid_length", "One Content-Length is required")
                length = int(lengths[0])
                if length >= 65536:
                    raise Error(400, "body_too_large", "Body must be smaller than 64 KiB")
                try:
                    self.connection.settimeout(5)
                    data = json.loads(self.rfile.read(length))
                except (ValueError, UnicodeDecodeError, RecursionError):
                    raise Error(400, "invalid_json", "Invalid JSON body")
                if not isinstance(data, dict):
                    raise Error(400, "invalid_json", "Body must be an object")
                if path == "/api/goal/command":
                    return self.send_data(200, goals.command(settings, data))
                if path == "/api/evidence/feedback":
                    result = evidence.feedback(settings, data)
                elif path == "/api/idea":
                    result = cards.create_idea(settings, data.get("project"), data.get("title"),
                                              data.get("track", "model"), idea=data.get("idea"))
                elif path in ("/api/stage", "/api/discussion"):
                    field = "stage" if path == "/api/stage" else "text"
                    if data.get(field) is None:
                        raise Error(400, "missing_field", field + " is required")
                    result = cards.edit_card(settings, data.get("project"), data.get("card"), data.get("revision"), **{field: data[field]})
                else:
                    raise Error(404, "not_found", "Unknown endpoint")
                # Mutations return a card record too; keep one shape everywhere.
                result = enrich(settings, data.get("project"), [result])[0]
                self.send_data(200, result)
            except Error as exc:
                self.send_data(exc.status, exc.payload)
            except (OSError, ValueError):
                self.send_data(503, {"error": "storage_unavailable", "message": "Record storage or request I/O is unavailable"})

        do_GET = handle_request
        do_POST = handle_request
        do_OPTIONS = handle_request
        do_HEAD = handle_request
        do_PUT = handle_request
        do_DELETE = handle_request
        do_PATCH = handle_request

    return ThreadingHTTPServer((settings.bind_host, settings.port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int)
    parser.add_argument("--repo-root")
    parser.add_argument("--cache-dir")
    args = parser.parse_args()
    env = dict(os.environ)
    if args.repo_root:
        env["RDASH_REPO_ROOT"] = args.repo_root
    if args.cache_dir:
        env["RESEARCH_DASH_CACHE"] = args.cache_dir
    try:
        settings = Settings.from_env(env, args.port)
        with make_server(settings) as server:
            print("http://127.0.0.1:" + str(server.server_address[1]), flush=True)
            server.serve_forever()
    except (ValueError, OSError, Error) as exc:
        print("rdash: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
