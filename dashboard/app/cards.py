"""Strict card reads and three narrowly scoped mutations."""
import hashlib
import re
import unicodedata
from datetime import datetime, timezone

from .jobs import declared_jobs, declared_steps
from .needs_you import STATES, parse as needs_you_block
from .projects import discover, get_project
from .safety import (Error, agent_lock_state, backup, card_ref, publish_link,
                     publish_replace, resolve_within, writer_lock)


# `jobs` is a parallel LANE, not a lifecycle step: radd-task cards describe a
# unit of work to run and stay there until it lands, while radd-hypo cards walk
# idea -> formulating -> probing -> reviewing. It is first so the queue reads
# left-most on the board. Order here is the order the UI offers.
STAGES = ("jobs", "idea", "formulating", "probing", "reviewing", "parked")
VERDICTS = ("open", "met", "failed", "inconclusive")
# `track` is optional: a project without tracks (tasks + milestones only) omits it.
REQUIRED = {"id", "title", "project", "stage", "created", "updated"}


def parse(data, project):
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Card is not UTF-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError("Missing opening ---")
    metadata, positions, quotes = {}, {}, {}
    for index, line in enumerate(lines[1:], 1):
        raw = line.rstrip("\r\n")
        if raw == "---":
            break
        if not raw or raw[0].isspace() or ": " not in raw:
            raise ValueError("Expected an unindented key: value line")
        key, value = raw.split(": ", 1)
        value = value.strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", key) or key in metadata:
            raise ValueError("Invalid or duplicate key")
        if len(value) > 200 or " #" in value:
            raise ValueError("Long scalar or inline comment")
        quote = value[:1] if value[:1] in ("'", '"') else ""
        if quote:
            if len(value) < 2 or not value.endswith(quote) or quote in value[1:-1] or "\\" in value[1:-1]:
                raise ValueError("Unsupported quoted scalar")
            value = value[1:-1]
        elif (value[:1] and value[0] in "-[{&*|>!?%@`#") or ": " in value:
            raise ValueError("Unsupported plain scalar")
        metadata[key], positions[key], quotes[key] = value, index, quote
    else:
        raise ValueError("Missing closing ---")
    if not REQUIRED <= metadata.keys():
        raise ValueError("Missing required frontmatter key")
    if any(not metadata[key].strip() for key in REQUIRED | ({"track"} & metadata.keys())):
        raise ValueError("Empty required frontmatter scalar")
    if metadata["stage"] not in STAGES:
        raise ValueError("Unknown stage")
    if "verdict" in metadata and metadata["verdict"] not in VERDICTS:
        raise ValueError("Unknown verdict")
    if "state" in metadata and metadata["state"] not in STATES:
        raise ValueError("Unknown state")
    if metadata["project"] != project:
        raise ValueError("Project differs from directory")
    return metadata, lines, positions, quotes, index


def _path(settings, project, ref):
    get_project(settings, project)
    card_ref(ref)
    if ref not in discover(settings, project)[0]:
        raise Error(404, "unknown_card", "Card is not addressable")
    return resolve_within(settings.repo_root, "projects", project, "cards", ref)


def _record(data, project, ref):
    text = data.decode("utf-8", errors="replace")
    record = dict(card=ref, revision=hashlib.sha256(data).hexdigest(),
                  body=text, read_only=False, job_ids=declared_jobs(text))
    try:
        metadata, lines, _, _, end = parse(data, project)
        record.update(metadata=metadata, body="".join(lines[end + 1:]))
    except ValueError as exc:
        record.update(read_only=True, error="unsupported_frontmatter", reason=str(exc), metadata={})
    record["owner"] = record["metadata"].get("owner", "")
    record["acceptance"] = acceptance(record["body"])
    record["verdict"] = record["metadata"].get("verdict")
    record["state"] = record["metadata"].get("state")
    record["needs_you"] = needs_you_block(record["body"]) if record["state"] == "needs-you" else None
    if record["metadata"].get("task") == "batch":
        record["steps"] = steps(record["body"])
        record["step_jobs"] = declared_steps(text)
        record["summary"] = summary(record["body"])
    return record


def read_card(settings, project, ref):
    return _record(_path(settings, project, ref).read_bytes(), project, ref)


def list_cards(settings, project):
    get_project(settings, project)
    return [read_card(settings, project, ref) for ref in discover(settings, project)[0]]


def _today():
    return datetime.now(timezone.utc).date().isoformat()


def _set_line(lines, positions, quotes, key, value):
    old = lines[positions[key]]
    ending = "\r\n" if old.endswith("\r\n") else "\n" if old.endswith("\n") else ""
    quote = quotes[key]
    lines[positions[key]] = key + ": " + quote + value + quote + ending


