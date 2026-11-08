"""Injected runtime configuration; importing modules has no filesystem effects."""
import json
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

COORDINATOR_ENV_ALLOWLIST = (
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "ANTHROPIC_API_KEY",
    "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME",
)


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    cache_dir: Path
    port: int
    bind_host: str = field(default="127.0.0.1", init=False)

    config_dir: Path = None
    project_labels: dict = field(default_factory=dict, init=False)
    owner: str = ""
    require_owner: bool = field(default=False, init=False)
    host_alias: str = ""
    ssh_hosts: tuple = ()
    stat_local: bool = False
    stat_roots: tuple = ()
    result_roots: tuple = ()
    default_result_roots: tuple = field(default=(), init=False)
    coordinator_timeout_s: int = 180
    coordinator_packet_max_bytes: int = 120000
    supervisor_poll_s: int = 15
    settle_window_s: int = 900
    coordinator_env_allowlist: tuple = COORDINATOR_ENV_ALLOWLIST

    @property
    def supervisor_db(self):
        from .safety import cache_path
        return cache_path(self, "supervisor", "runtime.db")

    def __post_init__(self):
        if any(type(value) is not int or value <= 0 for value in (
                self.coordinator_timeout_s, self.coordinator_packet_max_bytes,
                self.supervisor_poll_s, self.settle_window_s)):
            raise ValueError("Supervisor limits must be positive integers")
        directory = self.config_dir if self.config_dir is not None else self.repo_root / "projects/config"
        if directory != self.repo_root / "projects/config" and (not directory.is_absolute() or not directory.is_dir()):
            raise ValueError("RDASH_CONFIG_DIR must be an existing absolute directory")
        object.__setattr__(self, "config_dir", directory)
        object.__setattr__(self, "project_labels", load_labels(directory))
        if self.owner and not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", self.owner):
            raise ValueError("Invalid RDASH_OWNER")
        try:
            with (directory / "rdash-owner.json").open("rb") as source:
                raw = source.read(65537)
            if len(raw) > 65536:
                raise ValueError("owner configuration too large")
            config = json.loads(raw)
            if not isinstance(config, dict) or set(config) != {"require_owner"} or type(config["require_owner"]) is not bool:
                raise ValueError("expected require_owner boolean")
            object.__setattr__(self, "require_owner", config["require_owner"])
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            raise ValueError("Invalid rdash-owner.json: " + str(exc)) from exc
        defaults = []
        for project in (self.repo_root / "projects").iterdir():
            if project.is_dir() and not project.is_symlink():
                defaults.extend((project.name, os.path.realpath(str(project / name)))
                                for name in ("results", "logs"))
        object.__setattr__(self, "default_result_roots", tuple(defaults))

    @property
    def local_enabled(self):
        return self.stat_local or bool(self.host_alias)

    @classmethod
    def from_env(cls, env=None, port=None):
        env = os.environ if env is None else env
        root = Path(env.get("RDASH_REPO_ROOT", Path(__file__).resolve().parents[2])).resolve()
        if not (root / "projects").is_dir():
            raise ValueError("Repository must contain projects/")
        home = Path(env.get("HOME", str(Path.home())))
        default = (home / "Library/Caches" if sys.platform == "darwin" else
                   Path(env.get("XDG_CACHE_HOME", home / ".cache")))
        cache = Path(env.get("RESEARCH_DASH_CACHE", default / "dw-research-dashboard")).expanduser().absolute()
        value = int(port if port is not None else env.get("RESEARCH_DASH_PORT", 8766))
        if not 0 <= value <= 65535:
            raise ValueError("Port must be between 0 and 65535")
        directory = Path(env["RDASH_CONFIG_DIR"]) if "RDASH_CONFIG_DIR" in env else root / "projects/config"
        if "RDASH_CONFIG_DIR" in env and (not directory.is_absolute() or not directory.is_dir()):
            raise ValueError("RDASH_CONFIG_DIR must be an existing absolute directory")
        return cls(root, cache, value,
                   config_dir=directory if "RDASH_CONFIG_DIR" in env else None,
                   owner=env.get("RDASH_OWNER", ""),
                   host_alias=env.get("RDASH_HOST_ALIAS", "").strip(),
                   ssh_hosts=tuple(x.strip() for x in env.get("RDASH_SSH_HOSTS", "").split(",") if x.strip()),
                   stat_local=env.get("RDASH_STAT_LOCAL") == "1",
                   result_roots=load_roots(directory, env.get("RDASH_HOST_ALIAS", "").strip(),
                       tuple(x.strip() for x in env.get("RDASH_SSH_HOSTS", "").split(",") if x.strip())),
                   stat_roots=tuple(x.strip() for x in env.get("RDASH_STAT_ROOTS", "").split(",") if x.strip()),
                   coordinator_timeout_s=int(env.get("COORDINATOR_TIMEOUT_S", 180)),
                   coordinator_env_allowlist=COORDINATOR_ENV_ALLOWLIST + tuple(
                       x.strip() for x in env.get("COORDINATOR_ENV_ALLOWLIST", "").split(",") if x.strip()),
                   coordinator_packet_max_bytes=int(env.get("COORDINATOR_PACKET_MAX_BYTES", 120000)),
                   supervisor_poll_s=int(env.get("RDASH_SUPERVISOR_POLL_S", 15)),
                   settle_window_s=int(env.get("RDASH_SETTLE_WINDOW_S", 900)))


