#!/usr/bin/env python3
"""Inspect an explicit probe-contract JSON fence; never launch or authorize work.

Usage: check_readiness.py PROJECT [--task PROJECT_RELATIVE_FILE] [--json]
The selected file defaults to spec.md. References are project-relative paths,
optionally with an ATX Markdown heading anchor. External references are not read.
Exit 1 means missing/inconsistent structure; exit 0 may still contain unknowns.
Neither exit code establishes scientific validity or permission to execute.
"""

import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


MAX_BYTES = 1_048_576
KINDS = {"engineering", "science", "exploration"}
REFS = ("objective", "acceptance", "evidence", "authority", "method")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*?)\s*$")
LITERAL_HTML = re.compile(r"^ {0,3}<(pre|script|style|textarea)(?:\s|>|$)", re.I)
PLACEHOLDER = re.compile(r"<[^>]+>|\{[^}]+\}|\$[A-Za-z_]|^(?:TODO|TBD|FILL|UNKNOWN)$", re.I)
LIMIT = "Structure only: no execution, scientific validation, or authorization is established."


def read_text(path):
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("File exceeds the 1 MiB inspection limit.")
    return data.decode("utf-8")


def inside(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def visible_lines(text):
    """Hide comments/literal HTML; preserve code spans, fenced JSON, and line numbers."""
    fence, comment, literal_html = None, False, None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw
        if fence is None:
            html_start = LITERAL_HTML.match(line) if not comment else None
            if literal_html or html_start:
                literal_html = literal_html or html_start[1].lower()
                if re.search(rf"</{literal_html}\s*>", line, re.I):
                    literal_html = None
                yield number, ""
                continue
            visible = ""
            while line:
                if comment:
                    _, end, line = line.partition("-->")
                    if not end:
                        break
                    comment = False
                else:
                    token = re.search(r"`+|<!--", line)
                    if token is None:
                        visible += line
                        break
                    visible += line[:token.start()]
                    marker = token[0]
                    line = line[token.end():]
                    if marker == "<!--":
                        comment = True
                    else:
                        # A matched code span makes comment markers literal.
                        # Unmatched backticks remain ordinary Markdown text.
                        close = next((m for m in re.finditer(r"`+", line)
                                      if m[0] == marker), None)
                        if close:
                            visible += marker + line[:close.end()]
                            line = line[close.end():]
                        else:
                            visible += marker
            line = visible
        match = FENCE.match(line)
        if match:
            if fence is None:
                fence = match[1]
            elif match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
        yield number, line


def contract_blocks(text):
    """Find top-level fences, ignoring examples inside other fenced blocks."""
    blocks, current = [], None
    for number, line in visible_lines(text):
        match = FENCE.match(line)
        if current is None:
            if match:
                marker, info = match.groups()
                current = [marker, info.strip() == "probe-contract", number, []]
        elif match and match[1][0] == current[0][0] and len(match[1]) >= len(current[0]) and not match[2].strip():
            if current[1]:
                blocks.append((current[2], "\n".join(current[3]), True))
            current = None
        else:
            current[3].append(line)
    if current and current[1]:
        blocks.append((current[2], "\n".join(current[3]), False))
    return blocks


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key; remove the ambiguity.")
        result[key] = value
    return result


def markdown_anchors(text):
    anchors, counts, fence = set(), {}, None
    for _, line in visible_lines(text):
        match = FENCE.match(line)
        if match:
            if fence is None:
                fence = match[1]
            elif match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
            continue
        if fence:
            continue
        heading = re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if heading:
            label = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", heading[1]).lower()
            slug = "".join(c for c in label if c.isalnum() or c in " _-").replace(" ", "-")
            count = counts.get(slug, 0)
            counts[slug] = count + 1
            anchors.add(f"{slug}-{count}" if count else slug)
    return anchors


def inspect(project, task="spec.md"):
    findings = []

    def add(status, field, location, detail, next_action=None):
        findings.append(dict(status=status, field=field, location=location,
                             detail=detail, next_action=next_action))

    def finish(kind=None):
        unresolved = [f for status in ("inconsistent", "missing", "unknown")
                      for f in findings if f["status"] == status]
        return {"report_version": 1, "kind": kind, "scope": LIMIT,
                "findings": findings, "next_unresolved": unresolved[0] if unresolved else None}

    try:
        root = Path(project).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Project must be a directory.")
        selector = Path(task)
        if selector.is_absolute() or ".." in selector.parts or "\\" in task or "#" in task or "?" in task:
            raise ValueError("--task must be a project-relative filename without traversal or selectors.")
        selected = (root / selector).resolve()
        if not inside(selected, root):
            raise ValueError("Selected task resolves outside the project.")
        source = selector.as_posix()
    except (OSError, RuntimeError, ValueError):
        add("inconsistent", "input", "input", "Invalid project or task path.",
            "Supply an existing project directory and a task filename contained within it.")
        return finish()
    if not selected.is_file():
        add("missing", "task", f"{source}:1", "Selected task file does not exist.", "Select an existing canonical task file.")
        return finish()
    try:
        text = read_text(selected)
    except (OSError, UnicodeError, ValueError):
        add("unknown", "task", f"{source}:1", "Task file cannot be inspected as bounded UTF-8 text.", "Inspect its format and accessibility.")
        return finish()
    blocks = contract_blocks(text)
    if not blocks:
        add("unknown", "contract", f"{source}:1", "No probe-contract block; existing prose/legacy rules were not interpreted or changed.",
            "Review this existing record; add an explicit contract only if useful and authorized.")
        return finish()
    start, body, closed = blocks[0]

    def location(key=None):
        offset = 0
        if key:
            for offset, line in enumerate(body.splitlines()):
                if re.search(r'"' + re.escape(key) + r'"\s*:', line):
                    break
            else:
                offset = 0
        pointer = f"#/references/{key}" if key in REFS else (f"#/{key}" if key else "")
        return f"{source}:{start + 1 + offset}{pointer}"

    if len(blocks) != 1:
        lines = ", ".join(str(b[0]) for b in blocks)
        add("inconsistent", "contract", f"{source}:{start}", f"Multiple contract blocks at lines {lines}.", "Select one canonical contract per task file.")
        return finish()
    if not closed:
        add("inconsistent", "contract", f"{source}:{start}", "Unclosed contract fence.", "Close the contract fence.")
        return finish()
    try:
        contract = json.loads(body, object_pairs_hook=unique_object,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON number.")))
    except (ValueError, RecursionError) as exc:
        line = start + getattr(exc, "lineno", 1)
        add("inconsistent", "contract", f"{source}:{line}", "Contract is not unambiguous standard JSON.", "Fix JSON syntax, duplicate keys, or non-finite values.")
        return finish()
    if not isinstance(contract, dict):
        add("inconsistent", "contract", location(), "Contract must be a JSON object.", "Use the documented schema.")
        return finish()
    if type(contract.get("schema_version")) is not int or contract["schema_version"] != 1:
        add("inconsistent", "schema_version", location("schema_version"), "Only schema_version 1 is supported.", "Check the explicit contract schema; do not migrate scientific state.")
        return finish()
    if set(contract) - {"schema_version", "kind", "references"}:
        add("inconsistent", "contract", location(), "Unrecognized contract fields.", "Use only schema_version, kind, and references.")
    kind = contract.get("kind")
    if not isinstance(kind, str) or kind not in KINDS:
        add("inconsistent", "kind", location("kind"), "Kind must be engineering, science, or exploration.", "State the actual task kind.")
        return finish()
    add("present", "contract", location(), f"Explicit schema 1 {kind} contract found.")
    refs = contract.get("references")
    if not isinstance(refs, dict):
        add("inconsistent", "references", location("references"), "references must be a JSON object.", "Supply references to existing canonical records.")
        return finish(kind)
    if set(refs) - set(REFS):
        add("inconsistent", "references", location("references"), "Unrecognized reference fields.", "Use objective, acceptance, evidence, authority, and optional method.")

    for key in REFS:
        if key == "method" and key not in refs and kind != "science":
            continue
        value = refs.get(key)
        loc = location(key)
        if value is None or (isinstance(value, str) and (not value.strip() or PLACEHOLDER.search(value))):
            add("missing", key, loc, "Reference is absent or contains an unresolved placeholder.", f"Identify the canonical {key} reference, or retain the uncertainty explicitly.")
            continue
        if not isinstance(value, str):
            add("inconsistent", key, loc, "Reference must be a string or null.", "Use a locator, not copied content.")
            continue
        if value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value) or "\\" in value:
            add("inconsistent", key, loc, "Ambiguous reference spelling or control characters.", "Use a plain project-relative path or explicit external URI.")
            continue
        try:
            parsed = urlsplit(value)
        except ValueError:
            add("inconsistent", key, loc, "Malformed reference URI.", "Correct the locator without including credentials.")
            continue
        if parsed.scheme or parsed.netloc:
            if parsed.username is not None or parsed.password is not None:
                add("inconsistent", key, loc, "Credential-bearing URI is not accepted or inspected.", "Use a permitted credential-free reference.")
            else:
                add("unknown", key, loc, "External reference was not dereferenced.", "Verify it in its owning authorized environment.")
            continue
        if value.startswith(("/", "~")):
            add("unknown", key, loc, "External filesystem reference was not inspected.", "Verify it in its owning authorized environment.")
            continue
        path_text, separator, anchor = value.partition("#")
        if ".." in Path(path_text).parts or "%" in path_text or "?" in path_text or (separator and (not anchor or "#" in anchor)):
            add("inconsistent", key, loc, "Traversal, encoded path, query, or ambiguous fragment is unsupported.", "Use an unambiguous project-relative path and optional heading anchor.")
            continue
        target = selected if not path_text else root / path_text
        try:
            target = target.resolve()
            if not inside(target, root):
                add("unknown", key, loc, "Reference resolves outside the project; it was not read.", "Verify the target in its owning environment.")
            elif not target.exists():
                add("missing", key, loc, "Referenced local path does not exist.", "Correct the reference or provide the missing artifact within the task authority.")
            elif not target.is_file() and not target.is_dir():
                add("unknown", key, loc, "Special filesystem object was not read.", "Use a regular record file or directory reference.")
            elif separator and target.suffix.lower() != ".md":
                add("unknown", key, loc, "Local path exists; fragments are checked only for Markdown ATX headings.", "Verify the fragment with its owning format's tools.")
            elif separator and anchor not in markdown_anchors(read_text(target)):
                add("missing", key, loc, "Referenced Markdown heading anchor was not found.", "Correct the drifted reference or inspect unsupported heading syntax.")
            else:
                detail = "Reference present; its meaning and contents are not certified."
                if key == "method":
                    detail += " Existing method adoption/revision is not interpreted or upgraded."
                add("present", key, loc, detail)
        except (OSError, RuntimeError, UnicodeError, ValueError):
            add("unknown", key, loc, "Local reference could not be inspected within the read limit.", "Check accessibility, format, or symlink resolution.")
    add("unknown", "authority_verification", location("authority"), "A referenced record does not establish current execution authority.", "Apply the user's existing task authorization; do not request it again if already granted.")
    add("unknown", "evidence_verification", location("evidence"), "Reference existence does not establish engineering correctness or scientific validity.", "Use the applicable project checks and evidence review.")
    return finish(kind)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="Project-memory directory")
    parser.add_argument("--task", default="spec.md", help="Existing project-relative canonical file (default: spec.md)")
    parser.add_argument("--json", action="store_true", help="Emit a JSON report")
    args = parser.parse_args(argv)
    report = inspect(args.project, args.task)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(report["scope"])
        for finding in report["findings"]:
            print(f"{finding['status'].upper():12} {finding['location']} [{finding['field']}] {finding['detail']}")
        next_item = report["next_unresolved"]
        if next_item:
            print(f"Next: {next_item['next_action']} ({next_item['location']})")
    return int(any(f["status"] in {"missing", "inconsistent"} for f in report["findings"]))


if __name__ == "__main__":
    sys.exit(main())