def _note(value, field):
    """Validate and flatten a human note. Shared by idea capture and append."""
    if (not isinstance(value, str) or len(value) > 2000
            or any(unicodedata.category(c) == "Cc" and c not in "\r\n" for c in value)):
        raise Error(400, "invalid_" + field,
                    field.capitalize() + " must be at most 2000 characters without control characters")
    value = " ".join(value.splitlines()).strip().lstrip("-# ").strip()
    if not value:
        raise Error(400, "invalid_" + field, field.capitalize() + " is empty")
    return value


def _discussion_index(lines, start):
    """Index to insert a new bullet at: after the last line of the last bullet.

    A bullet may wrap onto indented continuation lines; advancing only over
    "- " lines would splice the new entry into the middle of an existing one.
    """
    headings = [i for i in range(start, len(lines)) if lines[i].rstrip("\r\n") == "## Ideas and discussion"]
    if len(headings) != 1:
        raise Error(422, "missing_section" if not headings else "ambiguous_section",
                    "Expected exactly one Ideas and discussion section")
    section_end = next((i for i in range(headings[0] + 1, len(lines))
                        if lines[i].startswith("#")), len(lines))
    insert = headings[0] + 1
    while insert < section_end and not lines[insert].strip():
        insert += 1
    last = None
    for i in range(headings[0] + 1, section_end):
        if lines[i].startswith("- "):
            last = i
        elif last is not None and lines[i].strip() and lines[i][:1].isspace():
            last = i
    return (last + 1) if last is not None else insert


def _bullet(text):
    return "- " + _today() + " — rdash: " + text + "\n"


