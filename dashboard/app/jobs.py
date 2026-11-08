"""Parse declarations only; all live inspection is in inspection.py."""
import json
import re
from . import inspection

FENCE = re.compile(r"^```probe-status\s*$(.*?)^```\s*$", re.MULTILINE | re.DOTALL)
MAX_JOBS = 64          # a card declaring more than this is misusing the fence


def declared_status(text):
    result = dict(host=None, host_ok=True, jobs=[], artifacts=[])
    match = FENCE.search(text or "")
    if not match:
        return result
    try:
        fence = json.loads(match.group(1))
    except (ValueError, RecursionError):
        return result
    if not isinstance(fence, dict):
        return result
    host = fence.get("host")
    result["host"] = host
    result["host_ok"] = ("host" not in fence or
                         isinstance(host, str) and bool(inspection.ALIAS.fullmatch(host)))
    values = fence.get("jobs")
    for value in values if isinstance(values, list) else []:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            continue
        value = str(value).strip()
        if not re.fullmatch(r"[0-9]{1,12}", value):
            continue
        number = int(value)
        if number > 0 and number not in result["jobs"]:
            result["jobs"].append(number)
        if len(result["jobs"]) == MAX_JOBS:
            break
    artifacts = fence.get("artifacts")
    for label, path in artifacts.items() if isinstance(artifacts, dict) else []:
        if (not isinstance(label, str) or not 1 <= len(label) <= 120 or
                not isinstance(path, str) or not 1 <= len(path) <= 512 or
                not path.startswith("/") or not re.fullmatch(r"[\x20-\x7e]+", path)):
            continue
        result["artifacts"].append(dict(label=label, path=path))
        if len(result["artifacts"]) == 64:
            break
    return result


def declared_steps(text):
    """Job IDs per pipeline step from the fence's `steps` map ({} if none)."""
    match = FENCE.search(text or "")
    try:
        fence = json.loads(match.group(1)) if match else None
    except (ValueError, RecursionError):
        fence = None
    steps = fence.get("steps") if isinstance(fence, dict) else None
    result = {}
    for key, entry in steps.items() if isinstance(steps, dict) else []:
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", key) or not isinstance(entry, dict):
            continue
        values = entry.get("jobs")
        result[key] = [int(v) for v in (values if isinstance(values, list) else [])
                       if not isinstance(v, bool) and isinstance(v, int) and 0 < v < 10**12][:MAX_JOBS]
    return result


MAX_SESSIONS = 16
FIELDS = dict(provider=32, id=128, host=64, cwd=512)


def declared_sessions(text):
    """Read the attach declaration only. A declared session is not a live one.

    The card says which session is tackling this card; nothing here observes
    whether that process still exists. `process_state` is therefore absent, not
    "running" -- the derivation in attention.py reads the difference.
    """
    result = dict(declared=False, items=[])
    match = FENCE.search(text or "")
    if not match:
        return result
    try:
        fence = json.loads(match.group(1))
    except (ValueError, RecursionError):
        return result
    values = fence.get("sessions") if isinstance(fence, dict) else None
    for value in values if isinstance(values, list) else []:
        if not isinstance(value, dict):
            continue
        label = value.get("label")
        if not isinstance(label, str) or not 1 <= len(label) <= 120 or not re.fullmatch(r"[^\x00-\x1f]+", label):
            continue
        session = dict(label=label)
        for field, limit in FIELDS.items():
            text_value = value.get(field)
            if isinstance(text_value, str) and 1 <= len(text_value) <= limit and re.fullmatch(r"[\x20-\x7e]+", text_value):
                session[field] = text_value
        if session.get("host") and not inspection.ALIAS.fullmatch(session["host"]):
            del session["host"]
        result["items"].append(session)
        if len(result["items"]) == MAX_SESSIONS:
            break
    result["declared"] = bool(result["items"])
    return result


def declared_jobs(text):
    return declared_status(text)["jobs"]
