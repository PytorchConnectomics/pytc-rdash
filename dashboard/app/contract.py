"""Read-only adapter to the canonical structure checker; never infer authority."""
import hashlib
import json
import re
from pathlib import Path

from .safety import resolve_within


def load_checker(root):
    try:
        path = Path(root) / "probe/scripts/check_readiness.py"
        namespace = {"__name__": "rdash_readiness", "__file__": str(path)}
        exec(compile(path.read_bytes(), str(path), "exec"), namespace)
        return namespace
    except (OSError, ValueError, SyntaxError, ImportError):
        return None


CHECKER = load_checker(Path(__file__).resolve().parents[2])


def missing_facts(body):
    in_evidence = False
    in_missing = False
    count = 0
    fence = None
    for line in body.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
            continue
        if fence:
            continue
        if re.match(r"^ {0,3}#{1,6}\s", line):
            in_evidence = line.strip().rstrip("#").strip() == "## Evidence"
            in_missing = False
        elif in_evidence and line.strip().startswith("**Missing"):
            in_missing = True
        elif in_missing and re.match(r"^[-*+]\s+", line):
            count += 1
        elif in_missing and line.strip() and not line[:1].isspace():
            in_missing = False
    return count


CONTRACT_FENCE = re.compile(r"^ {0,3}(?:`{3,}|~{3,})probe-contract\s*$(.*?)^ {0,3}(?:`{3,}|~{3,})\s*$",
                            re.MULTILINE | re.DOTALL)
MAX_TASKS = 24


def _anchor(heading):
    """The checker's own slug rule, so a reference that passes it resolves here."""
    label = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", heading).lower()
    return "".join(c for c in label if c.isalnum() or c in " _-").replace(" ", "-")


def _plain(text):
    """Heading text as a reader sees it: link labels, no code ticks or asterisks.

    Underscores survive: `ExPID82_1` is an identifier, and stripping `_` as an
    emphasis marker silently renames it.
    """
    text = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", text)
    return re.sub(r"[`*]", "", text).strip()


def method_reference(body, card):
    """The method reference, but only when it points into this card's own headings.

    A method kept in another file (a protocol revision, a spec section) is not
    read: the board shows the reference instead of restating someone else's steps.
    """
    match = CONTRACT_FENCE.search(body or "")
    if not match:
        return None, None
    try:
        fence = json.loads(match.group(1))
    except (ValueError, RecursionError):
        return None, None
    value = ((fence.get("references") or {}).get("method")
             if isinstance(fence, dict) and isinstance(fence.get("references"), dict) else None)
    if not isinstance(value, str) or not value:
        return None, None
    path, separator, anchor = value.partition("#")
    local = separator and path in ("", "cards/" + card, card)
    return value, (anchor if local else None)


def method_tasks(body, anchor):
    """Numbered subheadings under the method section, in authored order.

    A card writes its procedure as `### 1. ...` steps; unnumbered subsections
    beside them (traps, sizing) are supporting prose, not work, and are left out.
    Ordered list items serve when a card writes no subheadings. Nothing here
    assigns a step a status -- the card does not record one, so neither does the
    board.
    """
    if not anchor:
        return []
    lines = (body or "").splitlines()
    fence = None
    depth = None
    section = []
    for line in lines:
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
            continue
        if fence:
            continue
        heading = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading and depth is None:
            if _anchor(heading[2]) == anchor:
                depth = len(heading[1])
            continue
        if depth is None:
            continue
        if heading and len(heading[1]) <= depth:
            break
        section.append((heading, line))
    numbered = [h for h, _ in section if h and re.match(r"^\s*\d+[.)]\s", h[2])]
    # One depth only: `### 1.` steps are the procedure, a `#### 1.` under one of
    # them is detail inside a step and would read on the board as a sibling of it.
    step_depth = min((len(h[1]) for h in numbered), default=0)
    steps = [_plain(re.sub(r"^\s*\d+[.)]\s*", "", h[2]))
             for h in numbered if len(h[1]) == step_depth]
    if not steps:
        steps = [_plain(m[1]) for m in
                 (re.match(r"^ {0,3}\d+[.)]\s+(.*)$", line) for h, line in section if not h) if m]
    return [step for step in steps if step][:MAX_TASKS]


def report(settings, project, record, checker=CHECKER):
    body = record["body"]
    declared = bool(re.search(r"^ {0,3}(?:`{3,}|~{3,})probe-contract\s*$", body, re.M))
    reference, anchor = method_reference(body, record["card"])
    result = dict(declared=declared, kind=None, structure="unknown", findings=[],
                  unresolved=0, unknown=0, missing_facts=missing_facts(body), scope="",
                  method=reference, tasks=method_tasks(body, anchor))
    if checker is None:
        return dict(result, reason="checker_unavailable")
    result["scope"] = checker["LIMIT"]
    if not declared:
        return result
    try:
        path = resolve_within(settings.repo_root, "projects", project, "cards", record["card"])
        def unchanged():
            return hashlib.sha256(path.read_bytes()).hexdigest() == record["revision"]
        if not unchanged():
            return dict(result, reason="card_changed_during_read")
        checked = checker["inspect"](settings.repo_root / "projects" / project, "cards/" + record["card"])
        if not unchanged():
            return dict(result, reason="card_changed_during_read")
    except (OSError, ValueError, UnicodeError, RuntimeError):
        return dict(result, reason="inspection_failed")
    findings = checked["findings"]
    structural = [f for f in findings if f["field"] not in ("authority_verification", "evidence_verification")]
    structure = ("fail" if any(f["status"] in ("missing", "inconsistent") for f in structural)
                 else "unknown" if any(f["status"] == "unknown" for f in structural) else "pass")
    return dict(result, kind=checked["kind"], structure=structure, scope=checked["scope"],
                findings=findings, unresolved=sum(f["status"] != "present" for f in findings),
                unknown=sum(f["status"] == "unknown" for f in findings))
