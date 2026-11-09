"""The one state signal an agent thread declares, and the block that makes `needs-you` valid.

A notebook or card carries `state:` in its frontmatter: `working` (an agent or the
scheduler owns the next step), `needs-you` (the bell: a person owes a decision),
`paused` (a person parked it; no bell, no work) or `done`. A session may stop in a
waiting state only by writing `needs-you`, and `needs-you` is valid only with a
`## Needs you` section holding one to three numbered options and a
`Recommendation:` line. Anything else is a malformed bell the agent must fix.
"""
import json
import re
import sys
from pathlib import Path

STATES = ("working", "needs-you", "paused", "done")
MAX_OPTIONS = 3
_SECTION = re.compile(r"^## Needs you[ \t]*\n(.*?)(?=^## |\Z)", re.M | re.S)
_OPTION = re.compile(r"^\s*(\d+)[.)]\s+(\S.*)$")
_RECOMMENDATION = re.compile(r"^\s*(?:[-*]\s*)?\**Recommendation\**\s*:\s*(.*\S)\s*$", re.I)


def parse(body):
    """Return the `## Needs you` block as data; `declared` is False when absent."""
    match = _SECTION.search(body)
    if not match:
        return dict(declared=False, options=[], recommendation="", valid=False, problems=["no `## Needs you` section"])
    options, recommendation = [], ""
    for line in match.group(1).splitlines():
        option = _OPTION.match(line)
        if option:
            options.append(option.group(2).strip()[:300])
            continue
        hit = _RECOMMENDATION.match(line)
        if hit:
            recommendation = hit.group(1)[:300]
    problems = []
    if not options:
        problems.append("no numbered options")
    if len(options) > MAX_OPTIONS:
        problems.append("more than %d options" % MAX_OPTIONS)
    if not recommendation:
        problems.append("no `Recommendation:` line")
    return dict(declared=True, options=options, recommendation=recommendation, valid=not problems, problems=problems)


def frontmatter_state(text):
    """`state:` from a lenient frontmatter read; None when absent or unknown."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            return None
        key, sep, value = line.partition(": ")
        if sep and key.strip() == "state":
            value = value.strip().strip("'\"")
            return value if value in STATES else None
    return None


def collect(roots):
    """Every notebook and card across the given workbench roots, with state and bell.

    Read-only. A root is a workbench checkout (it has `projects/`). Items with
    `state: needs-you` come first, invalid bells flagged, so one file read answers
    "what needs me" across BC and Mindspan without a second board.
    """
    items = []
    for root in roots:
        root = Path(root)
        for path in sorted(root.glob("projects/*/focus/F-*.md")) + sorted(root.glob("projects/*/cards/*.md")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")[:262144]
            except OSError:
                continue
            state = frontmatter_state(text)
            if state is None:
                continue
            title = re.search(r"^# (.+)$", text, re.M)
            updated = re.search(r"^(?:Updated|updated):\s*(\S+)", text, re.M)
            item = dict(workbench=root.name, project=path.parts[-3], file=str(path.relative_to(root)),
                        id=path.stem, title=title.group(1).strip() if title else "", state=state,
                        updated=updated.group(1) if updated else "")
            if state == "needs-you":
                item["needs_you"] = parse(text)
            items.append(item)
    order = {"needs-you": 0, "working": 1, "paused": 2, "done": 3}
    items.sort(key=lambda i: (order[i["state"]], i["workbench"], i["project"], i["id"]))
    return items


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="List needs-you items across workbench checkouts (read-only).")
    parser.add_argument("roots", nargs="*", help="workbench roots; default: RDASH_REPO_ROOT or the current directory")
    parser.add_argument("--all", action="store_true", help="include working, paused and done items")
    parser.add_argument("--write", help="write JSON here (keep it git-ignored) instead of stdout")
    args = parser.parse_args(argv)
    import os
    roots = args.roots or [os.environ.get("RDASH_REPO_ROOT") or os.getcwd()]
    items = collect(roots)
    if not args.all:
        items = [i for i in items if i["state"] == "needs-you"]
    payload = dict(needs_you=items, roots=[str(Path(r).resolve()) for r in roots])
    text = json.dumps(payload, indent=2) + "\n"
    if args.write:
        Path(args.write).write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
