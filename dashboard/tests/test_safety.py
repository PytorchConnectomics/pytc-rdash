import errno
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from fixtures import RepoTest, SAMPLE, SOURCE
from dashboard.app import cards, safety
from dashboard.app.config import Settings


class SafetyTests(RepoTest):
    def test_config_injection(self):
        settings = Settings.from_env(self.env(12345))
        self.assertEqual(settings.repo_root, self.repo.resolve())
        self.assertEqual(settings.bind_host, "127.0.0.1")
        self.assertEqual(Settings.from_env(self.env(12345), port=0).port, 0)
        with self.assertRaises(ValueError):
            Settings.from_env(dict(RDASH_REPO_ROOT=str(self.root)))

    def test_cache_with_symlinked_ancestor_and_confined_children(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        settings = Settings(self.repo, alias / "cache", 0)
        self.assertEqual(safety.cache_path(settings), self.cache.resolve())
        revision = cards.read_card(settings, "alpha", "question.md")["revision"]
        cards.edit_card(settings, "alpha", "question.md", revision, stage="parked")
        self.assertEqual([p.read_bytes() for p in self.cache.rglob("*.md")], [SAMPLE])
        (self.cache / "escape").symlink_to(self.root, target_is_directory=True)
        self.error(400, "unsafe_path", safety.cache_path, settings, "escape", "file")

    def test_agent_locks_fail_closed_and_stale_unchanged(self):
        lock = self.card.parents[1] / ".agent-lock"
        now = datetime.now(timezone.utc)
        values = [("broken", "project_locked_unreadable"), ("{}", "project_locked_unreadable"),
                  (json.dumps({"started": (now + timedelta(hours=1)).isoformat()}), "project_locked_unreadable"),
                  (json.dumps({"started": now.isoformat()}), "project_locked"),
                  (json.dumps({"started": "2020-01-01"}), "project_locked_unreadable")]
        revision = cards.read_card(self.settings, "alpha", "question.md")["revision"]
        for value, code in values:
            lock.write_text(value)
            self.error(423, code, cards.edit_card, self.settings, "alpha", "question.md", revision, stage="parked")
            self.error(423, code, cards.create_idea, self.settings, "alpha", "Blocked")
            self.assertEqual(lock.read_text(), value)
            self.assertEqual(self.card.read_bytes(), SAMPLE)
        value = json.dumps({"started": (now - timedelta(hours=7)).isoformat()})
        lock.write_text(value)
        cards.edit_card(self.settings, "alpha", "question.md", revision, stage="parked")
        self.assertEqual(lock.read_text(), value)
        lock.unlink()
        cards.create_idea(self.settings, "alpha", "Allowed")
        self.assertFalse(lock.exists())

    def test_agent_lock_own_session_passes(self):
        lock = self.card.parents[1] / ".agent-lock"
        now = datetime.now(timezone.utc).isoformat()
        lock.write_text(json.dumps({"session_id": "s1", "started": now, "task": "t"}))
        safety.agent_lock_state(lock.parent, session_id="s1")
        for other in ("s2", ""):
            self.error(423, "project_locked", safety.agent_lock_state, lock.parent, other)
        lock.write_text(json.dumps({"started": now}))
        self.error(423, "project_locked", safety.agent_lock_state, lock.parent, "s1")
        lock.write_text("session=s1 " + now)
        self.error(423, "project_locked_unreadable", safety.agent_lock_state, lock.parent, "s1")
        lock.unlink()

    def test_card_locks_let_sessions_share_a_project(self):
        project = self.card.parents[1]
        card = self.card.name
        lock = safety.take_lock(project, "s1", "card work", card=card)
        self.assertEqual(lock, project / ".locks" / "cards" / (card + ".lock"))
        safety.agent_lock_state(project, "s1", card=card)
        self.error(423, "card_locked", safety.agent_lock_state, project, "s2", card)
        safety.agent_lock_state(project, "s2", card="other.md")      # another card: free
        safety.agent_lock_state(project, "s2")                       # project-wide write: free
        safety.take_lock(project, "s2", "other card", card="other.md")
        self.error(423, "card_locked", safety.take_lock, project, "s2", "t", card)
        self.error(423, "cards_locked", safety.take_lock, project, "s3", "whole project")
        revision = cards.read_card(self.settings, "alpha", "question.md")["revision"]
        with mock.patch.dict(os.environ, RDASH_SESSION_ID="s2"):
            self.error(423, "card_locked", cards.edit_card, self.settings, "alpha", card, revision, stage="parked")
        with mock.patch.dict(os.environ, RDASH_SESSION_ID="s1"):
            cards.edit_card(self.settings, "alpha", card, revision, stage="parked")
        before = lock.read_text()
        safety.take_lock(project, "s1", "refreshed", card=card)       # own lock: refreshed in place
        self.assertIn("refreshed", lock.read_text())
        self.error(423, "not_your_lock", safety.release_lock, project, "s2", card)
        self.error(423, "not_your_lock", safety.release_lock, project, "s2", card, True)  # fresh: --stale refuses
        self.assertEqual(safety.release_lock(project, "s1", card), lock)
        self.assertFalse(lock.exists())
        old = project / ".locks" / "cards" / "other.md.lock"
        old.write_text(json.dumps(dict(session_id="s2", started="2020-01-01T00:00:00+00:00", task="t")))
        self.error(423, "lock_stale_foreign", safety.take_lock, project, "s3", "t", "other.md")
        safety.take_lock(project, "s3", "whole project")              # stale card locks do not block
        self.error(423, "project_locked", safety.take_lock, project, "s1", "t", card)
        self.assertEqual(safety.release_lock(project, "s1", "other.md", stale=True), old)
        safety.release_lock(project, "s3")
        self.assertFalse((project / ".agent-lock").exists())
        self.error(400, "session_required", safety.take_lock, project, "", "t", card)
        self.error(400, "invalid_card", safety.take_lock, project, "s1", "t", "../x.md")

    def test_atomic_link_readers_and_predictable_temp_symlink(self):
        target = self.card.parent / "new.md"
        outside = self.root / "untouched"
        outside.write_bytes(b"untouched")
        (self.card.parent / "question.md.tmp").symlink_to(outside)
        safety.publish_replace(self.card, SAMPLE + b"new")
        self.assertEqual(outside.read_bytes(), b"untouched")
        link = os.link
        def inspect(source, destination):
            self.assertFalse(target.exists())
            self.assertEqual(Path(source).read_bytes(), SAMPLE)
            link(source, destination)
            self.assertEqual(target.read_bytes(), SAMPLE)
        with mock.patch.object(safety.os, "link", side_effect=inspect):
            safety.publish_link(target, SAMPLE)
        with self.assertRaises(FileExistsError):
            safety.publish_link(target, b"overwrite")
        self.assertEqual(target.read_bytes(), SAMPLE)
        self.assertEqual(list(self.card.parent.glob(".rdash-*.tmp")), [])

    def test_cache_and_repository_lock_symlinks(self):
        self.cache.symlink_to(self.root, target_is_directory=True)
        self.error(400, "unsafe_path", safety.cache_path, self.settings)
        outside = self.root / "outside"
        outside.write_text("untouched")
        (self.repo / ".rdash.lock").symlink_to(outside)
        self.error(503, "lock_unavailable", cards.create_idea, self.settings, "alpha", "No")
        self.assertEqual(outside.read_text(), "untouched")

    def test_lock_initialization_failure_refuses_write(self):
        real_open = os.open
        def readonly(path, *args, **kwargs):
            if str(path).endswith(".rdash.lock"):
                raise OSError(errno.EROFS, "Read-only file system")
            return real_open(path, *args, **kwargs)
        with mock.patch.object(safety.os, "open", side_effect=readonly):
            self.error(503, "lock_unavailable", cards.create_idea, self.settings, "alpha", "No")
        self.assertEqual(self.card.read_bytes(), SAMPLE)
        self.assertFalse((self.card.parent / "inbox").exists())

    def test_actual_unwritable_repository(self):
        self.repo.chmod(0o555)
        try:
            self.error(503, "lock_unavailable", cards.create_idea, self.settings, "alpha", "No")
            self.assertFalse((self.repo / ".rdash.lock").exists())
            self.assertFalse((self.card.parent / "inbox").exists())
        finally:
            self.repo.chmod(0o755)

    def test_backup_directory_symlink_refuses_edit(self):
        self.cache.mkdir()
        (self.cache / "backups").symlink_to(self.root, target_is_directory=True)
        revision = cards.read_card(self.settings, "alpha", "question.md")["revision"]
        self.error(400, "unsafe_path", cards.edit_card, self.settings, "alpha", "question.md", revision, stage="parked")
        self.assertEqual(self.card.read_bytes(), SAMPLE)

    def test_process_lock_contention_and_holder_death(self):
        holder_code = """
import sys, time
from dashboard.app.config import Settings
from dashboard.app.safety import writer_lock
with writer_lock(Settings.from_env()):
    print('locked', flush=True)
    time.sleep(60)
"""
        holder = subprocess.Popen([sys.executable, "-B", "-c", holder_code], cwd=SOURCE,
                                  env=self.env(0), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            if holder.poll() is None:
                holder.kill()
            holder.communicate(timeout=5)
        self.addCleanup(cleanup)
        self.assertEqual(holder.stdout.readline().strip(), "locked")
        contender_code = """
from dashboard.app.config import Settings
from dashboard.app.cards import create_idea
from dashboard.app.safety import Error
try:
    create_idea(Settings.from_env(), 'alpha', 'Blocked')
except Error as exc:
    print(exc.status, exc.payload['error'])
"""
        env = self.env(0)
        env["RESEARCH_DASH_CACHE"] = str(self.root / "different-cache")
        result = subprocess.run([sys.executable, "-B", "-c", contender_code], env=env, cwd=SOURCE, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "503 busy")
        self.assertFalse((self.card.parent / "inbox").exists())
        holder.kill()
        holder.communicate(timeout=5)
        (self.repo / ".rdash.lock").write_text("malformed diagnostic body")
        cards.create_idea(self.settings, "alpha", "After death")
        self.assertTrue((self.card.parent / "inbox/after-death.md").exists())
