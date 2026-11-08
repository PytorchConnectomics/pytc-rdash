#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/rdash_env.sh"
# Keep lifecycle logic stdlib-only, including the fallback on hosts without flock.
RDASH_SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export RDASH_SCRIPT_DIR

# Live inspection defaults. Without a permitted host the board can declare a
# job or a result but never observe one, so every card reads `unknown` and the
# columns look broken when they are merely unwired. rdash ships no host: the
# team's systemd unit, ~/.config/rdash/env or `hub.sh` exports RDASH_SSH_HOSTS,
# and the roots it may read are pinned in the team's projects/config/rdash-roots.yaml
# (a host listed without an entry there still reads nothing). Unset, the board
# touches no remote host.
: "${RDASH_SSH_HOSTS=}"
export RDASH_SSH_HOSTS
exec python3 -B - "$@" <<'PY'
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

script = Path(os.environ["RDASH_SCRIPT_DIR"]) / "server.py"
sys.path.insert(0, str(script.parents[2]))
from dashboard.app.config import Settings
from dashboard.app.safety import cache_path, publish_replace


def alive(pid):
    try:
        os.kill(pid, 0)
        stat = Path("/proc") / str(pid) / "stat"
        if stat.exists():
            state = stat.read_text().rsplit(")", 1)[1].split()[0]
        else:
            state = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "stat="], text=True).strip()
        return bool(state) and not state.startswith("Z")
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return False


def owned():
    if not pidfile.exists():
        return None
    try:
        data = json.loads(pidfile.read_text())
        pid = data["pid"]
        if not isinstance(pid, int) or pid <= 1:
            raise ValueError()
        proc = Path("/proc") / str(pid) / "cmdline"
        if proc.exists():
            command = proc.read_bytes().decode().split("\0")
            expected = [str(script), "--repo-root", str(settings.repo_root), "--cache-dir", str(settings.cache_dir), "--port", str(data["port"])]
            matches = any(command[i:i + len(expected)] == expected for i in range(len(command)))
        else:
            command = subprocess.check_output(["ps", "-p", str(pid), "-o", "command="], text=True)
            matches = str(script) in command and ("--repo-root " + str(settings.repo_root)) in command and ("--cache-dir " + str(settings.cache_dir)) in command
        if data["repo_root"] != str(settings.repo_root) or data["cache_dir"] != str(settings.cache_dir) or not matches or not alive(pid):
            raise ValueError()
        return data
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print("rdash: stale pidfile removed; no process signalled", flush=True)
        pidfile.unlink(missing_ok=True)
        return None


def stop():
    data = owned()
    if data:
        pid = data["pid"]
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 10
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(.05)
        if alive(pid):
            os.kill(pid, signal.SIGKILL)
        pidfile.unlink(missing_ok=True)
    print("rdash: stopped", flush=True)


def start():
    data = owned()
    if data:
        print("http://127.0.0.1:" + str(data["port"]), flush=True)
        return 0
    command = [sys.executable, "-B", str(script), "--repo-root", str(settings.repo_root),
               "--cache-dir", str(settings.cache_dir), "--port", str(settings.port)]
    logpath = cache_path(settings, "rdash.log")
    with logpath.open("wb") as log:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    url = "http://127.0.0.1:" + str(settings.port)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + 10
    try:
        while child.poll() is None and time.monotonic() < deadline:
            try:
                request = urllib.request.Request(url + "/api/health", headers={"Host": "127.0.0.1:" + str(settings.port)})
                with opener.open(request, timeout=.3) as response:
                    health = json.load(response)
                if health.get("pid") == child.pid and child.poll() is None:
                    publish_replace(pidfile, json.dumps(dict(pid=child.pid, port=settings.port,
                        repo_root=str(settings.repo_root), cache_dir=str(settings.cache_dir),
                        started=time.time(), cmd=command)).encode())
                    print(url, flush=True)
                    return 0
            except (OSError, ValueError):
                pass
            time.sleep(.1)
        print("rdash: startup failed", file=sys.stderr)
        print("\n".join(logpath.read_text(errors="replace").splitlines()[-20:]), file=sys.stderr)
        return 1
    finally:
        if not pidfile.exists():
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
            child.wait()


try:
    action = sys.argv[1] if len(sys.argv) == 2 else ""
    if action not in ("start", "stop", "status", "restart"):
        raise ValueError("Usage: research_dash.sh start|stop|status|restart")
    settings = Settings.from_env()
    if settings.port == 0:
        raise ValueError("Launcher port 0 is test-only; choose a nonzero port")
    cache_path(settings).mkdir(parents=True, exist_ok=True)
    pidfile = cache_path(settings, "rdash.pid")
    lockpath = cache_path(settings, "rdash.start.lock")
    fd = os.open(lockpath, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if action in ("stop", "restart"):
            stop()
        if action in ("start", "restart"):
            sys.exit(start())
        if action == "status":
            data = owned()
            print("rdash: running http://127.0.0.1:" + str(data["port"]) if data else "rdash: stopped")
except Exception as exc:
    print("rdash: " + str(exc), file=sys.stderr)
    sys.exit(1)
PY