def load_roots(config_dir, host_alias="", ssh_hosts=(), name="rdash-roots.yaml"):
    """Read a strict YAML subset: host keys with lists of absolute roots.

    Root symlinks resolve once here, on the owning host. Remote configuration
    resolution uses the same bounded fixed transport, only for permitted hosts.
    No configuration file is created. Invalid configuration fails closed.
    """
    path = Path(config_dir) / name
    try:
        with path.open("rb") as source:
            raw = source.read(65537)
    except FileNotFoundError:
        return ()
    if len(raw) > 65536:
        raise ValueError(name + " exceeds 64 KiB")
    rows, host = [], None
    for line in raw.decode("utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}:", line):
            host = line[:-1]
        elif host is not None and line.startswith("  - /"):
            value = line[4:]
            if "\x00" in value or value != value.strip():
                raise ValueError("Invalid result root")
            value = os.path.normpath(value)
            rows.append(("local" if host in ("local", host_alias) else host, value))
        else:
            raise ValueError("Expected host: and two-space - /absolute/root")
    from . import inspection
    pinned = []
    for host in dict.fromkeys(host for host, _ in rows):
        paths = [path for owner, path in rows if owner == host]
        if host == "local":
            resolved = tuple(os.path.realpath(path) for path in paths)
        elif host in ssh_hosts:
            resolved = inspection.resolve_roots(host, paths)
        else:
            continue
        if resolved is None:
            _unresolved[host] = tuple(paths)
            pinned.append((host, None))
        else:
            pinned.extend((host, path) for path in resolved)
    return tuple(pinned)


# Remote roots whose host was unreachable at load: retried on use, so a board
# started while the host was down recovers without a restart.
_unresolved = {}
_retry_lock = threading.Lock()


def _retry_roots(settings, host):
    with _retry_lock:
        if (host, None) not in settings.result_roots or host not in _unresolved:
            return
        from . import inspection
        resolved = inspection.resolve_roots(host, _unresolved[host])
        if resolved is None:
            return
        rows = tuple(row for row in settings.result_roots if row != (host, None))
        object.__setattr__(settings, "result_roots", rows + tuple((host, path) for path in resolved))
        del _unresolved[host]


def roots_for(settings, project, host):
    """Defaults are on the board host only; remote roots are explicit."""
    if host:
        _retry_roots(settings, host)
    roots = [root for owner, root in settings.result_roots if owner == (host or "local")]
    if not host:
        roots.extend(root for owner, root in settings.default_result_roots if owner == project)
    return (None,) if None in roots else tuple(sorted(set(roots)))


def load_labels(config_dir):
    """Load a bounded label map once per Settings instance."""
    import json
    import logging
    try:
        with (config_dir / "project-labels.json").open("rb") as source:
            raw = source.read(65537)
        if len(raw) > 65536:
            raise ValueError("exceeds 64 KiB")
        labels = json.loads(raw)
        if not isinstance(labels, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in labels.items()):
            raise ValueError("expected string-to-string object")
        return labels
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logging.warning("Invalid project-labels.json: %s", exc)
        return {}
