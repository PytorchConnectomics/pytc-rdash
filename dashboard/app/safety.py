"""Confinement, advisory coordination, and atomic publication."""
import fcntl
import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class Error(Exception):
    def __init__(self, status, code, message, **details):
        super().__init__(message)
        self.status = status
        self.payload = dict(error=code, message=message, **details)


def project_id(value):
    if not isinstance(value, str) or len(value) > 64 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
        raise Error(400, "invalid_project", "Invalid project identifier")
    return value


def card_ref(value):
    if not isinstance(value, str) or len(value) > 96:
        raise Error(400, "invalid_card", "Invalid card reference")
    name = value[6:] if value.startswith("inbox/") else value
    if not name.endswith(".md") or len(name[:-3]) > 80 or ".." in name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.md", name):
        raise Error(400, "invalid_card", "Invalid card reference")
    return value


def resolve_within(base, *parts):
    base = Path(base).absolute()
    target = base.joinpath(*parts)
    try:
        if os.path.commonpath([str(base.resolve()), str(target.resolve())]) != str(base.resolve()):
            raise ValueError()
        relative = target.relative_to(base)
        current = base
        for part in relative.parts:
            if part == "..":
                raise ValueError()
            current = current / part
            if current.is_symlink():
                raise ValueError()
    except (ValueError, RuntimeError):
        raise Error(400, "unsafe_path", "Path is outside the permitted records or is a symlink")
    return target


def cache_path(settings, *parts):
    # System ancestors may be aliases (for example /var on macOS).
    # Keep rejecting a symlink at the cache directory itself or below it.
    cache = resolve_within(settings.cache_dir.parent.resolve(), settings.cache_dir.name)
    return resolve_within(cache, *parts)


_thread_lock = threading.Lock()


@contextmanager
def writer_lock(settings):
    with _thread_lock:
        fd = None
        try:
            try:
                path = resolve_within(settings.repo_root, ".rdash.lock")
                fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            except (OSError, Error) as exc:
                raise Error(503, "lock_unavailable", "Writer lock unavailable: " + (getattr(exc, "strerror", None) or "unsafe lock path"))
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (BlockingIOError, PermissionError):
                raise Error(503, "busy", "Another rdash writer holds the lock")
            os.ftruncate(fd, 0)
            os.write(fd, json.dumps({"pid": os.getpid(), "started": datetime.now(timezone.utc).isoformat()}).encode())
            yield
        finally:
            if fd is not None:
                os.close(fd)


LOCK_FORMAT = '{"session_id": "...", "started": "<ISO-8601 with timezone>", "task": "..."}'
LOCK_FRESH_SECONDS = 21600
PROJECT_LOCK = ".agent-lock"
CARD_LOCKS = (".locks", "cards")


def card_lock_path(project_dir, card):
    """`<project>/.locks/cards/<card ref>.lock`; an inbox card keeps its `inbox/` prefix."""
    card_ref(card)
    return Path(project_dir).joinpath(*CARD_LOCKS, card + ".lock")


def _session(session_id):
    return os.environ.get("RDASH_SESSION_ID", "") if session_id is None else session_id


def read_lock(path):
    """`(lock, age_seconds)` for an existing lock file, None when absent; unreadable fails closed."""
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return None
    try:
        if path.is_symlink():
            raise ValueError()
        lock = json.loads(path.read_text())
        started = datetime.fromisoformat(lock["started"].replace("Z", "+00:00"))
        if started.tzinfo is None:
            raise ValueError()
        age = (datetime.now(timezone.utc) - started).total_seconds()
        if age < 0:
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise Error(423, "project_locked_unreadable",
                    "Lock %s is not JSON %s, or its time is in the future" % (path, LOCK_FORMAT))
    return lock, age


def _foreign_fresh(path, session_id):
    state = read_lock(path)
    if state is None:
        return None
    lock, age = state
    if session_id and lock.get("session_id") == session_id:
        return None
    return lock if age < LOCK_FRESH_SECONDS else None


def card_locks(project_dir):
    """Every card lock in the project: [(card ref, path)]."""
    root = Path(project_dir).joinpath(*CARD_LOCKS)
    if not root.is_dir():
        return []
    return [(str(p.relative_to(root))[:-len(".lock")], p) for p in sorted(root.rglob("*.lock"))]


