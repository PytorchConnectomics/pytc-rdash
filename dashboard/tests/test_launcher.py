import ast
import concurrent.futures
import os
from pathlib import Path
from unittest import mock
import json
import socket
import subprocess
import sys
import unittest

from fixtures import RepoTest, SOURCE


SCRIPT = SOURCE / "dashboard/app/research_dash.sh"


class ImportHygieneTests(unittest.TestCase):
    """Startup imports must work even on hosts that prohibit socket binds."""

    def test_app_directory_imports_stdlib_inspect(self):
        code = '''import sys
sys.path.insert(0, sys.argv[1])
import inspect
import sysconfig
from pathlib import Path
assert Path(inspect.__file__).resolve() == (Path(sysconfig.get_path('stdlib')) / 'inspect.py').resolve(), inspect.__file__
assert str(inspect.signature(lambda value: None)) == '(value)'
'''
        done = subprocess.run([sys.executable, '-B', '-c', code, str(SCRIPT.parent)],
                              capture_output=True, text=True, timeout=10)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_server_script_help_without_binding(self):
        done = subprocess.run([sys.executable, '-B', str(SCRIPT.parent / 'server.py'), '--help'],
                              cwd=str(SOURCE.parent), capture_output=True, text=True, timeout=10)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('--repo-root', done.stdout)
        self.assertIn('--cache-dir', done.stdout)


class LauncherTests(RepoTest):
    def setUp(self):
        super().setUp()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            self.port = sock.getsockname()[1]
        self.addCleanup(self.run_launcher, "stop")

    def run_launcher(self, action):
        return subprocess.run([str(SCRIPT), action], env=self.env(self.port), capture_output=True, text=True, timeout=25)

    def test_start_status_curl_stop_roundtrip(self):
        started = self.run_launcher("start")
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertIn("http://127.0.0.1:", started.stdout)
        self.assertIn("running", self.run_launcher("status").stdout)
        response = subprocess.run(["curl", "--noproxy", "*", "-fsS", "http://127.0.0.1:" + str(self.port) + "/api/health"], capture_output=True, text=True, timeout=5)
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertTrue(json.loads(response.stdout)["ok"])
        self.assertEqual(self.run_launcher("stop").returncode, 0)
        self.assertFalse((self.cache / "rdash.pid").exists())
        self.assertIn("stopped", self.run_launcher("status").stdout)

    def test_cache_with_symlinked_ancestor(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.cache = alias / "cache"
        self.test_start_status_curl_stop_roundtrip()
        from dashboard.app import cards, safety
        from dashboard.app.config import Settings
        settings = Settings.from_env(self.env(self.port))
        revision = cards.read_card(settings, "alpha", "question.md")["revision"]
        cards.edit_card(settings, "alpha", "question.md", revision, stage="parked")
        self.assertEqual(len(list(self.cache.rglob("*.md"))), 1)
        (self.cache / "escape").symlink_to(self.root, target_is_directory=True)
        self.error(400, "unsafe_path", safety.cache_path, settings, "escape", "file")
        (self.cache / "rdash.log").unlink()
        (self.cache / "rdash.log").symlink_to(self.card)
        self.assertNotEqual(self.run_launcher("start").returncode, 0)

    def test_concurrent_start_and_restart(self):
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(self.run_launcher, ["start", "start"]))
        self.assertEqual([r.returncode for r in results], [0, 0], [r.stderr for r in results])
        first = json.loads((self.cache / "rdash.pid").read_text())
        self.assertEqual(results[0].stdout, results[1].stdout)
        self.assertEqual(self.run_launcher("start").returncode, 0)
        self.assertEqual(json.loads((self.cache / "rdash.pid").read_text())["pid"], first["pid"])
        self.assertEqual(self.run_launcher("restart").returncode, 0)
        self.assertNotEqual(json.loads((self.cache / "rdash.pid").read_text())["pid"], first["pid"])

    def test_occupied_port_and_zero_fail_cleanly(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", self.port))
            sock.listen()
            result = self.run_launcher("start")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("startup failed", result.stderr)
        self.assertIn("Address already in use", result.stderr)
        self.assertFalse((self.cache / "rdash.pid").exists())
        self.port = 0
        self.assertNotEqual(self.run_launcher("start").returncode, 0)

    def test_live_unrelated_process_and_foreign_repository(self):
        sleeper = subprocess.Popen(["sleep", "60"])
        def cleanup():
            sleeper.terminate()
            sleeper.wait(timeout=5)
        self.addCleanup(cleanup)
        self.cache.mkdir()
        data = dict(pid=sleeper.pid, port=self.port, repo_root=str(self.repo), cache_dir=str(self.cache), started=0, cmd=[])
        (self.cache / "rdash.pid").write_text(json.dumps(data))
        self.assertIn("stale", self.run_launcher("stop").stdout)
        self.assertIsNone(sleeper.poll())
        self.assertEqual(self.run_launcher("start").returncode, 0)
        pidfile = self.cache / "rdash.pid"
        real = pidfile.read_text()
        data = json.loads(real)
        data["repo_root"] = str(self.root / "foreign")
        pidfile.write_text(json.dumps(data))
        try:
            self.assertIn("stale", self.run_launcher("stop").stdout)
            response = subprocess.run(["curl", "--noproxy", "*", "-fsS", "http://127.0.0.1:" + str(self.port) + "/api/health"], capture_output=True, timeout=5)
            self.assertEqual(response.returncode, 0)
        finally:
            pidfile.write_text(real)


class ProcessStateTests(RepoTest):
    def test_zombie_detection_without_proc(self):
        # Load only the embedded helper; do not execute launcher lifecycle code.
        source = SCRIPT.read_text().split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        function = next(node for node in ast.parse(source).body
                        if isinstance(node, ast.FunctionDef) and node.name == "alive")
        namespace = dict(os=os, Path=Path, subprocess=subprocess)
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(SCRIPT), "exec"), namespace)
        with mock.patch.object(Path, "exists", return_value=False), \
                mock.patch.object(subprocess, "check_output") as ps:
            for state, expected in (("S", True), ("Z", False), ("Z+", False), ("", False)):
                ps.return_value = state
                self.assertEqual(namespace["alive"](os.getpid()), expected)
            ps.assert_called_with(["ps", "-p", str(os.getpid()), "-o", "stat="], text=True)
            ps.side_effect = subprocess.CalledProcessError(1, "ps")
            self.assertFalse(namespace["alive"](os.getpid()))
