"""Keep the existing rdash lifecycle under systemd without starting a supervisor.

The lifecycle script owns its server pidfile. This foreground wrapper monitors
that exact server over loopback, and systemd restarts it if health fails.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import urllib.request


def main():
    launcher = Path(__file__).with_name("research_dash.sh")
    quit_event = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: quit_event.set())
    port = int(os.environ.get("RESEARCH_DASH_PORT", "8766"))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = "http://127.0.0.1:%d/api/health" % port
    subprocess.run([str(launcher), "start"], check=True)
    try:
        with opener.open(url, timeout=5) as response:
            expected_pid = json.load(response)["pid"]
        while not quit_event.wait(10):
            with opener.open(url, timeout=5) as response:
                if json.load(response).get("pid") != expected_pid:
                    raise RuntimeError("rdash server identity changed")
    finally:
        subprocess.run([str(launcher), "stop"], check=True)


if __name__ == "__main__":
    main()