def agent_lock_state(project_dir, session_id=None, card=None):
    """Refuse a write while another session holds a fresh lock that covers it.

    Two scopes. The project lock `<project>/.agent-lock` covers the whole project
    (spec, state, new cards) and every card in it. A card lock
    `<project>/.locks/cards/<ref>.lock` covers one card, so sessions on different cards
    of one project do not block each other. `card` names the card a write touches;
    None means a project-wide write, which only the project lock refuses. A lock whose
    `session_id` equals `session_id` (default: $RDASH_SESSION_ID) is the caller's own.
    Unreadable locks fail closed; locks older than six hours do not refuse.
    """
    session_id = _session(session_id)
    lock = _foreign_fresh(Path(project_dir) / PROJECT_LOCK, session_id)
    if lock is not None:
        raise Error(423, "project_locked", "Project has a recent agent lock (%s); if it is your "
                    "session's, set RDASH_SESSION_ID to its session_id" % lock.get("session_id", "?"))
    if card is not None:
        lock = _foreign_fresh(card_lock_path(project_dir, card), session_id)
        if lock is not None:
            raise Error(423, "card_locked", "Card %s has a recent agent lock (%s); if it is your "
                        "session's, set RDASH_SESSION_ID to its session_id" % (card, lock.get("session_id", "?")))


def _lock_data(session_id, task):
    return (json.dumps(dict(session_id=session_id, started=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            task=task)) + "\n").encode()


def take_lock(project_dir, session_id, task, card=None):
    """Create the card lock (or, with card None, the project lock) for `session_id`.

    Exclusive create. The caller's own lock is refreshed in place. Refused while another
    session holds a fresh lock that overlaps: the project lock blocks every card; a card
    lock blocks that card and the project lock. A foreign stale lock is never taken over
    here: reconcile its jobs, then `release --stale`.
    """
    if not isinstance(session_id, str) or not session_id.strip():
        raise Error(400, "session_required", "Set RDASH_SESSION_ID (or pass --session) to take a lock")
    if not isinstance(task, str) or not task.strip() or len(task) > 200:
        raise Error(400, "invalid_task", "A short task description is required")
    project_dir = Path(project_dir)
    agent_lock_state(project_dir, session_id, card)
    if card is None:
        busy = [ref for ref, path in card_locks(project_dir) if _foreign_fresh(path, session_id) is not None]
        if busy:
            raise Error(423, "cards_locked", "Other sessions hold card locks: %s; take a card lock instead, "
                        "or wait for them" % ", ".join(busy))
        path = project_dir / PROJECT_LOCK
    else:
        path = card_lock_path(project_dir, card)
        path.parent.mkdir(parents=True, exist_ok=True)
    state = read_lock(path)
    if state is not None:
        if state[0].get("session_id") != session_id:
            raise Error(423, "lock_stale_foreign", "%s belongs to %s and is stale; reconcile its jobs, then "
                        "release it with --stale" % (path, state[0].get("session_id", "?")))
        publish_replace(path, _lock_data(session_id, task))
        return path
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "wb") as stream:
        stream.write(_lock_data(session_id, task))
        stream.flush()
        os.fsync(stream.fileno())
    return path


def release_lock(project_dir, session_id, card=None, stale=False):
    """Remove the caller's own lock; with `stale`, also a foreign lock older than six hours."""
    project_dir = Path(project_dir)
    path = project_dir / PROJECT_LOCK if card is None else card_lock_path(project_dir, card)
    state = read_lock(path)
    if state is None:
        return None
    lock, age = state
    own = bool(session_id) and lock.get("session_id") == session_id
    if not own and not (stale and age >= LOCK_FRESH_SECONDS):
        raise Error(423, "not_your_lock", "%s belongs to %s (%.1f h old); only its holder releases it, "
                    "or --stale once it is over 6 h old" % (path, lock.get("session_id", "?"), age / 3600))
    path.unlink()
    return path


def _publish(path, data, exclusive):
    path = Path(path)
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".rdash-", suffix=".tmp")
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        if exclusive:
            os.link(tmp, path)
        else:
            os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass


def publish_replace(path, data):
    _publish(path, data, False)


def publish_link(path, data):
    _publish(path, data, True)


def backup(settings, project, card_path):
    directory = cache_path(settings, "backups", project_id(project), card_path.stem)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    data = card_path.read_bytes()
    for index in range(101):
        path = resolve_within(directory, stamp + ("-" + str(index) if index else "") + ".md")
        try:
            publish_link(path, data)
            return path
        except FileExistsError:
            continue
    raise Error(503, "backup_exhausted", "Backup names exhausted")
