"""Bounded previews and human feedback on card-declared evidence snapshots."""
import hashlib
import json
from pathlib import PurePosixPath
import re
import struct
import time
import uuid
from urllib.parse import urlencode
import zlib

from . import cards, inspection, jobs
from .config import roots_for
from .safety import Error


TEXT_TYPES = {".txt", ".log", ".md", ".json", ".csv", ".tsv"}
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
MAX_PIXELS = 32 * 1024 * 1024


def _invalid_constant(value):
    raise ValueError(value)


def _revision(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise Error(400, "invalid_" + field, "A SHA-256 " + field + " is required")


def _dimensions(width, height):
    if not (0 < width <= 16384 and 0 < height <= 16384 and width * height <= MAX_PIXELS):
        raise Error(422, "image_dimensions", "Image exceeds preview dimensions")


def _image(data, suffix):
    """Check format framing and dimensions; browsers perform image decoding."""
    try:
        if suffix == ".png":
            if data[:8] != b"\x89PNG\r\n\x1a\n":
                raise ValueError()
            position, seen_data, seen_header = 8, False, False
            while position + 12 <= len(data):
                length = struct.unpack_from(">I", data, position)[0]
                end = position + length + 12
                if end > len(data):
                    raise ValueError()
                kind = data[position + 4:position + 8]
                body = data[position + 8:end - 4]
                if zlib.crc32(kind + body) != struct.unpack_from(">I", data, end - 4)[0]:
                    raise ValueError()
                if not seen_header:
                    if kind != b"IHDR" or length != 13:
                        raise ValueError()
                    width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", body)
                    _dimensions(width, height)
                    depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
                    if depth not in depths.get(color, ()) or compression or filtering or interlace not in (0, 1):
                        raise ValueError()
                    seen_header = True
                elif kind == b"IHDR":
                    raise ValueError()
                if kind == b"IDAT":
                    seen_data = True
                if kind == b"IEND":
                    if length or not seen_data or end != len(data):
                        raise ValueError()
                    return
                position = end
            raise ValueError()
        if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
            raise ValueError()
        position, seen_frame = 2, False
        while position < len(data) - 2:
            if data[position] != 255:
                raise ValueError()
            while position < len(data) and data[position] == 255:
                position += 1
            marker = data[position]
            position += 1
            length = struct.unpack_from(">H", data, position)[0]
            if length < 2 or position + length > len(data) - 2:
                raise ValueError()
            if marker in (0xC0, 0xC1, 0xC2):
                if length < 8:
                    raise ValueError()
                height, width = struct.unpack_from(">HH", data, position + 3)
                _dimensions(width, height)
                seen_frame = True
            if marker == 0xDA:
                if not seen_frame or length < 6:
                    raise ValueError()
                return
            position += length
        raise ValueError()
    except (ValueError, IndexError, struct.error):
        raise Error(422, "invalid_image", "Artifact is not a supported PNG or JPEG image")


def _read(settings, project, card, revision, label):
    _revision(revision, "revision")
    if not isinstance(label, str) or not 1 <= len(label) <= 120:
        raise Error(400, "invalid_label", "Choose a declared artifact label")
    record = cards.read_card(settings, project, card)
    if record["revision"] != revision:
        raise Error(409, "stale_revision", "Card changed; reload it before inspecting evidence")
    if record["read_only"]:
        raise Error(422, "unsupported_card", "Fix the card before inspecting evidence")
    declared = jobs.declared_status(record["body"])
    artifact = next((row for row in declared["artifacts"] if row["label"] == label), None)
    if artifact is None:
        raise Error(404, "unknown_artifact", "This card does not declare that artifact")
    mode, reason = inspection.resolve_host(settings, declared["host"], declared["host_ok"])
    if mode == "none":
        raise Error(403, reason, "Artifact host is unavailable or not permitted: " + reason)
    host = declared["host"] if mode == "ssh" else ""
    path = artifact["path"]
    if not inspection.path_permitted(settings, path):
        raise Error(403, "path_not_permitted", "Artifact is outside permitted observation paths")
    roots = roots_for(settings, project, host)
    if None in roots:
        raise Error(503, "root_unavailable", "Artifact roots are unavailable; retry when the host is reachable")
    suffix = PurePosixPath(path).suffix.lower()
    if suffix not in TEXT_TYPES | IMAGE_TYPES.keys():
        raise Error(415, "unsupported_format", "Preview supports PNG, JPEG and UTF-8 txt, log, md, json, csv or tsv files")
    observations, outcome = inspection.read_files(host, [path], roots)
    observed = observations.get(path, {})
    state, reason = observed.get("state"), observed.get("reason", outcome)
    if outcome != "ok" or state != "present":
        status = 404 if state == "absent" else 403 if state == "refused" else 413 if reason == "too_large" else 503
        raise Error(status, "evidence_unavailable", "Cannot preview artifact: " + str(reason if state != "absent" else "file missing"), state=state, reason=reason)
    data = observed.get("data")
    if not isinstance(data, bytes) or len(data) != observed.get("size"):
        raise Error(503, "invalid_observation", "Artifact observation was incomplete")
    if len(data) > inspection.MAX_CONTENT_FILE:
        raise Error(413, "evidence_too_large", "Artifact exceeds the 1 MiB preview limit")
    result = dict(label=label, path=path, host=declared["host"] or settings.host_alias or "local",
                  revision=revision, artifact_revision=hashlib.sha256(data).hexdigest(),
                  size=len(data), observed_at=time.time(), mtime=observed["mtime"])
    if suffix in IMAGE_TYPES:
        _image(data, suffix)
        result.update(kind="image", mime=IMAGE_TYPES[suffix])
    else:
        try:
            text = data.decode("utf-8")
            if any(ord(c) < 32 and c not in "\t\r\n" for c in text):
                raise ValueError()
            if suffix == ".json":
                pending = [(json.loads(text, parse_constant=_invalid_constant), 0)]
                while pending:
                    value, depth = pending.pop()
                    if depth > 32:
                        raise ValueError()
                    if isinstance(value, (dict, list)):
                        pending.extend((child, depth + 1) for child in (value.values() if isinstance(value, dict) else value))
        except (UnicodeError, ValueError, RecursionError):
            raise Error(422, "invalid_text", "Artifact must contain UTF-8 text (and valid JSON for .json files)")
        result.update(kind="text", mime="text/plain", text=text)
    # A slow remote read must not publish a receipt for a card edited meanwhile.
    if cards.read_card(settings, project, card)["revision"] != revision:
        raise Error(409, "stale_revision", "Card changed while reading evidence; reload it")
    return result, data


def preview(settings, project, card, revision, label):
    result, _ = _read(settings, project, card, revision, label)
    if result["kind"] == "image":
        result["content_url"] = "/api/evidence/content?" + urlencode(dict(project=project, card=card,
            revision=revision, label=label, artifact_revision=result["artifact_revision"]))
    return result


def content(settings, project, card, revision, label, artifact_revision):
    _revision(artifact_revision, "artifact_revision")
    result, data = _read(settings, project, card, revision, label)
    if result["artifact_revision"] != artifact_revision:
        raise Error(409, "stale_artifact", "Artifact changed; inspect the new version before continuing")
    if result["kind"] != "image":
        raise Error(415, "unsupported_format", "Binary preview only serves PNG or JPEG images")
    return data, result["mime"]


def feedback(settings, data):
    text = data.get("text")
    if not isinstance(text, str) or len(text) > 1000:
        raise Error(400, "invalid_text", "Feedback must be at most 1000 characters")
    text = cards._note(text, "text")
    expected = data.get("artifact_revision")
    _revision(expected, "artifact_revision")
    project, card, revision, label = (data.get(key) for key in ("project", "card", "revision", "label"))
    observed, _ = _read(settings, project, card, revision, label)
    if observed["artifact_revision"] != expected:
        raise Error(409, "stale_artifact", "Artifact changed; inspect the new version before sending feedback")
    identifier = uuid.uuid4().hex[:12]
    reference = json.dumps({key: observed[key] for key in ("label", "host", "path", "artifact_revision", "revision", "observed_at")}, ensure_ascii=False).replace("`", "\\u0060")
    note = "Evidence feedback " + identifier + " (needs follow-up) — " + text + " — inspected: `" + reference + "`"
    return cards.edit_card(settings, project, card, revision, text=note)
