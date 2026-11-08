"""Batch cards for agents: create from the project's pipeline, report, tick.

A project that runs a settled pipeline on each incoming volume declares it once in
spec.md under `## PIPELINE` as an `rdash-pipeline` JSON fence:

    {"batch": {"required": ["name", "input"], "optional": ["fold_z"]},
     "steps": [{"name": "info", "script": "scripts/pipeline/info.sbatch", "needs": [],
                "check": "what must be true before ticking"}, ...]}

`script` is null for a step done by hand (e.g. feedback to collaborators). Every
command prints one JSON object, so a Claude Code or Codex session can act on it:

    dashboard/app/hub.sh batch new    P --name brain3 --date 2026-10-07 --set input=/x.czi ...
    dashboard/app/hub.sh batch status P cards/batch-....md
    dashboard/app/hub.sh batch tick   P cards/batch-....md --step S --result "..." [--skip]

(hub.sh runs `python3 -B -m dashboard.app.batch <cmd> --project P [--card C] ...` on the
hub and keeps its exit status; errors are one JSON object on stderr.)

`status` names the next runnable step and the exact launch command. `tick` refuses a
step whose prerequisites are unticked, and a scripted step whose latest job has not
COMPLETED (job completion is still not the check: the agent runs the step's check
first and writes what it found as the result).
"""
import argparse
import json
import re
import sys

from . import inspection, receipts
from .cards import STEP_KEY, _set_line, _today, parse, read_card, steps
from .config import Settings
from .jobs import FENCE
from .launch import BATCH_KEY, BATCH_VALUE, SCRIPT
from .projects import get_project
from .safety import Error, agent_lock_state, backup, publish_link, publish_replace, resolve_within, writer_lock

PIPELINE = re.compile(r"^```rdash-pipeline\s*$(.*?)^```\s*$", re.MULTILINE | re.DOTALL)
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,47}")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def pipeline(settings, project):
    get_project(settings, project)
    spec = resolve_within(settings.repo_root, "projects", project, "spec.md")
    match = PIPELINE.search(spec.read_text(encoding="utf-8") if spec.is_file() else "")
    if not match:
        raise Error(422, "no_pipeline", "spec.md has no rdash-pipeline fence under ## PIPELINE")
    try:
        data = json.loads(match.group(1))
    except ValueError:
        raise Error(422, "invalid_pipeline", "rdash-pipeline fence is not JSON")
    keys = data.get("batch", {}) if isinstance(data, dict) else None
    rows = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(keys, dict) or not isinstance(rows, list) or not rows:
        raise Error(422, "invalid_pipeline", "rdash-pipeline needs `batch` and a non-empty `steps` list")
    required, optional = keys.get("required", []), keys.get("optional", [])
    if not all(isinstance(k, str) and BATCH_KEY.fullmatch(k) for k in required + optional) or "name" not in required:
        raise Error(422, "invalid_pipeline", "batch keys must be plain names and include `name`")
    seen = []
    for row in rows:
        name, script, needs = (row.get("name"), row.get("script"), row.get("needs", [])) if isinstance(row, dict) else (None,) * 3
        if (not isinstance(name, str) or not STEP_KEY.fullmatch(name) or name in seen
                or (script is not None and (not isinstance(script, str) or not SCRIPT.fullmatch(script)))
                or not isinstance(needs, list) or not all(n in seen for n in needs)):
            raise Error(422, "invalid_pipeline", "Bad step %r (unique name, scripts/ path or null, needs earlier steps)" % (name,))
        seen.append(name)
    return dict(required=required, optional=optional, steps=rows)


def _fence(text):
    match = FENCE.search(text)
    if not match:
        raise Error(422, "missing_fence", "Batch card has no probe-status fence")
    return match, json.loads(match.group(1))


def _id_prefix(settings, project):
    root = resolve_within(settings.repo_root, "projects", project, "cards")
    for path in sorted(root.glob("*.md")) if root.is_dir() else []:
        found = re.search(r"^id: +([A-Z0-9]+)-[A-Z]+-\d+", path.read_text(errors="replace"), re.MULTILINE)
        if found:
            return found.group(1)
    return re.sub(r"[^A-Z0-9]", "", project.upper())[-8:] or "BATCH"


