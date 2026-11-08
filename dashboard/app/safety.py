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


def agent_lock_state(project_dir):
    path = Path(project_dir) / ".agent-lock"
    if not path.exists() and not path.is_symlink():
        return
    try:
        if path.is_symlink():
            raise ValueError()
        started = datetime.fromisoformat(json.loads(path.read_text())["started"].replace("Z", "+00:00"))
        if started.tzinfo is None:
            raise ValueError()
        age = (datetime.now(timezone.utc) - started).total_seconds()
        if age < 0:
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise Error(423, "project_locked_unreadable", "Project lock timestamp is missing, unreadable, or in the future")
    if age < 21600:
        raise Error(423, "project_locked", "Project has a recent agent lock")


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
