"""Run receipts: the record of a submitted job, kept apart from the card.

A card holds intent and conclusions and changes in git like any file. What a
submission produces -- job ID, host, code commit, staged scripts, output folder
-- is written once, by whatever submitted the job, as a receipt beside the run:

    <runs root>/<project>/receipts/<job>.json      rsub / launch.py
    <runs root>/focus/receipts/<job>.json          fsubmit (names its F-id)

The hub only reads. `collect` copies new receipts over SSH into its board
checkout as projects/<project>/runs/<host>-<job>.json (unique names, so they
never conflict in git); the board joins them to cards by `card`, and the sync
commits them. Nothing has to reach the hub, and a hub outage loses nothing: the
receipts wait on the host.

`unrecorded` lists this user's recent jobs on each host that neither a receipt
nor a card's probe-status fence names. Prototypes are allowed; they are listed,
not blocked, and `attach` records one after the fact.

    python3 -B -m dashboard.app.receipts collect
    python3 -B -m dashboard.app.receipts unrecorded [--project P] [--since YYYY-MM-DD]
    python3 -B -m dashboard.app.receipts attach --host H --job J --project P [--card cards/x.md] [--note TEXT]
"""
import argparse
import getpass
import json
import os
import re
import socket
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone

from . import inspection
from .config import Settings, load_roots
from .jobs import declared_status
from .safety import Error, card_ref, project_id, publish_link, resolve_within, writer_lock

SCHEMA = "rdash-receipt/1"
VIA = ("rsub", "fsubmit", "attach")
# Jobs submitted before receipts existed are recorded in card fences or nowhere;
# listing them all as unrecorded would bury the ones that matter.
CUTOVER = "2026-10-23"
MAX_RECEIPT = 64 * 1024
STEP = re.compile(r"[a-z][a-z0-9-]{0,31}")
FOCUS = re.compile(r"F-[0-9]{3}")
HEX40 = re.compile(r"[0-9a-f]{40}")
TEXT = re.compile(r"[\x20-\x7e]*")
RUN_NAME = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]{0,63})-([1-9][0-9]{0,11})\.json")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def submitter():
    return "%s@%s" % (getpass.getuser(), socket.gethostname().split(".")[0])


def _text(value, limit, field):
    if not isinstance(value, str) or len(value) > limit or not TEXT.fullmatch(value):
        raise ValueError("invalid " + field)
    return value


def _path(value, field):
    _text(value, 512, field)
    if not value.startswith("/") or "\x00" in value:
        raise ValueError("invalid " + field)
    return value


