"""Read goal projections and append revision-bound operator commands."""
import sqlite3
from . import safety
from .projects import get_project
from dashboard.supervisor import goals as records
from dashboard.supervisor.store import Store


def read(settings, project, goal):
    get_project(settings, project)
    path = safety.resolve_within(records.directory(settings, project, goal), "state.json")
    try:
        value, _ = records.read_json(path)
    except FileNotFoundError:
        raise safety.Error(404, "unknown_goal", "No published goal state")
    if value.get("project") != project or value.get("id") != goal:
        raise safety.Error(422, "invalid_goal_projection", "Goal identity does not match its directory")
    return value


def card_index(settings, project):
    """Read each projection once; retain failures using the authored card binding."""
    root = safety.resolve_within(settings.repo_root, "projects", project, "goals")
    index = {}
    for path in sorted(root.glob("*/state.json")):
        try:
            value = read(settings, project, path.parent.name)
            if not isinstance(value.get("card"), str):
                raise ValueError("Missing card binding")
        except (safety.Error, OSError, ValueError) as exc:
            card = None
            try:
                authored, _ = records.read_json(safety.resolve_within(
                    records.directory(settings, project, path.parent.name), "goal.json"))
                if authored.get("project") == project and authored.get("id") == path.parent.name:
                    card = authored.get("card")
            except (safety.Error, OSError, ValueError):
                pass
            value = dict(id=path.parent.name, project=project,
                         card=card if isinstance(card, str) else None, phase="unknown",
                         waiting_reason="invalid_goal_projection", projection_error=str(exc))
        index.setdefault(value.get("card"), []).append(value)
    return index


def for_card(settings, project, card, index=None):
    index = card_index(settings, project) if index is None else index
    # A broken authored binding cannot safely identify one card: warn on all.
    matches = index.get(card, []) + index.get(None, [])
    if len(matches) > 1:
        return dict(project=project, card=card, phase="decision_required",
                    waiting_reason="multiple_goals_for_card", goal_ids=[goal["id"] for goal in matches],
                    goals=matches)
    return matches[0] if matches else None


def augment_sessions(sessions, goal):
    if goal is None:
        return sessions
    items = list(sessions.get("items", []))
    for dispatch in goal.get("dispatches", []):
        if dispatch["state"] in ("submitting", "submitted"):
            items.append(dict(source="goal", label=dispatch["assignment"], process_state="running",
                              request_id=dispatch["request_id"], job_id=dispatch.get("job_id")))
    if goal.get("coordinator_in_flight"):
        items.append(dict(source="goal", label="Goal coordinator", process_state="running"))
    return dict(sessions, declared=bool(items), items=items,
                running=any(item.get("process_state") == "running" for item in items) or sessions.get("running", False))


def command(settings, data):
    project, goal = data.get("project"), data.get("goal")
    read(settings, project, goal)
    if not settings.supervisor_db.is_file():
        raise safety.Error(503, "runtime_store_lost", "Runtime store is unavailable")
    store = Store(settings.supervisor_db)
    payload = data.get("payload", {})
    if not isinstance(payload, dict):
        raise safety.Error(400, "invalid_command", "Command payload must be an object")
    try:
        identifier = store.enqueue(records.key(project, goal), data.get("kind"), payload,
                                   "dashboard", data.get("goal_revision"))
    except sqlite3.DatabaseError:
        raise safety.Error(503, "runtime_store_lost", "Runtime store is unreadable")
    return dict(id=identifier, state="pending")
