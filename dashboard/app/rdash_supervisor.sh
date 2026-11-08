#!/bin/sh
# Keep process ownership checks on the same host as the durable runtime store.
RDASH_SUPERVISOR_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
export RDASH_SUPERVISOR_ROOT
exec python3 -B - "$@" <<'PY'
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

root = Path(os.environ['RDASH_SUPERVISOR_ROOT'])
sys.path.insert(0, str(root))
from dashboard.app.config import Settings
from dashboard.app.safety import cache_path, publish_replace

def owned(path):
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    pid = data['pid']
    if type(pid) is not int or pid <= 1:
        return None
    try:
        command = (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0')
        token = data['token'].encode()
        environment = (Path('/proc') / str(pid) / 'environ').read_bytes().split(b'\0')
        return pid if (b'dashboard.supervisor.cli' in command and b'serve' in command
                       and b'RDASH_SUPERVISOR_TOKEN=' + token in environment) else None
    except (OSError, ValueError):
        return None

try:
    action = sys.argv[1] if len(sys.argv) == 2 else ''
    if action not in ('start', 'stop', 'status', 'restart'):
        raise ValueError('Usage: rdash_supervisor.sh start|stop|status|restart')
    settings = Settings.from_env()
    directory = cache_path(settings, 'supervisor')
    directory.mkdir(parents=True, exist_ok=True)
    lock = os.open(cache_path(settings, 'supervisor', 'lifecycle.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX)
    path = cache_path(settings, 'supervisor', 'pid.json')
    pid = owned(path)
    if action in ('stop', 'restart') and pid:
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 30
        while owned(path) and time.monotonic() < deadline:
            time.sleep(.1)
        if owned(path):
            raise RuntimeError('Supervisor still finishing; no force kill or job cancellation performed')
        path.unlink(missing_ok=True)
        pid = None
    if action in ('start', 'restart') and not pid:
        import uuid
        token = uuid.uuid4().hex
        env = dict(os.environ, RDASH_SUPERVISOR_TOKEN=token)
        logpath = cache_path(settings, 'supervisor', 'service.log')
        with logpath.open('ab') as log:
            child = subprocess.Popen([sys.executable, '-B', '-m', 'dashboard.supervisor.cli', 'serve'],
                                     cwd=str(root), env=env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=log, start_new_session=True)
        publish_replace(path, json.dumps(dict(pid=child.pid, token=token)).encode())
        time.sleep(.2)
        if child.poll() is not None:
            path.unlink(missing_ok=True)
            raise RuntimeError('Startup failed; inspect ' + str(logpath))
        pid = child.pid
    ready_path = cache_path(settings, 'supervisor', 'ready.json')
    ready = json.loads(ready_path.read_text()) if ready_path.exists() else {}
    status = 'probe=pass' if ready.get('pid') == pid and ready.get('probe') == 'pass' else 'initialization pending'
    print('rdash supervisor: process running pid=' + str(pid) + ' ' + status if pid else 'rdash supervisor: stopped')
except Exception as exc:
    print('rdash supervisor: ' + str(exc), file=sys.stderr)
    sys.exit(1)
PY