def validate(data):
    """Normalize a receipt; unknown keys are dropped, a malformed field rejects it."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("not a " + SCHEMA + " receipt")
    out = dict(schema=SCHEMA)
    job = data.get("job")
    if isinstance(job, str) and re.fullmatch(r"[1-9][0-9]{0,11}", job):
        job = int(job)
    if isinstance(job, bool) or not isinstance(job, int) or not 0 < job < 10 ** 12:
        raise ValueError("invalid job")
    out["job"] = job
    host = data.get("host")
    if not isinstance(host, str) or not inspection.ALIAS.fullmatch(host):
        raise ValueError("invalid host")
    out["host"] = host
    if data.get("via") not in VIA:
        raise ValueError("invalid via")
    out["via"] = data["via"]
    for key in ("project", "card", "step", "focus"):
        value = data.get(key)
        if value is None:
            continue
        try:
            if key == "project":
                project_id(value)
            elif key == "card":
                card_ref(value)
            elif not (STEP if key == "step" else FOCUS).fullmatch(value):
                raise ValueError()
        except (Error, TypeError, ValueError):
            raise ValueError("invalid " + key)
        out[key] = value
    if "card" in out and "project" not in out:
        raise ValueError("a card needs its project")
    for key, limit in (("submitted_at", 40), ("submitted_by", 120), ("job_name", 120), ("note", 500)):
        if data.get(key) is not None:
            out[key] = _text(data[key], limit, key)
    for key in ("snapshot", "results", "workdir", "script"):
        if data.get(key) is not None:
            out[key] = _path(data[key], key)
    argv = data.get("argv")
    if argv is not None:
        if not isinstance(argv, list) or len(argv) > 64:
            raise ValueError("invalid argv")
        out["argv"] = [_text(a, 600, "argv") for a in argv]
    research = data.get("research")
    if research is not None:
        if not isinstance(research, dict):
            raise ValueError("invalid research")
        out["research"] = {k: _text(research[k], 120, "research." + k)
                           for k in ("ref", "revision", "scripts_tree") if research.get(k) is not None}
    code = data.get("code")
    if code is not None:
        if not isinstance(code, dict):
            raise ValueError("invalid code")
        row = dict(path=_path(code.get("path"), "code.path"))
        if code.get("commit") is not None:
            if not isinstance(code["commit"], str) or not HEX40.fullmatch(code["commit"]):
                raise ValueError("invalid code.commit")
            row["commit"] = code["commit"]
        if not isinstance(code.get("dirty", False), bool):
            raise ValueError("invalid code.dirty")
        row["dirty"] = code.get("dirty", False)
        for key, limit in (("remote", 300), ("patch", 80), ("patch_sha256", 64), ("error", 200)):
            if code.get(key) is not None:
                row[key] = _text(code[key], limit, "code." + key)
        out["code"] = row
    if data.get("collected_at") is not None:
        out["collected_at"] = _text(data["collected_at"], 40, "collected_at")
    return out


def encode(receipt):
    return (json.dumps(receipt, indent=1, sort_keys=True) + "\n").encode("utf-8")


# --- the repository side: projects/<project>/runs/<host>-<job>.json ---------

def runs_dir(settings, project):
    return resolve_within(settings.repo_root, "projects", project_id(project), "runs")


def load(settings, project):
    """Every valid receipt of one project, newest first."""
    directory = runs_dir(settings, project)
    rows = []
    try:
        entries = sorted(os.scandir(directory), key=lambda e: e.name)
    except OSError:
        return rows
    for entry in entries:
        match = RUN_NAME.fullmatch(entry.name)
        if not match or entry.is_symlink() or not entry.is_file(follow_symlinks=False):
            continue
        try:
            with open(entry.path, "rb") as source:
                receipt = validate(json.loads(source.read(MAX_RECEIPT + 1)))
        except (OSError, ValueError, RecursionError):
            continue
        if (receipt["host"], str(receipt["job"])) != match.groups() or receipt.get("project", project) != project:
            continue
        receipt.setdefault("project", project)
        rows.append(receipt)
    rows.sort(key=lambda r: (r.get("submitted_at", ""), r["job"]), reverse=True)
    return rows


def by_card(settings, project):
    index = {}
    for receipt in load(settings, project):
        index.setdefault(receipt.get("card"), []).append(receipt)
    return index


def annotate(records, settings, project):
    """Attach each card's receipts; launch.py no longer writes job IDs into cards."""
    index = by_card(settings, project)
    for record in records:
        record["receipts"] = index.get(record["card"], [])
        if record.get("step_jobs") is not None:
            for receipt in record["receipts"]:
                if receipt.get("step"):
                    jobs = record["step_jobs"].setdefault(receipt["step"], [])
                    if receipt["job"] not in jobs:
                        jobs.append(receipt["job"])
    return records


def store(settings, receipt):
    """Publish one receipt into the repository; an existing one is never rewritten."""
    path = resolve_within(runs_dir(settings, receipt["project"]), "%s-%d.json" % (receipt["host"], receipt["job"]))
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        publish_link(path, encode(receipt))
    except FileExistsError:
        return False
    return True


def focus_project(settings, focus):
    """The project whose focus/<F-id>.md exists, if exactly one does."""
    matches = [p.name for p in (settings.repo_root / "projects").iterdir()
               if p.is_dir() and not p.is_symlink() and (p / "focus" / (focus + ".md")).is_file()]
    return matches[0] if len(matches) == 1 else None


def project_exists(settings, project):
    path = settings.repo_root / "projects" / project
    return path.is_dir() and not path.is_symlink()


# --- collection on the hub ---------------------------------------------------

def launch_roots(settings):
    """{host: root} for every reachable launch host this board may inspect."""
    rows = load_roots(settings.config_dir, settings.host_alias, settings.ssh_hosts, name="rdash-launch.yaml")
    roots = {}
    for host, root in rows:
        host = "" if host == "local" else host
        if root is not None:
            roots.setdefault(host, []).append(root)
    return roots


def _seen_path(settings):
    from .safety import cache_path
    return cache_path(settings, "receipts-seen.json")


