"""rdash_sync.sh against real git repositories: a bare origin, the board checkout, a peer."""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
HOST = socket.gethostname().split(".")[0]  # what `hostname -s` prints


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


class SyncTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="rdash-sync-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.origin, self.board, self.peer = root / "origin.git", root / "board", root / "peer"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        git(root, "clone", "-q", str(self.origin), str(self.board))
        git(self.board, "checkout", "-q", "-B", "main")
        shutil.copytree(SOURCE / "dashboard/app", self.board / "dashboard/app",
                        ignore=shutil.ignore_patterns("__pycache__"))
        (self.board / "dashboard/__init__.py").write_text("")
        cards = self.board / "projects/alpha/cards"
        cards.mkdir(parents=True)
        (cards / "q.md").write_text("card v1\n")
        (self.board / "README.md").write_text("readme\n")
        (self.board / ".gitignore").write_text(".rdash.lock\n")
        git(self.board, "add", "-A")
        git(self.board, "commit", "-qm", "init")
        git(self.board, "push", "-q", "origin", "main")
        git(root, "clone", "-q", str(self.origin), str(self.peer))
        self.cache = root / "cache"
        self.env = dict(os.environ, HOME=str(root), RDASH_ENV_FILE=str(root / "no-env"), RDASH_SSH_HOSTS="",
                        RDASH_HOST_ALIAS="hub", RESEARCH_DASH_CACHE=str(self.cache), XDG_CACHE_HOME=str(root),
                        GIT_AUTHOR_NAME="hub", GIT_AUTHOR_EMAIL="hub@x", GIT_COMMITTER_NAME="hub",
                        GIT_COMMITTER_EMAIL="hub@x")

    def sync(self):
        result = subprocess.run([str(self.board / "dashboard/app/rdash_sync.sh")], env=self.env,
                                capture_output=True, text=True, timeout=120)
        return result, json.loads((self.cache / "sync.json").read_text())

    def test_board_writes_are_committed_and_pushed_and_peers_flow_in(self):
        (self.board / "projects/alpha/cards/q.md").write_text("card v2 (board edit)\n")
        runs = self.board / "projects/alpha/runs"
        runs.mkdir()
        (runs / "gpu1-7.json").write_text("{}\n")
        (self.peer / "projects/alpha/cards/new.md").write_text("written on cajal\n")
        git(self.peer, "add", "-A")
        git(self.peer, "commit", "-qm", "peer card")
        git(self.peer, "push", "-q", "origin", "main")
        result, state = self.sync()
        self.assertEqual(state["state"], "ok", result.stdout + result.stderr)
        self.assertEqual(git(self.board, "status", "--porcelain"), "")
        self.assertTrue((self.board / "projects/alpha/cards/new.md").is_file())
        log = git(self.origin, "log", "--format=%s", "main")
        self.assertIn("rdash: board edits, plan ticks and run receipts (%s sync)" % HOST, log)
        self.assertIn("peer card", log)
        self.assertEqual(git(self.origin, "show", "main:projects/alpha/cards/q.md"), "card v2 (board edit)")

    def test_plan_edits_made_on_the_board_are_committed_like_cards(self):
        (self.board / "plan").mkdir()
        (self.board / "plan/LADDER.md").write_text("# L\n\n## Deliverables\n\n### 2026-08 — x\n\n- [x] a\n")
        git(self.board, "add", "plan")
        git(self.board, "commit", "-qm", "ladder")
        git(self.board, "push", "-q", "origin", "main")
        (self.board / "plan/LADDER.md").write_text("# L\n\n## Deliverables\n\n### 2026-08 — x\n\n- [x] a\n- [ ] b\n")
        (self.board / "plan/days").mkdir()
        (self.board / "plan/days/2026-11-09.md").write_text("# Mon\n\n## p\n\n- [ ] c\n")
        result, state = self.sync()
        self.assertEqual(state["state"], "ok", result.stdout + result.stderr)
        self.assertEqual(git(self.board, "status", "--porcelain"), "")
        self.assertIn("- [ ] b", git(self.origin, "show", "main:plan/LADDER.md"))
        self.assertIn("- [ ] c", git(self.origin, "show", "main:plan/days/2026-11-09.md"))

    def test_other_tracked_changes_block_and_are_never_committed(self):
        (self.board / "README.md").write_text("someone's work\n")
        (self.board / "projects/alpha/cards/q.md").write_text("card v2\n")
        result, state = self.sync()
        self.assertEqual(state["state"], "blocked", result.stdout)
        self.assertIn("README.md", state["message"])
        # Nothing is committed while blocked -- not even the card -- and nothing is pushed.
        self.assertEqual(git(self.board, "log", "--format=%s", "-1"), "init")
        self.assertIn("README.md", git(self.board, "status", "--porcelain"))
        self.assertEqual(git(self.origin, "log", "--format=%s", "-1", "main"), "init")

    def test_a_board_checkout_off_main_is_left_alone(self):
        git(self.board, "checkout", "-q", "-b", "feature")
        (self.board / "projects/alpha/cards/q.md").write_text("card v2\n")
        result, state = self.sync()
        self.assertEqual(state["state"], "blocked")
        self.assertIn("feature", state["message"])
        self.assertIn("card v2", (self.board / "projects/alpha/cards/q.md").read_text())
        self.assertEqual(git(self.board, "log", "--format=%s", "-1"), "init")

    def test_conflicting_edit_is_kept_locally_and_reported(self):
        (self.peer / "projects/alpha/cards/q.md").write_text("peer edit\n")
        git(self.peer, "commit", "-qam", "peer edit")
        git(self.peer, "push", "-q", "origin", "main")
        (self.board / "projects/alpha/cards/q.md").write_text("board edit\n")
        result, state = self.sync()
        self.assertEqual(state["state"], "conflict")
        self.assertEqual(git(self.board, "log", "--format=%s", "-1"), "rdash: board edits, plan ticks and run receipts (%s sync)" % HOST)
        self.assertEqual(git(self.origin, "log", "--format=%s", "-1", "main"), "peer edit")

    def test_a_host_that_drops_out_warns_until_it_is_back_or_removed(self):
        # No launch roots configured, so gpu1 never answers: the silent drop bc made on 2026-10-23.
        self.env.update(RDASH_SSH_HOSTS="gpu1", RDASH_SLOW_HOSTS="gpu1:900")
        result, state = self.sync()
        self.assertEqual(state["state"], "warn", result.stdout + result.stderr)
        self.assertIn("gpu1 unreachable since", state["message"])
        polled = (self.cache / "polled-gpu1").read_text()
        # Within its interval the slow host is not polled again, and the warning stays.
        result, state = self.sync()
        self.assertEqual(state["state"], "warn")
        self.assertEqual((self.cache / "polled-gpu1").read_text(), polled)
        # Taking the host out of RDASH_SSH_HOSTS clears it.
        self.env.update(RDASH_SSH_HOSTS="")
        result, state = self.sync()
        self.assertEqual(state["state"], "ok", result.stdout)

    def test_a_slow_host_is_polled_again_after_its_interval(self):
        self.env.update(RDASH_SSH_HOSTS="gpu1", RDASH_SLOW_HOSTS="gpu1:900")
        self.sync()
        (self.cache / "polled-gpu1").write_text("0\n")
        self.sync()
        self.assertNotEqual((self.cache / "polled-gpu1").read_text(), "0\n")


