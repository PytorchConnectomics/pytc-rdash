"""rdash_sync.sh against real git repositories: a bare origin, the board checkout, a peer."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]


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
        self.assertIn("rdash: board edits and run receipts (g02 sync)", log)
        self.assertIn("peer card", log)
        self.assertEqual(git(self.origin, "show", "main:projects/alpha/cards/q.md"), "card v2 (board edit)")

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
        self.assertEqual(git(self.board, "log", "--format=%s", "-1"), "rdash: board edits and run receipts (g02 sync)")
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
