"""Planned tracks and runs, read from a project's spec.md.

A track is one approach within one task (data, deep-learning, decoding, ...). A run
is one end-to-end path: one track per task, on one cube. Both are declared in
an ``rdash-tracks`` JSON fence under ``## TRACKS`` in spec.md; cards name the
tracks they serve in ``track:`` (comma separated) and, optionally, the cubes
in ``cube:``. A milestone is one approach, higher level than a track: a name,
the output it delivers, the runs that make it up and, optionally, which tasks
of those runs count. Each track belongs to at most one milestone (``milestone``);
questions (questions.py) are filed by task and milestone. An optional top-level
``tasks`` list fixes the board's task columns and their order for the project.
Progress is never stored here: the board derives it from cards.
"""
import json
import re

from .projects import get_project
from .safety import resolve_within

# `rdash-milestones` is the same block for a project with no tracks (tasks + milestones only).
FENCE = re.compile(r"^```rdash-(?:tracks|milestones)[ \t]*\n(.*?)^```[ \t]*$", re.M | re.S)
NAME = re.compile(r"[a-z0-9][a-z0-9.-]{0,47}")
STATUSES = ("planned", "active", "chosen", "dropped")
MILESTONE_STATUSES = ("planned", "current", "done", "dropped")
SHARED = "shared"  # a prerequisite of every track in its task; never part of a run
MAX_BYTES = 262144


def split(value):
    """`a, b` -> ["a", "b"]; frontmatter list values for track and cube."""
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _text(value, field, errors, limit=200):
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        errors.append(field + " must be text of at most " + str(limit) + " characters")
        return ""
    return value


def parse(text):
    """Return {tasks, tracks, runs, errors}; errors never raise, the board shows them."""
    result = dict(declared=False, columns=[], tasks=[], tracks=[], runs=[], milestones=[], errors=[])
    matches = FENCE.findall(text)
    if not matches:
        return result
    result["declared"] = True
    errors = result["errors"]
    if len(matches) > 1:
        errors.append("More than one rdash-tracks block; reading the first")
    try:
        data = json.loads(matches[0])
    except ValueError as exc:
        errors.append("rdash-tracks is not valid JSON: " + str(exc))
        return result
    if not isinstance(data, dict) or not isinstance(data.get("tracks", {}), dict):
        errors.append("rdash-tracks needs an object; tracks, if given, maps task -> track -> fields")
        return result
    columns = data.get("tasks", [])
    if not isinstance(columns, list) or not all(isinstance(c, str) and NAME.fullmatch(c) for c in columns):
        errors.append("tasks must be a list of lowercase task names (the board's columns)")
        columns = []
    result["columns"] = list(dict.fromkeys(columns))
    stage_of = {}
    for task, entries in data.get("tracks", {}).items():
        if not NAME.fullmatch(task) or not isinstance(entries, dict):
            errors.append("Task " + repr(task) + " needs a lowercase name and an object of tracks")
            continue
        result["tasks"].append(task)
        for name, fields in entries.items():
            fields = fields if isinstance(fields, dict) else {}
            if not NAME.fullmatch(name) or name == SHARED:
                errors.append("Track " + repr(name) + " needs a lowercase name other than " + SHARED)
                continue
            if name in stage_of:
                errors.append("Track " + name + " is declared in both " + stage_of[name] + " and " + task)
                continue
            status = fields.get("status", "planned")
            if status not in STATUSES:
                errors.append("Track " + name + " has unknown status " + repr(status))
                status = "planned"
            needs = fields.get("needs", [])
            if not isinstance(needs, list) or not all(isinstance(n, str) for n in needs):
                errors.append("Track " + name + " needs must be a list of track names")
                needs = []
            stage_of[name] = task
            result["tracks"].append(dict(name=name, task=task, status=status, needs=needs,
                                         desc=_text(fields.get("desc"), "Track " + name + " desc", errors),
                                         cube=split(_text(fields.get("cube"), "Track " + name + " cube", errors)),
                                         milestone=_text(fields.get("milestone"), "Track " + name + " milestone", errors, 32)))
    for track in result["tracks"]:
        for need in track["needs"]:
            if need not in stage_of:
                errors.append("Track " + track["name"] + " needs unknown track " + need)
    runs = data.get("runs", [])
    if not isinstance(runs, list):
        errors.append("runs must be a list")
        runs = []
    seen = set()
    for index, run in enumerate(runs):
        if not isinstance(run, dict) or not isinstance(run.get("path"), list):
            errors.append("Run " + str(index + 1) + " needs a path list")
            continue
        name = run.get("name") or " → ".join(str(p) for p in run["path"])
        if (name, run.get("cube")) in seen:
            errors.append("Run " + name + " is listed twice")
        seen.add((name, run.get("cube")))
        path, tasks = {}, []
        for step in run["path"]:
            task = stage_of.get(step) if isinstance(step, str) else None
            if task is None:
                errors.append("Run " + name + " names unknown track " + repr(step))
            elif task in path:
                errors.append("Run " + name + " names two " + task + " tracks")
            else:
                path[task] = step
        # A track may list several inputs (hf18 runs on clahe or u8): for each
        # task its needs cover, the run's track there must be one of them.
        for step in path.values():
            needs = next(t for t in result["tracks"] if t["name"] == step)["needs"]
            for task in dict.fromkeys(stage_of[n] for n in needs if n in stage_of):
                if task in path and path[task] not in needs:
                    errors.append("Run " + name + ": " + step + " does not take " + path[task])
        result["runs"].append(dict(name=name, cube=_text(run.get("cube"), "Run " + name + " cube", errors, 32),
                                   path=path, desc=_text(run.get("desc"), "Run " + name + " desc", errors),
                                   status=run.get("status", "planned") if run.get("status") in STATUSES else "planned"))
    _milestones(data.get("milestones", []), result)
    ids = {m["id"] for m in result["milestones"]}
    for track in result["tracks"]:
        if track["milestone"] and track["milestone"] not in ids:
            errors.append("Track " + track["name"] + " names unknown milestone " + track["milestone"])
    return result