def edit_card(settings, project, ref, revision, *, stage=None, text=None):
    if not isinstance(revision, str) or not revision:
        raise Error(400, "invalid_revision", "A revision is required")
    if stage is not None and stage not in STAGES:
        raise Error(400, "invalid_stage", "Unknown stage")
    if text is not None:
        text = _note(text, "text")
    with writer_lock(settings):
        path = _path(settings, project, ref)
        agent_lock_state(path.parents[2] if ref.startswith("inbox/") else path.parents[1])
        data = path.read_bytes()
        try:
            _, lines, positions, quotes, end = parse(data, project)
        except ValueError as exc:
            raise Error(422, "unsupported_card", str(exc))
        current = hashlib.sha256(data).hexdigest()
        if revision != current:
            raise Error(409, "stale_revision", "Card changed; reload before saving", revision=current)
        if stage is not None:
            _set_line(lines, positions, quotes, "stage", stage)
        if text is not None:
            insert = _discussion_index(lines, end + 1)
            if insert and not lines[insert - 1].endswith("\n"):
                lines[insert - 1] += "\n"
            lines.insert(insert, _bullet(text))
        _set_line(lines, positions, quotes, "updated", _today())
        backup(settings, project, path)
        publish_replace(path, "".join(lines).encode("utf-8"))
        return read_card(settings, project, ref)


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def create_idea(settings, project, title, track="model", idea=None):
    if not isinstance(title, str) or any(unicodedata.category(c) == "Cc" for c in title):
        raise Error(400, "invalid_title", "Title must be text without control characters")
    title = " ".join(re.sub(r"[^A-Za-z0-9 ._+()/,'-]", " ", title).split())[:120].strip()
    title = re.sub(r"^[^A-Za-z0-9]+", "", title)
    if not title:
        raise Error(400, "invalid_title", "Title needs an ASCII letter or digit")
    if not isinstance(track, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", track):
        raise Error(400, "invalid_track", "Invalid track")
    if idea is not None:
        idea = _note(idea, "idea")
    if settings.require_owner and not settings.owner:
        raise Error(409, "owner_required", "Set RDASH_OWNER to your handle; new cards carry the owner")
    with writer_lock(settings):
        info = get_project(settings, project)
        root = resolve_within(settings.repo_root, "projects", project)
        agent_lock_state(root)
        inbox = resolve_within(root, "cards", "inbox")
        inbox.mkdir(parents=True, exist_ok=True)
        ids = set()
        for ref in discover(settings, project)[0]:
            data = resolve_within(root, "cards", ref).read_text(errors="replace")
            for match in re.finditer(r"^id: +(.*)$", data, re.MULTILINE):
                ids.add(match.group(1).strip().strip("\"'"))
        template = resolve_within(settings.repo_root, "dashboard", "TEMPLATE.md").read_bytes()
        # The template uses placeholder dates/project, so extract its body directly.
        chunks = template.split(b"---", 2)
        if len(chunks) != 3 or chunks[0]:
            raise Error(422, "invalid_template", "Card template has no frontmatter")
        body = chunks[2].decode("utf-8", errors="strict")
        if idea is not None:
            # A new card should open with the human's words, not the template's
            # hint. Substituting in place keeps the template's own blank lines;
            # deleting the placeholder and inserting separately left a double
            # blank above and none before the next heading.
            body_lines = body.splitlines(keepends=True)
            placeholder = next((i for i, l in enumerate(body_lines)
                                if l.startswith("- YYYY-MM-DD ")), None)
            if placeholder is None:
                insert = _discussion_index(body_lines, 0)
                if insert and not body_lines[insert - 1].endswith("\n"):
                    body_lines[insert - 1] += "\n"
                body_lines.insert(insert, _bullet(idea))
            else:
                body_lines[placeholder] = _bullet(idea)
            body = "".join(body_lines)
        slug = _slug(title)[:48].rstrip("-") or "idea"
        if settings.owner:
            prefix = _slug(info["label"]).upper()
            pattern = re.compile(r"^" + re.escape(prefix) + r"-[A-Z0-9]+-" + re.escape(settings.owner) + r"-(\d{3,})$")
            counter = max((int(m.group(1)) for item in ids if (m := pattern.fullmatch(item))), default=0) + 1
            identifier = f"{prefix}-IDEA-{settings.owner}-{counter:03d}"
            base = _today() + "_" + settings.owner + "_"
            slug = slug[:80 - len(base) - 3].rstrip("-") or "idea"
        for number in range(1, 51):
            suffix = "-" + str(number) if number > 1 else ""
            if settings.owner:
                stem = base + slug[:80 - len(base) - len(suffix)] + suffix
            else:
                stem = slug + suffix
                identifier = _slug(info["label"] + "-" + stem).upper()
            path = resolve_within(inbox, stem + ".md")
            if path.exists() or identifier in ids:
                continue
            values = dict(id=identifier, title=title, project=project, track=track,
                          stage="idea", created=_today(), updated=_today())
            if settings.owner:
                values["owner"] = settings.owner
            data = ("---\n" + "".join(key + ": " + value + "\n" for key, value in values.items())
                    + "---").encode() + body.encode("utf-8")
            try:
                publish_link(path, data)
            except FileExistsError:
                continue
            return read_card(settings, project, "inbox/" + path.name)
    raise Error(409, "slug_exhausted", "All 50 idea names or identifiers are taken")


def _checklist(body, heading):
    """Checkbox items under one `## heading`; fenced blocks are skipped."""
    items = []
    inside = False
    fence = None
    current = None
    for line in body.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
            current = None
            continue
        if fence:
            continue
        if re.match(r"^ {0,3}#{1,6}\s", line):
            inside = line.strip().rstrip("#").strip() == heading
            current = None
            continue
        if not inside:
            continue
        match = re.match(r"^- \[( |x|X)\] (.*)$", line)
        if match:
            current = dict(index=len(items), checked=match[1].lower() == "x", text=match[2])
            items.append(current)
        elif current is not None and line.strip() and line[:1].isspace():
            current["text"] += " " + line.strip()
        else:
            current = None
    return items


def acceptance(body):
    """Read authored task items only; no job or artifact input enters this parse."""
    items = _checklist(body, "## Acceptance")
    for item in items:
        text, separator, refs = item["text"].rpartition(" — evidence: ")
        item["references"] = refs.split(", ") if separator else []
        if separator:
            item["text"] = text
    return dict(declared=bool(items), total=len(items),
                settled=sum(item["checked"] for item in items), items=items)


STEP_KEY = re.compile(r"[a-z][a-z0-9-]{0,31}")


def steps(body):
    """A batch card's `## Steps` checklist: `- [x] **key** — what happened`.

    The bold key names the pipeline step (and the probe-status `steps` entry that
    launches it); the rest is the human line. Items without a key are kept with
    key None so nothing the author wrote disappears.
    """
    items = _checklist(body, "## Steps")
    for item in items:
        match = re.match(r"^\*\*([^*]+)\*\*\s*(?:[—:-]\s*)?(.*)$", item["text"])
        key = match[1].strip() if match else None
        item["key"] = key if key and STEP_KEY.fullmatch(key) else None
        if match and item["key"]:
            item["text"] = match[2]
    return items


def summary(body, limit=1200):
    """First paragraph under `## Summary`, for the batch row."""
    lines, inside = [], False
    for line in body.splitlines():
        if re.match(r"^ {0,3}#{1,6}\s", line):
            if inside:
                break
            inside = line.strip().rstrip("#").strip() == "## Summary"
            continue
        if inside:
            if not line.strip() and lines:
                break
            if line.strip():
                lines.append(line.strip())
    return " ".join(lines)[:limit]
