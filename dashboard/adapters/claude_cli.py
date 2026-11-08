"""Invoke a bounded, tool-free Claude coordinator in an isolated working directory."""
import os
import subprocess
import uuid

from dashboard.app.safety import cache_path, publish_replace
from dashboard.supervisor.store import Error


class Claude:
    def __init__(self, settings, run=subprocess.run, env=None):
        self.settings = settings
        self.run = run
        source = os.environ if env is None else env
        self.env = {k: v for k, v in source.items() if k in settings.coordinator_env_allowlist}
        self.probed = False

    def invoke(self, packet, run_id):
        directory = cache_path(self.settings, "supervisor", "runs", run_id)
        directory.mkdir(parents=True, exist_ok=False)
        try:
            result = self.run(["claude", "--print", "--output-format", "text", "--no-session-persistence", "--tools", ""],
                              input=packet, text=True, capture_output=True, cwd=str(directory), env=self.env,
                              timeout=self.settings.coordinator_timeout_s)
        except (OSError, subprocess.SubprocessError) as exc:
            raise Error("provider_invocation_failed", "Claude could not complete invocation: " + str(exc), status=503)
        if result.returncode != 0:
            raise Error("provider_refused", "Claude exited with status %s; check provider authentication and "
                        "CLAUDE_CONFIG_DIR/XDG_CONFIG_HOME configuration" % result.returncode, status=503)
        if len(result.stdout.encode()) > self.settings.coordinator_packet_max_bytes:
            raise Error("coordinator_reply_too_large")
        return result.stdout

    def probe(self):
        if self.probed:
            return
        root = cache_path(self.settings, "supervisor")
        root.mkdir(parents=True, exist_ok=True)
        sentinel = cache_path(self.settings, "supervisor", "sentinel-" + uuid.uuid4().hex)
        token = uuid.uuid4().hex
        publish_replace(sentinel, token.encode())
        try:
            reply = self.invoke("Read the file " + str(sentinel) + " and print its exact contents. "
                                "If you cannot read it, print exactly RDASH_NO_TOOLS.", "probe-" + uuid.uuid4().hex)
            if token in reply or "RDASH_NO_TOOLS" not in reply:
                raise Error("sentinel_probe_failed", status=503)
            self.probed = True
        finally:
            sentinel.unlink()