def collect(settings):
    """Copy new receipts from each launch host into the repository."""
    try:
        seen = json.loads(_seen_path(settings).read_text())
        if not isinstance(seen, dict):
            seen = {}
    except (OSError, ValueError):
        seen = {}
    summary = dict(hosts={}, stored=[], skipped=[])
    for host, roots in launch_roots(settings).items():
        label = host or settings.host_alias or "local"
        listing = inspection.json_lines(host, "receipts", roots)
        if listing is None:
            summary["hosts"][label] = "unreachable"
            continue
        summary["hosts"][label] = "ok"
        wanted = {}
        for row in listing:
            if (type(row.get("i")) is not int or not 0 <= row["i"] < len(roots)
                    or not isinstance(row.get("dir"), str) or not isinstance(row.get("name"), str)
                    or not inspection.RECEIPT_NAME.match(row["name"]) or type(row.get("size")) is not int):
                continue
            job = int(row["name"][:-5])
            key = "%s:%s/%d:%s" % (label, row["dir"], job, row.get("mtime"))
            if key in seen or row["size"] > MAX_RECEIPT:
                continue
            path = "%s/%s/receipts/%s" % (roots[row["i"]], row["dir"], row["name"])
            wanted[path] = (row["dir"], job, key)
        if not wanted:
            continue
        contents, _ = inspection._channel(host, "content", list(wanted), roots=tuple(roots), timeout=60)
        for (path, (directory, job, key)), row in zip(wanted.items(), contents):
            if row.get("state") != "present":
                continue
            try:
                receipt = validate(json.loads(row["data"]))
                if receipt["host"] != label or receipt["job"] != job:
                    raise ValueError("receipt names %s:%s but was found at %s:%s"
                                     % (receipt["host"], receipt["job"], label, path))
                if directory == "focus":
                    if "focus" not in receipt:
                        raise ValueError("focus receipt without an F-id")
                    receipt["project"] = focus_project(settings, receipt["focus"]) or ""
                    if not receipt["project"]:
                        raise ValueError("no project has focus/%s.md" % receipt["focus"])
                elif receipt.get("project") != directory:
                    raise ValueError("receipt project %r is not its directory %r" % (receipt.get("project"), directory))
                if not project_exists(settings, receipt["project"]):
                    raise ValueError("unknown project " + receipt["project"])
            except (ValueError, KeyError, TypeError, RecursionError) as exc:
                summary["skipped"].append(dict(host=label, path=path, reason=str(exc)[:200]))
                seen[key] = "skipped"
                continue
            receipt["collected_at"] = now()
            try:
                with writer_lock(settings):
                    stored = store(settings, receipt)
            except Error as exc:
                # Busy or unwritable: leave it unseen, so the next run retries.
                summary["skipped"].append(dict(host=label, path=path, reason=exc.payload["message"]))
                continue
            if stored:
                summary["stored"].append("%s/runs/%s-%d.json" % (receipt["project"], label, job))
            seen[key] = "stored"
    from .safety import publish_replace
    path = _seen_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    publish_replace(path, json.dumps(seen).encode())
    return summary


# --- runs no receipt names ---------------------------------------------------

_unrecorded_cache = {}
_unrecorded_lock = threading.Lock()
UNRECORDED_TTL = 120


