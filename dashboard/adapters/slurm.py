"""Bounded SLURM submission, identity lookup, and allocation accounting."""
import datetime
import re

from dashboard.app import inspection
from dashboard.supervisor.store import Error


TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY", "BOOT_FAIL", "DEADLINE", "PREEMPTED"}


def elapsed_seconds(text):
    match = re.fullmatch(r"(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)", text)
    if not match:
        raise Error("invalid_accounting")
    days, hours, minutes, seconds = (int(v or 0) for v in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


class Slurm:
    def __init__(self, user, exchange=inspection._exchange):
        self.user = user
        self.exchange = exchange

    def _run(self, argv):
        raw, status = self.exchange(argv, b"", timeout=30)
        if status != "ok":
            raise Error("scheduler_unknown", status=503, transport=status)
        return raw.decode("utf-8", errors="strict")

    def submit(self, dispatch, wrapper, manifest, cwd, memory, partition):
        seconds = dispatch["time_limit_s"]
        limit = "%02d:%02d:%02d" % (seconds // 3600, seconds // 60 % 60, seconds % 60)
        result = self._run(["sbatch", "--parsable", "--nodes=1", "--ntasks=1",
                            "--cpus-per-task=" + str(dispatch["cpus"]), "--mem=" + memory,
                            "--time=" + limit, "--partition=" + partition,
                            "--job-name=" + dispatch["job_name"], "--chdir=" + str(cwd),
                            "--output=" + str(manifest.parent / "%x_%j.out"),
                            str(wrapper), str(manifest)]).strip()
        if not re.fullmatch(r"[1-9][0-9]*(?:;[A-Za-z0-9._-]+)?", result):
            raise Error("ambiguous_submission")
        return result.split(";", 1)[0]

    def lookup_by_name(self, name, since):
        date = datetime.datetime.fromtimestamp(since, datetime.timezone.utc).strftime("%Y-%m-%d")
        queued = self._run(["squeue", "-u", self.user, "-h", "-o", "%i|%j|%T"])
        accounted = self._run(["sacct", "-u", self.user, "--name=" + name, "-n", "-P", "-S", date,
                               "--format=JobID,JobName,State,Elapsed,AllocCPUS"])
        found = {}
        for line in (accounted + "\n" + queued).splitlines():
            fields = line.strip().split("|")
            if len(fields) >= 3 and re.fullmatch(r"[1-9][0-9]*", fields[0]) and fields[1] == name:
                found[fields[0]] = dict(job_id=fields[0], job_name=name, state=fields[2].split()[0].rstrip("+"))
        return list(found.values())

    def settle(self, job_id):
        if not re.fullmatch(r"[1-9][0-9]*", str(job_id)):
            raise Error("invalid_job_id")
        output = self._run(["sacct", "-j", str(job_id), "-X", "-n", "-P", "--format=JobID,State,Elapsed,AllocCPUS"])
        for line in output.splitlines():
            fields = line.strip().split("|")
            if len(fields) < 4 or fields[0] != str(job_id):
                continue
            state = fields[1].split()[0].rstrip("+")
            if state in TERMINAL:
                try:
                    cpus = int(fields[3])
                    if cpus < 1:
                        raise ValueError()
                    return dict(state=state, cpu_hours=cpus * elapsed_seconds(fields[2]) / 3600,
                                alloc_cpus=cpus, elapsed=fields[2])
                except ValueError:
                    raise Error("invalid_accounting")
        return None

    def cancel(self, job_id):
        if not re.fullmatch(r"[1-9][0-9]*", str(job_id)):
            raise Error("invalid_job_id")
        self._run(["scancel", str(job_id)])
