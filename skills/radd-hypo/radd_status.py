#!/usr/bin/env python3
"""Generate a card's execution status from live sources; never author it by hand.

Usage:
  radd_status.py PROJECT --task cards/FILE.md [--repo-root DIR] [--json] [--write]

Reads exactly one ``probe-status`` JSON fence from the selected card, then asks
the execution host what is actually true: do the declared artifacts exist, and
what does the scheduler say about the declared job IDs. Also reports whether the
card's ``probe-contract`` still passes the readiness checker.

Everything it cannot reach is reported ``unknown``. It never infers that a job
finished from an artifact's presence, nor that an artifact is valid from a job's
success -- those are different claims and both have been wrong here before.

Exit 0 means the report was produced, not that the work is going well.
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

# Support direct invocation from any working directory.
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dashboard.app import inspection

SCHEMA = 1
FENCE = re.compile(r"^ {0,3}```probe-status\s*$")
FENCE_END = re.compile(r"^ {0,3}```\s*$")
JOB_STATES_DONE = {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL"}
BEGIN = "<!-- radd-status:begin -->"
END = "<!-- radd-status:end -->"


def read_fence(text, path):
    """Return the single probe-status fence, or None when the card declares none."""
    lines, block, collecting = text.splitlines(), [], False
    for line in lines:
        if not collecting and FENCE.match(line):
            collecting = True
            continue
        if collecting:
            if FENCE_END.match(line):
                collecting = False
                break
            block.append(line)
    if not block:
        return None
    if sum(1 for line in lines if FENCE.match(line)) > 1:
        sys.exit(f"{path}: more than one probe-status fence; exactly one is supported")
    try:
        fence = json.loads("\n".join(block))
    except json.JSONDecodeError as exc:
        sys.exit(f"{path}: probe-status fence is not valid JSON: {exc}")
    if fence.get("schema_version") != SCHEMA:
        sys.exit(f"{path}: only probe-status schema_version {SCHEMA} is supported")
    return fence


class Host:
    """Run read-only probes locally or over an ssh alias."""

    def __init__(self, alias=None, timeout=60):
        self.alias = alias
        self.timeout = timeout
        self.reachable = None

    def run(self, command):
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", self.alias, command] \
            if self.alias else ["bash", "-c", command]
        try:
            done = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self.reachable = False
            return None
        self.reachable = True
        return done.stdout

    def stat(self, paths):
        """Metadata through the shared bounded inspection channel."""
        if not paths:
            return {}
        rows, status = inspection.observe_paths(self.alias or "", paths, timeout=self.timeout)
        self.reachable = status == "ok"
        kinds = {"file": "regular file", "dir": "directory", "symlink": "symbolic link", "other": "other"}
        return {path: ((row["size"], time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row["mtime"])),
                        kinds[row["kind"]]) if row["state"] == "present" else
                       None if row["state"] == "absent" else "unknown")
                for path, row in rows.items()}

    def jobs(self, ids):
        """Preserve per-task formatting, using shared scheduler observations."""
        if not ids:
            return {}
        rows, status = inspection.probe_jobs(self.alias or "", ids, timeout=self.timeout)
        self.reachable = status == "ok"
        def formatted(row):
            return (row["state"] + (" (" + row["elapsed"] + ")" if row.get("elapsed") else "") +
                    (" " + row["reason"] if row.get("reason") else ""))
        return {job: self._match({task: formatted(row) for task, row in result.get("tasks", {}).items()}, job)
                for job, result in rows.items()}

    @staticmethod
    def _match(state, job):
        """Resolve one declared id, including an array job given by its base id.

        sacct/squeue report array tasks as `<base>_<task>`, so a bare base id
        declared on a card would otherwise read `unknown` while its tasks are
        finishing -- the one answer this tool must never give wrongly.
        """
        key = str(job)
        if key in state:
            return state[key]
        tasks = {k: v for k, v in state.items() if k.startswith(f"{key}_")}
        if not tasks:
            return "unknown"
        if len(set(tasks.values())) == 1:
            return f"{next(iter(tasks.values()))} [{len(tasks)} array tasks]"
        if len(tasks) <= 5:
            return "; ".join(f"{k.split('_', 1)[1]}: {v}" for k, v in sorted(tasks.items()))
        # A large array: count tasks per state, and name the tasks outside the
        # commonest state, instead of one row per task.
        by_state = {}
        for k, v in tasks.items():
            by_state.setdefault(v.split()[0] if v else "unknown", []).append(k.split("_", 1)[1])
        common = max(by_state, key=lambda st: len(by_state[st]))
        parts = [f"{st} ×{len(ids)}" + ("" if st == common else
                 " (tasks " + ", ".join(sorted(ids, key=lambda i: (len(i), i))[:10]) + (", …" if len(ids) > 10 else "") + ")")
                 for st, ids in sorted(by_state.items(), key=lambda kv: -len(kv[1]))]
        return f"{'; '.join(parts)} [{len(tasks)} array tasks]"


def contract_state(repo_root, project, task):
    checker = repo_root / "probe" / "scripts" / "check_readiness.py"
    if not checker.is_file():
        return "unknown (checker not found)"
    done = subprocess.run(
        [sys.executable, "-B", str(checker), f"projects/{project}", "--task", task],
        capture_output=True, text=True, cwd=repo_root)
    return "passes" if done.returncode == 0 else f"FAILS (exit {done.returncode})"


def human(size):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def render(report):
    out = [f"*Generated {report['generated_at']} by `{report['command']}`. Do not hand-edit.*", ""]
    reach = ("reachable" if report["reachable"] else "nothing declared to observe" if report["reachable"] is None
             else "UNREACHABLE — rows below are stale or unknown")
    out.append(f"Contract: **{report['contract']}** · execution host: `{report['host'] or 'local'}` ({reach})")
    out.append("")
    if report["artifacts"]:
        out += ["| artifact | state | size | modified |", "|---|---|---:|---|"]
        for name, item in report["artifacts"].items():
            out.append(f"| {name} | {item['state']} | {item.get('size') or '—'} | {item.get('mtime') or '—'} |")
        out.append("")
    if report["jobs"]:
        out += ["| job | scheduler state |", "|---|---|"]
        for job, state in report["jobs"].items():
            out.append(f"| `{job}` | {state} |")
        out.append("")
    if report.get("malformed"):
        out += ["Not observed (declared as something other than an absolute path): "
                + ", ".join(report["malformed"]), ""]
    out.append("A present artifact is not a validated one, and a COMPLETED job is not a "
               "correct result; both need their own check.")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project")
    parser.add_argument("--task", required=True, help="project-relative card path, e.g. cards/x.md")
    parser.add_argument("--repo-root", default=".", help="research checkout containing projects/ (default: cwd)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true",
                        help=f"splice the report into the card between {BEGIN} and {END}")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    card = repo_root / "projects" / args.project / args.task
    if not card.is_file():
        sys.exit(f"card not found: {card}")
    text = card.read_text(encoding="utf-8")

    fence = read_fence(text, card)
    if fence is None:
        sys.exit(f"{card}: no probe-status fence. Add one declaring `artifacts` and `jobs`, "
                 "so status is generated from named sources rather than remembered.")

    host = Host(fence.get("host"))
    # Observe only what the schema allows (path strings, job ids); report the rest
    # as malformed rather than crash or guess what a list or an object meant.
    declared = fence.get("artifacts", {}) if isinstance(fence.get("artifacts"), dict) else {}
    artifacts = {k: v for k, v in declared.items() if isinstance(v, str) and v.startswith("/")}
    malformed = sorted(set(declared) - set(artifacts))
    ids = []
    for job in fence.get("jobs", []) if isinstance(fence.get("jobs"), list) else []:
        job = job.get("id") if isinstance(job, dict) else job
        if not isinstance(job, bool) and re.fullmatch(r"[0-9]{1,12}", str(job)) and int(job) not in ids:
            ids.append(int(job))
    # Launches since 2026-10-23 are recorded as receipts (projects/<p>/runs/), not in the fence.
    from dashboard.app import receipts
    ids += [r["job"] for r in receipts.load(SimpleNamespace(repo_root=repo_root), args.project)
            if r.get("card") == args.task[len("cards/"):] and r["host"] == fence.get("host") and r["job"] not in ids]
    stats = host.stat(list(artifacts.values()))
    jobs = host.jobs(ids)

    resolved = {}
    for name, path in artifacts.items():
        item = stats.get(path)
        if item == "unknown" or item is None and host.reachable is False:
            resolved[name] = {"state": "unknown", "path": path}
        elif item is None:
            resolved[name] = {"state": "**absent**", "path": path}
        elif item[2] == "directory":
            # A directory's own size says nothing about its contents; counting
            # them is a different probe, so report presence and stop there.
            resolved[name] = {"state": "present (dir)", "path": path,
                              "size": "—", "mtime": item[1]}
        else:
            resolved[name] = {"state": "present", "path": path,
                              "size": human(item[0]), "mtime": item[1]}

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "command": f"radd_status.py {args.project} --task {args.task}",
        "card": str(card.relative_to(repo_root)),
        "host": fence.get("host"),
        "reachable": host.reachable,
        "contract": contract_state(repo_root, args.project, args.task),
        "artifacts": resolved,
        "malformed": malformed,
        "jobs": jobs,
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return

    body = render(report)
    if not args.write:
        print(body)
        return

    if BEGIN not in text or END not in text:
        sys.exit(f"{card}: add the {BEGIN} / {END} markers where the report should land.")
    head, _, rest = text.partition(BEGIN)
    _, _, tail = rest.partition(END)
    card.write_text(f"{head}{BEGIN}\n{body}\n{END}{tail}", encoding="utf-8")
    print(f"wrote status into {report['card']}")


if __name__ == "__main__":
    main()