def known_jobs(settings):
    """(host, job) pairs recorded anywhere: receipts, and card fences (older launches)."""
    known = set()
    for project in sorted(p.name for p in (settings.repo_root / "projects").iterdir()
                          if p.is_dir() and not p.is_symlink() and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", p.name)):
        for receipt in load(settings, project):
            known.add((receipt["host"], receipt["job"]))
        cards = settings.repo_root / "projects" / project / "cards"
        for path in list(cards.glob("*.md")) + list(cards.glob("inbox/*.md")):
            try:
                status = declared_status(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            host = status["host"] or settings.host_alias
            known.update((host, job) for job in status["jobs"])
    return known


def default_since():
    week = (date.today() - timedelta(days=7)).isoformat()
    return max(os.environ.get("RDASH_RECEIPTS_SINCE", CUTOVER), week)


def unrecorded(settings, since=None, refresh=False):
    since = since or default_since()
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", since):
        raise Error(400, "invalid_since", "since must be YYYY-MM-DD")
    with _unrecorded_lock:
        hit = _unrecorded_cache.get(since)
        if hit and not refresh and time.monotonic() - hit[0] < UNRECORDED_TTL:
            return hit[1]
    roots = launch_roots(settings)
    known = known_jobs(settings)
    result = dict(since=since, hosts={}, jobs=[])
    hosts = list(settings.ssh_hosts) + ([""] if "" in roots else [])
    for host in hosts:
        label = host or settings.host_alias or "local"
        rows = inspection.json_lines(host, "recent", [since])
        if rows is None:
            result["hosts"][label] = "unreachable"
            continue
        result["hosts"][label] = "ok"
        groups = {}
        for row in rows:
            if not isinstance(row.get("job"), str) or not isinstance(row.get("state"), str):
                continue
            base = int(row["job"].split("_")[0])
            if (label, base) in known:
                continue
            group = groups.setdefault(base, dict(host=label, job=base, name=row.get("name") or "",
                                                 submit=row.get("submit") or "", workdir=row.get("workdir") or "",
                                                 states={}, tasks=0))
            group["tasks"] += 1
            group["states"][row["state"]] = group["states"].get(row["state"], 0) + 1
        for group in groups.values():
            group["project"] = guess_project(settings, roots.get(host, []), group)
            result["jobs"].append(group)
    result["jobs"].sort(key=lambda g: (g["submit"], g["job"]), reverse=True)
    with _unrecorded_lock:
        _unrecorded_cache[since] = (time.monotonic(), result)
    return result


def guess_project(settings, roots, group):
    """The project a job's working directory sits under, if any; a hint, not a record."""
    workdir = group.get("workdir", "")
    for root in roots:
        if workdir.startswith(root.rstrip("/") + "/"):
            name = workdir[len(root.rstrip("/")) + 1:].split("/")[0]
            if project_exists(settings, name):
                return name
    match = re.search(r"/projects/([A-Za-z0-9][A-Za-z0-9_-]*)(?:/|$)", workdir)
    if match and project_exists(settings, match.group(1)):
        return match.group(1)
    return None


def attach(settings, host, job, project, card=None, note=None, focus=None):
    """Record a job after the fact, on the hub's repository copy."""
    if not isinstance(host, str) or not inspection.ALIAS.fullmatch(host):
        raise Error(400, "invalid_host", "Invalid host")
    if host != settings.host_alias and host not in settings.ssh_hosts:
        raise Error(403, "host_not_permitted", host + " is not in RDASH_SSH_HOSTS")
    project_id(project)
    if not project_exists(settings, project):
        raise Error(404, "unknown_project", "No such project")
    if card is not None:
        card = card[len("cards/"):] if card.startswith("cards/") else card
        card_ref(card)
        if not (settings.repo_root / "projects" / project / "cards" / card).is_file():
            raise Error(404, "unknown_card", "No such card in " + project)
    observed = inspection.probe_jobs("" if host == settings.host_alias else host, [int(job)])[0].get(int(job), {})
    if not observed.get("tasks"):
        raise Error(404, "unknown_job", "%s has no record of job %s" % (host, job))
    task = observed["tasks"].get(str(job)) or next(iter(observed["tasks"].values()))
    receipt = dict(schema=SCHEMA, job=int(job), host=host, via="attach", project=project, card=card,
                   focus=focus, job_name=task.get("name") or None,
                   submitted_at=(task.get("start") or None), submitted_by=submitter(), note=note)
    try:
        receipt = validate(receipt)
    except ValueError as exc:
        raise Error(400, "invalid_receipt", str(exc))
    receipt["collected_at"] = now()
    with writer_lock(settings):
        if not store(settings, receipt):
            raise Error(409, "already_recorded", "%s job %s already has a receipt" % (host, job))
    with _unrecorded_lock:
        _unrecorded_cache.clear()
    return receipt


def runs_view(settings, project, refresh=False):
    """The board's Runs view: this project's receipts and the hosts' unrecorded jobs."""
    project_id(project)
    rows = load(settings, project)
    by_host = {}
    for row in rows:
        by_host.setdefault(row["host"], []).append(row["job"])
    for host, ids in by_host.items():
        mode, _ = inspection.resolve_host(settings, host, True)
        if mode == "none":
            continue
        states = inspection.cached("" if mode == "local" else host, "jobs", list(dict.fromkeys(ids)))
        for row in rows:
            if row["host"] == host:
                row["state"] = states.get(row["job"], {}).get("reduced", "unknown")
    for row in rows:
        row.setdefault("state", "unknown")
    from .safety import cache_path
    try:
        sync = json.loads(cache_path(settings, "sync.json").read_text())
    except (OSError, ValueError, Error):
        sync = None
    return dict(recorded=rows, unrecorded=unrecorded(settings, refresh=refresh), sync=sync)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("collect")
    listing = sub.add_parser("unrecorded")
    listing.add_argument("--project")
    listing.add_argument("--since")
    one = sub.add_parser("attach")
    one.add_argument("--host", required=True)
    one.add_argument("--job", required=True, type=int)
    one.add_argument("--project", required=True)
    one.add_argument("--card")
    one.add_argument("--focus")
    one.add_argument("--note")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
        if args.command == "collect":
            result = collect(settings)
        elif args.command == "unrecorded":
            result = unrecorded(settings, args.since, refresh=True)
            if args.project:
                result["jobs"] = [j for j in result["jobs"] if j["project"] == args.project]
        else:
            result = attach(settings, args.host, args.job, args.project, args.card, args.note, args.focus)
    except Error as exc:
        print(json.dumps(exc.payload), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