def _milestones(entries, result):
    errors = result["errors"]
    if not isinstance(entries, list):
        errors.append("milestones must be a list")
        return
    names = {run["name"] for run in result["runs"]}
    seen = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not NAME.fullmatch(entry["id"].lower()):
            errors.append("Milestone " + str(index + 1) + " needs an id such as M1")
            continue
        mid = entry["id"]
        if mid in seen:
            errors.append("Milestone " + mid + " is listed twice")
        seen.add(mid)
        status = entry.get("status", "planned")
        if status not in MILESTONE_STATUSES:
            errors.append("Milestone " + mid + " has unknown status " + repr(status))
            status = "planned"
        runs = entry.get("runs", [])
        if not isinstance(runs, list) or not all(isinstance(r, str) for r in runs):
            errors.append("Milestone " + mid + " runs must be a list of run names")
            runs = []
        for run in runs:
            if run not in names:
                errors.append("Milestone " + mid + " names unknown run " + repr(run))
        tasks = entry.get("tasks", [])
        if not isinstance(tasks, list) or not all(t in result["tasks"] for t in tasks):
            errors.append("Milestone " + mid + " tasks must be declared task names")
            tasks = []
        result["milestones"].append(dict(
            id=mid, status=status, runs=[r for r in runs if r in names], tasks=tasks,
            name=_text(entry.get("name"), "Milestone " + mid + " name", errors),
            output=_text(entry.get("output"), "Milestone " + mid + " output", errors),
            check=_text(entry.get("check"), "Milestone " + mid + " check", errors)))


def read(settings, project):
    get_project(settings, project)
    path = resolve_within(settings.repo_root, "projects", project, "spec.md")
    try:
        data = path.read_bytes()[:MAX_BYTES]
    except FileNotFoundError:
        return parse("")
    return parse(data.decode("utf-8", errors="replace"))