def create(settings, project, name, date, values, host="cajal"):
    plan = pipeline(settings, project)
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise Error(400, "invalid_name", "Batch name must match " + NAME.pattern)
    if not isinstance(date, str) or not DATE.fullmatch(date):
        raise Error(400, "invalid_date", "Date must be YYYY-MM-DD")
    batch = dict(values, name=name)
    allowed = set(plan["required"] + plan["optional"])
    missing = [k for k in plan["required"] if k not in batch]
    unknown = [k for k in batch if k not in allowed]
    bad = [k for k, v in batch.items() if not isinstance(v, str) or not BATCH_VALUE.fullmatch(v)]
    if missing or unknown or bad:
        raise Error(400, "invalid_batch", "missing %s, unknown %s, unsafe values %s" % (missing, unknown, bad))
    with writer_lock(settings):
        root = resolve_within(settings.repo_root, "projects", project)
        agent_lock_state(root)
        cards = resolve_within(root, "cards")
        cards.mkdir(exist_ok=True)
        existing = [read_card(settings, project, p.name) for p in sorted(cards.glob("batch-*.md"))]
        if any((r.get("metadata") or {}).get("title", "").split(" ")[0] == name for r in existing):
            raise Error(409, "batch_exists", "A batch card for %s already exists" % name)
        prefix = _id_prefix(settings, project)
        numbers = [int(m.group(1)) for r in existing
                   for m in [re.search(r"-BATCH-(\d+)$", (r.get("metadata") or {}).get("id", ""))] if m]
        identifier = "%s-BATCH-%03d" % (prefix, max(numbers, default=0) + 1)
        fence = {"schema_version": 1, "host": host, "batch": batch,
                 "steps": {s["name"]: dict({"script": s["script"]} if s.get("script") else {},
                                           needs=s.get("needs", []), jobs=[]) for s in plan["steps"]},
                 "jobs": []}
        lines = ["---", "id: " + identifier, "title: " + name, "project: " + project,
                 "task: batch", "batch: " + name, "stage: jobs", "batch_date: " + date, "created: " + _today(),
                 "updated: " + _today(), "---", "", "# " + name, "", "## Summary", "",
                 "TODO (agent): two or three lines for collaborators once steps land: what arrived, "
                 "what is new, problems, glance links.", "", "## Steps", ""]
        lines += ["- [ ] **%s** — %s" % (s["name"], s.get("check", "")) for s in plan["steps"]]
        lines += ["", "## Status", "", "```probe-status", json.dumps(fence, indent=2), "```", ""]
        path = resolve_within(cards, "batch-%s_%s.md" % (date, name))
        try:
            publish_link(path, "\n".join(lines).encode("utf-8"))
        except FileExistsError:
            raise Error(409, "batch_exists", path.name + " already exists")
    return status(settings, project, path.name)


def _observe(settings, project, record):
    receipts.annotate([record], settings, project)
    inspection.annotate_status([record], settings, project)
    return {job["id"]: job.get("state", "unknown") for job in record.get("jobs", [])}


def status(settings, project, ref):
    record = read_card(settings, project, ref)
    if record["read_only"] or record["metadata"].get("task") != "batch":
        raise Error(422, "not_a_batch", "Card is not a readable batch card (task: batch)")
    _, fence = _fence(record["body"])
    declared = fence.get("steps") if isinstance(fence.get("steps"), dict) else {}
    states = _observe(settings, project, record)
    ticked = {s["key"]: s for s in record["steps"] if s["key"]}
    rows, next_step = [], None
    for key, item in ticked.items():
        entry = declared.get(key, {}) if isinstance(declared.get(key), dict) else {}
        jobs = [dict(id=j, state=states.get(j, "unknown")) for j in record["step_jobs"].get(key, [])]
        needs = entry.get("needs", [])
        blocked = [n for n in needs if not (ticked.get(n) or {}).get("checked")]
        last = jobs[-1]["state"].upper() if jobs else None
        if item["checked"]:
            state = "done"
        elif last in ("RUNNING", "PENDING", "COMPLETING", "CONFIGURING", "REQUEUED", "SUSPENDED"):
            state = "running"
        elif blocked:
            state = "blocked"
        elif last == "COMPLETED":
            state = "check"          # job finished: run the step's check, then tick
        elif last:
            state = "failed"
        else:
            state = "ready"
        row = dict(step=key, state=state, text=item["text"], script=entry.get("script"), needs=needs,
                   blocked_by=blocked, jobs=jobs)
        card = "cards/" + ref
        if state in ("ready", "failed") and entry.get("script"):
            row["launch"] = "dashboard/app/hub.sh launch %s %s --step %s" % (project, card, key)
        if state == "check" or (state == "ready" and not entry.get("script")):
            row["tick"] = ("dashboard/app/hub.sh batch tick %s %s --step %s --result '<what the check found>'"
                           % (project, card, key))
        rows.append(row)
        if next_step is None and state not in ("done", "blocked"):
            next_step = key
    return dict(card="cards/" + ref, id=record["metadata"].get("id"), batch=fence.get("batch", {}),
                summary=record.get("summary", ""), next=next_step, steps=rows,
                complete=bool(rows) and all(r["state"] == "done" for r in rows))


