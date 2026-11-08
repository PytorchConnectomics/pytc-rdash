"""Questions a project is working on, read from projects/<p>/questions/*.md.

One file per question (template: that directory's README.md). Frontmatter gives
id, title, task, status and, optionally, the milestone it blocks; the body
records the trigger, the cards and the conclusion. Cards point back with
``question: Q-NNN``, the file name's first ``_``-separated part. Read-only: the
board never writes a question file.
"""
import re

from .projects import get_project
from .safety import resolve_within

STATUSES = ("open", "answered", "parked")
KEY = re.compile(r"[a-z][a-z0-9_]*")
MAX_BYTES = 65536


def _frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    meta = {}
    for index, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return meta, "\n".join(lines[index + 1:])
        key, sep, value = line.partition(": ")
        if sep and KEY.fullmatch(key):
            meta[key] = value.strip()[:200]
    return None, text


def _section(body, heading):
    match = re.search(r"^## " + heading + r"[ \t]*\n(.*?)(?=^## |\Z)", body, re.M | re.S)
    return match.group(1).strip() if match else ""


def read(settings, project):
    get_project(settings, project)
    root = resolve_within(settings.repo_root, "projects", project, "questions")
    result = dict(questions=[], errors=[])
    if not root.is_dir():
        return result
    for path in sorted(root.glob("*.md")):
        if path.name == "README.md" or path.is_symlink():
            continue
        resolve_within(root, path.name)
        text = path.read_bytes()[:MAX_BYTES].decode("utf-8", errors="replace")
        meta, body = _frontmatter(text)
        if meta is None or not meta.get("title"):
            result["errors"].append("questions/" + path.name + " needs frontmatter with a title")
            continue
        status = meta.get("status", "open")
        if status not in STATUSES:
            result["errors"].append("questions/" + path.name + " has unknown status " + repr(status))
            status = "open"
        result["questions"].append(dict(
            key=path.stem.split("_")[0], file="questions/" + path.name, id=meta.get("id", ""),
            title=meta["title"], task=meta.get("task", ""), status=status,
            milestone=meta.get("milestone", ""), updated=meta.get("updated", ""),
            **{key: meta.get(key, "") for key in ("rung", "eval_data", "metric", "train_data", "owner")},
            question=_section(body, "Question")[:600], conclusion=_section(body, "Conclusion")[:1200],
            body=body))
    return result