if __name__ == "__main__":
    unittest.main()


class SubmoduleSyncTests(unittest.TestCase):
    """The deployed layout: a team repository with rdash/ as its submodule (pytc-jam-msi)."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="rdash-sync-sub-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.env = dict(os.environ, HOME=str(root), RDASH_ENV_FILE=str(root / "no-env"), RDASH_SSH_HOSTS="",
                        RDASH_HOST_ALIAS="hub", RESEARCH_DASH_CACHE=str(root / "cache"), XDG_CACHE_HOME=str(root),
                        GIT_AUTHOR_NAME="hub", GIT_AUTHOR_EMAIL="hub@x", GIT_COMMITTER_NAME="hub",
                        GIT_COMMITTER_EMAIL="hub@x", GIT_CONFIG_COUNT="1",
                        GIT_CONFIG_KEY_0="protocol.file.allow", GIT_CONFIG_VALUE_0="always")
        self.cache = root / "cache"
        self.tool_origin, self.origin = root / "rdash.git", root / "team.git"
        tool_src = root / "rdash-src"
        for bare in (self.tool_origin, self.origin):
            subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
        self.run_git(root, "clone", "-q", str(self.tool_origin), str(tool_src))
        self.run_git(tool_src, "checkout", "-q", "-B", "main")
        for package in ("app", "supervisor"):   # the server imports both, so a board can start from the fixture
            shutil.copytree(SOURCE / "dashboard" / package, tool_src / "dashboard" / package,
                            ignore=shutil.ignore_patterns("__pycache__"))
        (tool_src / "dashboard/__init__.py").write_text("")
        self.run_git(tool_src, "add", "-A")
        self.run_git(tool_src, "commit", "-qm", "tool v1")
        self.run_git(tool_src, "push", "-q", "origin", "main")
        self.tool_src = tool_src
        seed = root / "seed"
        self.run_git(root, "clone", "-q", str(self.origin), str(seed))
        self.run_git(seed, "checkout", "-q", "-B", "main")
        self.run_git(seed, "submodule", "add", "-q", str(self.tool_origin), "rdash")
        (seed / "projects/alpha/cards").mkdir(parents=True)
        (seed / "projects/alpha/cards/q.md").write_text("card v1\n")
        (seed / ".gitignore").write_text(".rdash.lock\n")
        self.run_git(seed, "add", "-A")
        self.run_git(seed, "commit", "-qm", "init")
        self.run_git(seed, "push", "-q", "origin", "main")
        self.board, self.peer = root / "board", root / "peer"
        for clone in (self.board, self.peer):
            self.run_git(root, "clone", "-q", "--recurse-submodules", str(self.origin), str(clone))

    def run_git(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                              env=self.env).stdout.strip()

    def bump_tool_pin_from_peer(self):
        (self.tool_src / "NOTE").write_text("v2\n")
        self.run_git(self.tool_src, "add", "-A")
        self.run_git(self.tool_src, "commit", "-qm", "tool v2")
        self.run_git(self.tool_src, "push", "-q", "origin", "main")
        self.run_git(self.peer / "rdash", "pull", "-q", "origin", "main")
        self.run_git(self.peer, "commit", "-qam", "rdash: bump")
        self.run_git(self.peer, "push", "-q", "origin", "main")
        return self.run_git(self.tool_src, "rev-parse", "HEAD")

    def sync(self):
        result = subprocess.run([str(self.board / "rdash/dashboard/app/rdash_sync.sh")], env=self.env,
                                capture_output=True, text=True, timeout=120)
        return result, json.loads((self.cache / "sync.json").read_text())

    def test_a_pin_bump_pulled_by_the_sync_moves_the_submodule(self):
        pinned = self.bump_tool_pin_from_peer()
        result, state = self.sync()
        self.assertEqual(state["state"], "ok", result.stdout + result.stderr)
        self.assertEqual(self.run_git(self.board / "rdash", "rev-parse", "HEAD"), pinned)
        self.assertEqual(self.run_git(self.board, "status", "--porcelain"), "")
        result, state = self.sync()     # and the next run is not blocked
        self.assertEqual(state["state"], "ok", result.stdout + result.stderr)

    def test_a_pin_bump_stops_the_running_board_so_its_service_restarts(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        env = dict(self.env, RDASH_REPO_ROOT=str(self.board), RESEARCH_DASH_PORT=str(port))
        launcher = str(self.board / "rdash/dashboard/app/research_dash.sh")
        self.addCleanup(subprocess.run, [launcher, "stop"], env=env, capture_output=True, timeout=60)
        started = subprocess.run([launcher, "start"], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
        self.assertTrue((self.cache / "rdash.pid").is_file())
        self.bump_tool_pin_from_peer()
        result, state = self.sync()
        self.assertEqual(state["state"], "ok", result.stdout + result.stderr)
        self.assertIn("board stopped so its service restarts", result.stdout)
        self.assertFalse((self.cache / "rdash.pid").exists())
        self.assertIn("stopped", subprocess.run([launcher, "status"], env=env, capture_output=True, text=True, timeout=60).stdout)
        result, state = self.sync()     # with no board running there is nothing to stop
        self.assertEqual(state["state"], "ok", result.stdout + result.stderr)
        self.assertNotIn("board stopped", result.stdout)

    def test_a_board_already_behind_its_pin_heals(self):
        old = self.run_git(self.board / "rdash", "rev-parse", "HEAD")
        pinned = self.bump_tool_pin_from_peer()
        self.run_git(self.board, "pull", "-q", "origin", "main")    # gitlink moves, files stay at `old`
        self.assertEqual(self.run_git(self.board / "rdash", "rev-parse", "HEAD"), old)
        result, state = self.sync()
        self.assertEqual(state["state"], "ok", result.stdout + result.stderr)
        self.assertEqual(self.run_git(self.board / "rdash", "rev-parse", "HEAD"), pinned)

    def test_local_work_in_the_submodule_is_never_overwritten(self):
        self.bump_tool_pin_from_peer()
        self.run_git(self.board, "pull", "-q", "origin", "main")
        (self.board / "rdash/NOTE2").write_text("someone's edit\n")
        self.run_git(self.board / "rdash", "add", "NOTE2")
        result, state = self.sync()
        self.assertEqual(state["state"], "blocked", result.stdout + result.stderr)
        self.assertIn("rdash", state["message"])
        self.assertTrue((self.board / "rdash/NOTE2").is_file())