def tick(settings, project, ref, step, result, skip=False):
    if not isinstance(step, str) or not STEP_KEY.fullmatch(step):
        raise Error(400, "invalid_step", "Invalid step")
    if not isinstance(result, str) or not result.strip() or "\n" in result or len(result) > 600:
        raise Error(400, "invalid_result", "Result must be one line of at most 600 characters")
    report = status(settings, project, ref)
    row = next((r for r in report["steps"] if r["step"] == step), None)
    if row is None:
        raise Error(404, "unknown_step", "Card has no step " + step)
    if row["state"] == "done":
        raise Error(409, "already_ticked", step + " is already ticked")
    if row["blocked_by"]:
        raise Error(409, "needs_unmet", "Tick %s first" % ", ".join(row["blocked_by"]))
    if not skip and row["script"] and row["state"] != "check":
        raise Error(409, "job_not_completed", "%s: latest job is %s; launch it and let it complete first"
                    % (step, row["jobs"][-1]["state"] if row["jobs"] else "missing"))
    text = ("skipped — " if skip else "") + result.strip()
    with writer_lock(settings):
        path = resolve_within(settings.repo_root, "projects", project, "cards", ref)
        agent_lock_state(path.parents[1])
        data = path.read_bytes()
        _, lines, positions, quotes, _ = parse(data, project)
        pattern = re.compile(r"^- \[ \] \*\*%s\*\*" % re.escape(step))
        hits = [i for i, line in enumerate(lines) if pattern.match(line)]
        if len(hits) != 1:
            raise Error(422, "ambiguous_step", "Expected one unticked `- [ ] **%s**` line" % step)
        end = hits[0] + 1
        while end < len(lines) and lines[end][:1] in (" ", "\t") and lines[end].strip():
            end += 1        # drop the template's continuation lines with the old text
        lines[hits[0]:end] = ["- [x] **%s** — %s\n" % (step, text)]
        _set_line(lines, positions, quotes, "updated", _today())
        backup(settings, project, path)
        publish_replace(path, "".join(lines).encode("utf-8"))
    return status(settings, project, ref)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("new", "status", "tick"):
        p = sub.add_parser(command)
        p.add_argument("--project", required=True)
        if command == "new":
            p.add_argument("--name", required=True)
            p.add_argument("--date", required=True, help="when the data arrived, YYYY-MM-DD")
            p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
            p.add_argument("--host", default="cajal")
        else:
            p.add_argument("--card", required=True)
        if command == "tick":
            p.add_argument("--step", required=True)
            p.add_argument("--result", required=True)
            p.add_argument("--skip", action="store_true")
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    try:
        if args.command == "new":
            values = {}
            for item in args.set:
                key, sep, value = item.partition("=")
                if not sep or key in values:
                    raise Error(400, "invalid_set", "--set takes KEY=VALUE once per key")
                values[key] = value
            result = create(settings, args.project, args.name, args.date, values, args.host)
        else:
            ref = args.card[len("cards/"):] if args.card.startswith("cards/") else args.card
            result = (status(settings, args.project, ref) if args.command == "status" else
                      tick(settings, args.project, ref, args.step, args.result, args.skip))
    except Error as exc:
        print(json.dumps(exc.payload), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
