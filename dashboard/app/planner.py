"""Plan and Summary modes, read from the workbench's own files and written back one line at a time.

The board at `/` is the Project mode. These pages add two more over the same repository:

  Plan     /plan/ladder            every sprint in plan/*.md (a file with a `## Rungs` table, e.g.
                                   plan/LADDER.md), one row per sprint, one column per month; months
                                   -1 / 0 / +1 are the visible three, the rest scroll
           /plan/daily[?d=DATE]    plan/days/YYYY-MM-DD.md as checkboxes grouped by `## project`
           /plan/weekly[?w=DATE]   plan/weeks/YYYY-MM-DD.md (a Monday), the same shape
  Summary  /summary                plan/summary/YYYY-MM-DD-<kind>.md: the weekly summary and the
                                   heads / Ed / Konrad record, as a cadence table and a list
           /summary/view?p=<rel>   one of those files rendered

Writes (POST /api/plan/edit, /api/plan/new) touch only plan/days and plan/weeks: a tick flips
`[ ]` <-> `[x]` on one line, a delete drops one item and its indented notes, and `new` creates
an empty day or week file. The line must still read what the page showed, so a stale tab cannot
edit the wrong item. Gate tags in a ladder are read, never inferred (see ladder.py).
"""
import calendar
import datetime as dt
import html
import re
from pathlib import Path
from urllib.parse import quote

from .ladder import _table
from .safety import Error, publish_replace, resolve_within, writer_lock

KINDS = [("weekly", "weekly summary", "Thu"), ("heads", "heads meeting", "Tue"),
         ("ed", "Ed 1-on-1", "Thu"), ("konrad", "Konrad 1-on-1", "Thu"), ("note", "note", "")]
KIND_LABEL = {k: l for k, l, _ in KINDS}
MODES = [("plan", "Plan", "/plan/ladder"), ("project", "Project", "/"), ("summary", "Summary", "/summary")]
PLAN_SUBS = [("ladder", "Ladder", "/plan/ladder"), ("daily", "Daily", "/plan/daily"), ("weekly", "Weekly", "/plan/weekly")]
NAME = re.compile(r"\d{4}-\d{2}-\d{2}\.md")
MAX_FILE = 1048576


# ---------- reading ----------

def _text(path):
    with path.open("rb") as source:
        return source.read(MAX_FILE).decode("utf-8", errors="replace")


def inline(md, links=False):
    s = html.escape(md)
    if links:
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"~~(.+?)~~", r"<s>\1</s>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"<i>\1</i>", s)
    return s


def add_months(y, m, k):
    yy, mm = divmod((y * 12 + m - 1) + k, 12)
    return yy, mm + 1


def _items(lines, start=0):
    """Checkbox items from a run of lines: {'line', 'orig', 'text', 'state': todo|doing|done|note, 'sub': [text]}."""
    items = []
    for i, line in enumerate(lines, start):
        line = line.rstrip()
        if line.startswith("- "):
            mt = re.match(r"- \[([ xX.])\] (.*)", line)
            state = ({" ": "todo", ".": "doing"}.get(mt.group(1).lower(), "done")) if mt else "note"
            items.append(dict(line=i, orig=line, text=mt.group(2) if mt else line[2:], state=state, sub=[]))
        elif items and re.match(r"^\s+- ", line):
            items[-1]["sub"].append(re.sub(r"^\s+- (\[[ xX.]\] )?", "", line))
    return items


def read_deliverables(text):
    """'## Deliverables' → {(year, month): [(heading, [item])]}: one '### YYYY-MM …' block per rung, in file order."""
    out, lines = {}, text.split("\n")
    head = next((i for i, l in enumerate(lines) if l.rstrip() == "## Deliverables"), None)
    if head is None:
        return out
    block, start = None, None
    def close(end):
        if block:
            out.setdefault(block[0], []).append((block[1], _items(lines[start:end], start)))
    for i in range(head + 1, len(lines) + 1):
        line = lines[i].rstrip() if i < len(lines) else "## "
        if line.startswith("## "):
            close(i)
            break
        m = re.match(r"### (\d{4})-(0[1-9]|1[0-2])\b\s*[—–-]?\s*(.*)", line)
        if m:
            close(i)
            block, start = ((int(m.group(1)), int(m.group(2))), m.group(3).strip()), i + 1
    return out


def read_ladder(path, rel):
    """One ladder file: its '## Rungs' rows grouped by (year, month), gate cells tagged as ladder.py tags them,
    and each rung's '## Deliverables' checklist (matched by month, then by rung name when a month has several)."""
    lad = dict(rel=rel, label=rel, title="", months={}, gates=[], errors=[], missing=not path.exists())
    if lad["missing"]:
        return lad
    text = _text(path)
    lad["title"] = next((l[2:].strip() for l in text.split("\n") if l.startswith("# ")), rel)
    lad["label"] = lad["title"]
    lad["gates"] = _table(text, "Gates")
    deliverables = read_deliverables(text)
    for row in _table(text, "Rungs"):
        m = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", row.get("month", ""))
        if not m:
            lad["errors"].append("rung %r: month %r is not YYYY-MM" % (row.get("rung", "?"), row.get("month", "")))
            continue
        for g in ("g1", "g2", "g3"):
            value = row.get(g, "")
            tag = re.match(r"^\[([^]]+)\]\s*", value)
            if tag and tag.group(1) in ("met", "open", "failed"):
                state, value = tag.group(1), value[tag.end():]
            else:
                state = "none" if value in ("", "-", "—") else "target"
                if tag:
                    lad["errors"].append("rung %r: unknown gate tag %s" % (row.get("rung", "?"), tag.group(0).strip()))
            row[g] = dict(state=state, text=value)
        lad["months"].setdefault((int(m.group(1)), int(m.group(2))), []).append(row)
    for ym, rows in lad["months"].items():
        blocks = deliverables.get(ym, [])
        for row in rows:
            # a block names its rung ("### 2026-11 — 50 µm"); an unnamed block, or the month's only block, fits the month's only rung
            hit = next((b for b in blocks if b[0] and b[0] in row.get("rung", "")), None)
            if hit is None and len(rows) == 1 and blocks:
                hit = blocks[0]
            row["items"] = hit[1] if hit else []
    return lad


def ladders(settings):
    """One row per sprint: every plan/*.md carrying a `## Rungs` table, LADDER.md first then by name.
    With no such file the row for plan/LADDER.md is shown as missing."""
    folder = resolve_within(settings.repo_root, "plan")
    out = []
    if folder.is_dir():
        for path in sorted(folder.iterdir(), key=lambda p: (p.name != "LADDER.md", p.name)):
            if path.suffix == ".md" and not path.is_symlink() and path.is_file() and _table(_text(path), "Rungs"):
                out.append(read_ladder(resolve_within(folder, path.name), "plan/" + path.name))
    return out or [read_ladder(resolve_within(settings.repo_root, "plan", "LADDER.md"), "plan/LADDER.md")]


def plan_path(settings, rel):
    """The one file a plan edit may touch: plan/days/YYYY-MM-DD.md, plan/weeks/YYYY-MM-DD.md (a Monday),
    or a sprint file plan/<name>.md (its deliverables checklist)."""
    if not isinstance(rel, str):
        raise Error(400, "invalid_path", "Plan path must be a string")
    sprint = re.fullmatch(r"plan/([A-Za-z0-9][A-Za-z0-9_.-]*)\.md", rel)
    if sprint and ".." not in sprint.group(1):
        return resolve_within(settings.repo_root, "plan", sprint.group(1) + ".md")
    m = re.fullmatch(r"plan/(days|weeks)/(\d{4}-\d{2}-\d{2})\.md", rel)
    if not m:
        raise Error(400, "invalid_path", "Plan path must be plan/<sprint>.md, plan/days/YYYY-MM-DD.md or plan/weeks/YYYY-MM-DD.md")
    try:
        day = dt.date.fromisoformat(m.group(2))
    except ValueError:
        raise Error(400, "invalid_path", "Plan path has no such date")
    if m.group(1) == "weeks" and day.weekday() != 0:
        raise Error(400, "invalid_path", "A week file is named by its Monday")
    return resolve_within(settings.repo_root, "plan", m.group(1), m.group(2) + ".md")


def read_plan(settings, rel):
    """{'rel', 'exists', 'title', 'sections': [{'name', 'level', 'items': [item]}]}

    item = {'line', 'orig', 'text', 'state': todo|doing|done|note, 'sub': [text]}. A '## heading'
    is a project; '###' a group inside it; bullets before any heading go to '(no project)'."""
    path = plan_path(settings, rel)
    info = dict(rel=rel, exists=path.exists(), title=None, sections=[])
    if not info["exists"]:
        return info
    sec = None
    for i, line in enumerate(_text(path).split("\n")):
        line = line.rstrip()
        if line.startswith("# ") and info["title"] is None:
            info["title"] = line[2:].strip()
        elif re.match(r"^#{2,3} ", line):
            level = len(line) - len(line.lstrip("#"))
            sec = dict(name=line[level:].strip(), level=level, items=[])
            info["sections"].append(sec)
        elif line.startswith("- "):
            if sec is None:
                sec = dict(name="(no project)", level=2, items=[])
                info["sections"].append(sec)
            sec["items"] += _items([line], i)
        elif sec and sec["items"] and re.match(r"^\s+- ", line):
            sec["items"][-1]["sub"].append(re.sub(r"^\s+- (\[[ xX.]\] )?", "", line))
    return info


def summaries(settings):
    """plan/summary/YYYY-MM-DD-<kind>.md, newest first; kind from the name tokens, else 'note'."""
    folder = resolve_within(settings.repo_root, "plan", "summary")
    out = []
    if not folder.is_dir():
        return out
    for path in sorted(folder.iterdir()):
        m = re.match(r"(\d{4}-\d{2}-\d{2})[-_]?(.*)\.md$", path.name)
        if not m or path.is_symlink() or not path.is_file():
            continue
        try:
            date = dt.date.fromisoformat(m.group(1))
        except ValueError:
            continue
        toks = re.split(r"[-_]", m.group(2).lower())
        kind = next((k for k, *_ in KINDS[:-1] if k in toks), "note")
        text = _text(resolve_within(folder, path.name))
        title = next((l[2:].strip() for l in text.split("\n") if l.startswith("# ")), path.stem)
        out.append(dict(rel="plan/summary/" + path.name, date=date, kind=kind, title=title,
                        monday=date - dt.timedelta(days=date.weekday())))
    return sorted(out, key=lambda e: (e["date"], e["rel"]), reverse=True)


def summary_path(settings, rel):
    if not isinstance(rel, str) or not re.fullmatch(r"plan/summary/[A-Za-z0-9][A-Za-z0-9._-]*\.md", rel):
        raise Error(400, "invalid_path", "Summary path must be plan/summary/<name>.md")
    return resolve_within(settings.repo_root, "plan", "summary", rel[len("plan/summary/"):])


# ---------- writing ----------

def apply_edit(settings, rel, line, orig, op):
    path = plan_path(settings, rel)
    with writer_lock(settings):
        if not path.exists():
            raise Error(404, "not_found", "No such plan file")
        lines = _text(path).split("\n")
        if type(line) is not int or not 0 <= line < len(lines) or not isinstance(orig, str) or lines[line].rstrip() != orig.rstrip():
            raise Error(409, "stale_line", "That line changed since the page loaded; reload and retry")
        if op == "toggle":
            m = re.match(r"^(\s*- \[)([ xX.])(\].*)$", lines[line])
            if not m:
                raise Error(400, "not_checkbox", "Not a checkbox line")
            lines[line] = m.group(1) + (" " if m.group(2).lower() == "x" else "x") + m.group(3)
        elif op == "delete":
            indent = len(lines[line]) - len(lines[line].lstrip())
            end = line + 1
            while end < len(lines) and lines[end].strip() and (len(lines[end]) - len(lines[end].lstrip())) > indent:
                end += 1
            del lines[line:end]
        else:
            raise Error(400, "invalid_op", "op must be toggle or delete")
        publish_replace(path, "\n".join(lines).encode("utf-8"))
    return "%s: %s:%d" % (op, rel, line + 1)


def new_plan(settings, rel, projects=()):
    """Create an empty day or week file: a title and one `## heading` per project named."""
    path = plan_path(settings, rel)
    with writer_lock(settings):
        if path.exists():
            return "exists: " + rel
        day = dt.date.fromisoformat(path.stem)
        title = ("Week of %s" % day.strftime("%a %Y-%m-%d")) if path.parent.name == "weeks" else day.strftime("%a %Y-%m-%d")
        path.parent.mkdir(parents=True, exist_ok=True)
        publish_replace(path, ("# %s\n\n" % title + "".join("## %s\n\n" % p for p in projects)).encode("utf-8"))
    return "created " + rel


# ---------- rendering ----------

def page(title, mode, sub, body, problems=(), source=""):
    nav = "".join('<a href="%s" class="mode%s">%s</a>' % (u, " on" if k == mode else "", l) for k, l, u in MODES)
    if mode == "plan":   # the three mode buttons sit centred on their own row; the Plan sub-views below them
        nav += '</nav><nav class="subs">' + "".join(
            '<a href="%s" class="%s">%s</a>' % (u, "on" if k == sub else "", l) for k, l, u in PLAN_SUBS)
    prob = "".join("<li>%s</li>" % html.escape(p) for p in problems)
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>%s</title><link rel="stylesheet" href="/static/planner.css"><script src="/static/planner.js" defer></script></head>'
            '<body><nav class="modes">%s</nav>%s%s<p class="src">Read from the repository at %s. Edit the files, then reload.%s</p></body></html>'
            % (html.escape(title), nav, body, ("<ul class=problems>%s</ul>" % prob) if prob else "",
               dt.datetime.now().strftime("%H:%M:%S"), (" " + html.escape(source)) if source else ""))


def month_name(y, m):
    return dt.date(y, m, 1).strftime("%b %Y")


def render_ladder(settings, today=None):
    today = today or dt.date.today()
    lads = ladders(settings)
    cur = (today.year, today.month)
    have = {add_months(*cur, k) for k in (-1, 0, 1)} | {ym for l in lads for ym in l["months"]}
    months, ym, hi = [], min(have), max(have)
    while ym <= hi:
        months.append(ym)
        ym = add_months(*ym, 1)
    cells = ['<div class="lcorner">Ladder</div>']
    cells += ['<div class="lmon%s">%s</div>' % (" now" if ym == cur else "", month_name(*ym)) for ym in months]
    notes, problems = [], []
    for lad in lads:
        cells.append('<div class="lname">%s<small>%s</small></div>' % (html.escape(lad["label"]), html.escape(lad["rel"])))
        names = _gate_names(lad["gates"])
        for ym in months:
            cls = " now" if ym == cur else " past" if ym < cur else ""
            rungs = "".join(_rung_card(lad["rel"], r, names) for r in lad["months"].get(ym, []))
            cells.append('<div class="lcell%s">%s</div>' % (cls, rungs))
        if lad["missing"]:
            notes.append('<p class="empty"><b>%s</b> is missing, so its row is empty.</p>' % html.escape(lad["rel"]))
            continue
        gates = "".join("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            inline(g.get("gate", "")), inline(g.get("question", "")), inline(g.get("recorded_in", ""))) for g in lad["gates"])
        notes.append('<details><summary><b>%s</b> · %s</summary><table class="cad"><tr><th>Gate</th><th>Question</th><th>Recorded in</th></tr>%s</table></details>'
                     % (html.escape(lad["title"]), html.escape(lad["rel"]), gates))
        problems += ["%s: %s" % (lad["rel"], e) for e in lad["errors"]]
    body = ('<h1>%s · ladders by month · %d row%s, %d months (scroll sideways; ‹ › move one month)</h1>'
            '<p class="legend">A rung is one month\'s deliverable; it passes when its three gates are met: '
            '<b>G1 it ran</b> · <b>G2 quality</b> · <b>G3 cost</b> (each ladder\'s own gate table is under the grid). '
            'Gate colours: <span class="g met">met</span> <span class="g open">open</span> <span class="g failed">failed</span> '
            '<span class="g target">target</span> <span class="g none">—</span>, read from the ladder file, never inferred. '
            'Below the gates, the rung\'s deliverables are a checklist (<span class="dot done"></span> done '
            '<span class="dot doing"></span> in progress <span class="dot todo"></span> open) edited in place.</p>'
            '<div class="lwrap"><button class="larr" data-dir="-1" title="earlier month">‹</button>'
            '<div class="lscroll" id="lscroll"><div class="lgrid" data-n="%d">%s</div></div>'
            '<button class="larr" data-dir="1" title="later month">›</button></div>%s'
            % (today.strftime("%a %m/%d"), len(lads), "s" if len(lads) != 1 else "", len(months), len(months), "".join(cells), "".join(notes)))
    return page("Plan · Ladder", "plan", "ladder", body, problems, "Rows: every plan/*.md with a ## Rungs table (one per sprint).")


GATE_WORDS = {"g1": "it ran", "g2": "quality", "g3": "cost"}
GATE_STATE = {"met": "met", "open": "open", "failed": "failed", "target": "target", "none": "—"}


def _gate_names(gates):
    """{'g1': ('it ran', question)} from a ladder's Gates table, with the default words when the table lacks them."""
    names = {}
    for g in gates:
        m = re.match(r"\**(G[123])\**\s*[—–-]+\s*(.+?)\**$", g.get("gate", ""))
        if m:
            names[m.group(1).lower()] = (m.group(2).strip("* "), g.get("question", ""))
    return {k: names.get(k, (GATE_WORDS[k], "")) for k in GATE_WORDS}


def _rung_card(rel, r, names):
    """One rung: header (name, data, overall state), one row per gate, then the deliverables checklist."""
    states = [r[g]["state"] for g in ("g1", "g2", "g3")]
    overall = ("failed" if "failed" in states else "met" if states[0] == "met" and states[1] == "met" and states[2] in ("met", "none")
               else "open" if "met" in states or "open" in states else "target" if "target" in states else "none")
    rows = ""
    for g in ("g1", "g2", "g3"):
        word, question = names[g]
        rows += ('<div class="gate %s" title="%s"><span class="g %s">%s</span><span class="gw">%s</span><span class="gt">%s</span></div>'
                 % (r[g]["state"], html.escape(question, quote=True), r[g]["state"], g.upper(), html.escape(word),
                    inline(r[g]["text"]) if r[g]["text"].strip() not in ("", "-", "—") else '<i class="none">no evidence yet</i>'))
    items = r.get("items", [])
    done = sum(1 for it in items if it["state"] == "done")
    todo = ('<div class="dhead">deliverables <span class="dn">%d / %d</span></div><ul class="todo">%s</ul>'
            % (done, len(items), "".join(_todo(rel, it) for it in items))) if items else ""
    nb = r.get("notebook_question", "").strip()
    nb = '<div class="rnb">%s</div>' % inline(nb, links=True) if nb not in ("", "-", "—") else ""
    return ('<div class="rung %s"><div class="rtop"><b>%s</b><span class="rdata">%s</span><span class="g %s">%s</span></div>'
            '<div class="gates">%s</div>%s<div class="rstat">%s</div>%s</div>'
            % (overall, inline(r.get("rung", "")), inline(r.get("data", "")), overall, GATE_STATE[overall], rows, todo,
               inline(r.get("status", "")), nb))


def _todo(rel, item):
    box = ('<input type="checkbox" data-op="toggle"%s>' % (" checked" if item["state"] == "done" else "")) if item["state"] != "note" else ""
    subs = "".join('<span class="sub">– %s</span>' % inline(s) for s in item["sub"])
    return ('<li class="%s" data-path="%s" data-line="%d" data-orig="%s">%s<span class="txt">%s%s</span>'
            '<button class="del" data-op="delete" title="delete this item from %s">×</button></li>'
            % (item["state"], html.escape(rel, quote=True), item["line"], html.escape(item["orig"], quote=True), box,
               inline(item["text"]), subs, html.escape(rel, quote=True)))


def _checklist(settings, info, title, nav, kind):
    rel = info["rel"]
    if not info["exists"]:
        projects = sorted(p.name for p in (settings.repo_root / "projects").iterdir()
                          if p.is_dir() and not p.is_symlink() and p.name not in ("config", "TEMPLATE"))
        body = nav + ('<div class="proj"><p>No %s plan written — nothing at <code>%s</code>.</p>'
                      '<p class="empty">A plan file is <code># heading</code>, then one <code>## project</code> per block and '
                      '<code>- [ ] item</code> lines under it (indented sub-bullets are notes; <code>- [.]</code> marks in progress).</p>'
                      '<button class="primary" data-new="%s" data-projects="%s">Create it with one heading per project</button></div>'
                      % (kind, html.escape(rel), html.escape(rel, quote=True), html.escape(",".join(projects), quote=True)))
        return page(title, "plan", kind, body)
    done = sum(i["state"] == "done" for s in info["sections"] for i in s["items"])
    total = sum(i["state"] != "note" for s in info["sections"] for i in s["items"])
    projs, cur = [], None
    for s in info["sections"]:
        items = "".join(_todo(rel, i) for i in s["items"])
        lst = ('<ul class="todo">%s</ul>' % items) if items else '<p class="empty">no items</p>'
        if s["level"] == 2 or cur is None:
            n = sum(i["state"] != "note" for i in s["items"])
            k = sum(i["state"] == "done" for i in s["items"])
            cur = ['<div class="proj"><h3>%s<small>%d/%d</small></h3>%s' % (inline(s["name"]), k, n, lst)]
            projs.append(cur)
        else:
            cur[0] += "<h4>%s</h4>%s" % (inline(s["name"]), lst)
    body = (nav + '<h1>%s · %d/%d done · tick to mark done, × to delete the line from the file</h1><div class="projs">%s</div>%s'
            % (inline(info["title"] or ""), done, total, "".join(p[0] + "</div>" for p in projs),
               '<p class="empty">No items yet: add <code>- [ ] item</code> lines under a <code>## project</code> heading.</p>' if not projs else ""))
    return page(title, "plan", kind, body, (), rel)


def render_daily(settings, d=None, today=None):
    today = today or dt.date.today()
    d = d or today
    rel = "plan/days/%s.md" % d.isoformat()
    prev, nxt = d - dt.timedelta(days=1), d + dt.timedelta(days=1)
    nav = ('<div class="daynav"><a href="/plan/daily?d=%s">‹ %s</a><b>%s</b><a href="/plan/daily?d=%s">%s ›</a>%s'
           '<span class="src">%s</span></div>'
           % (prev, prev.strftime("%a %m/%d"), d.strftime("%A %Y-%m-%d"), nxt, nxt.strftime("%a %m/%d"),
              "" if d == today else '<a href="/plan/daily">today</a>', rel))
    return _checklist(settings, read_plan(settings, rel), "Plan · Daily " + d.isoformat(), nav, "daily")


def render_weekly(settings, monday=None, today=None):
    today = today or dt.date.today()
    this_monday = today - dt.timedelta(days=today.weekday())
    monday = monday or this_monday
    monday -= dt.timedelta(days=monday.weekday())
    sun = monday + dt.timedelta(days=6)
    rel = "plan/weeks/%s.md" % monday.isoformat()
    prev, nxt = monday - dt.timedelta(days=7), monday + dt.timedelta(days=7)
    nav = ('<div class="daynav"><a href="/plan/weekly?w=%s">‹ week of %s</a><b>Week of %s – %s%s</b><a href="/plan/weekly?w=%s">week of %s ›</a>%s'
           '<span class="src">%s</span></div>'
           % (prev, prev.strftime("%m/%d"), monday.strftime("%a %m/%d"), sun.strftime("%a %m/%d"),
              " · this week" if monday == this_monday else "", nxt, nxt.strftime("%m/%d"),
              "" if monday == this_monday else '<a href="/plan/weekly">this week</a>', rel))
    return _checklist(settings, read_plan(settings, rel), "Plan · Week of " + monday.isoformat(), nav, "weekly")


def render_summary(settings, today=None, weeks=10):
    today = today or dt.date.today()
    ents = summaries(settings)
    this_monday = today - dt.timedelta(days=today.weekday())
    rows = []
    for k in range(weeks):
        mon = this_monday - dt.timedelta(days=7 * k)
        cells = []
        for kind, label, day in KINDS[:-1]:
            hits = [e for e in ents if e["monday"] == mon and e["kind"] == kind]
            if hits:
                cells.append("<br>".join('<a href="/summary/view?p=%s" title="%s">%s</a>' % (
                    quote(e["rel"]), html.escape(e["title"], quote=True), e["date"].strftime("%m/%d")) for e in hits))
            else:
                due = mon + dt.timedelta(days=["Mon", "Tue", "Wed", "Thu"].index(day))
                cells.append('<span class="due">due %s</span>' % day if mon == this_monday and due >= today
                             else '<span class="%s">—</span>' % ("late" if mon == this_monday else "miss"))
        others = [e for e in ents if e["monday"] == mon and e["kind"] == "note"]
        cells.append(" · ".join('<a href="/summary/view?p=%s">%s %s</a>' % (
            quote(e["rel"]), e["date"].strftime("%m/%d"), html.escape(e["title"])) for e in others) or '<span class="miss">—</span>')
        rows.append('<tr class="%s"><td>%s%s</td>%s</tr>' % ("now" if mon == this_monday else "", mon.strftime("%m/%d"),
                    " · this week" if mon == this_monday else "", "".join("<td>%s</td>" % c for c in cells)))
    head = "".join("<th>%s%s</th>" % (l, " (%s)" % d if d else "") for _, l, d in KINDS[:-1]) + "<th>other notes</th>"
    chips = '<button class="chip on" data-k="all">all</button>' + "".join(
        '<button class="chip" data-k="%s">%s (%d)</button>' % (k, l, sum(e["kind"] == k for e in ents)) for k, l, _ in KINDS)
    lis = "".join('<li data-k="%s"><span class="d">%s</span><span class="k %s">%s</span><a href="/summary/view?p=%s">%s</a><small>%s</small></li>'
                  % (e["kind"], e["date"].strftime("%a %Y-%m-%d"), e["kind"], KIND_LABEL[e["kind"]], quote(e["rel"]),
                     html.escape(e["title"]), html.escape(e["rel"])) for e in ents)
    body = ('<h1>%s · the weekly summary and the heads / Ed / Konrad record, last %d weeks · heads meeting Tue, 1-on-1s Thu, summary dated the Thursday</h1>'
            '<table class="cad"><tr><th>week of</th>%s</tr>%s</table>'
            '<h2>All notes <small>%d files in plan/summary/</small></h2><div class="chips">%s</div><ul class="ent">%s</ul>'
            % (today.strftime("%a %m/%d"), weeks, head, "".join(rows), len(ents), chips,
               lis or '<li><span class="empty">none yet — add plan/summary/YYYY-MM-DD-weekly.md (or -heads, -ed, -konrad)</span></li>'))
    return page("Summary", "summary", "", body, (), "Kinds come from the file name: -weekly, -heads, -ed, -konrad; anything else is a note.")


def render_summary_view(settings, rel):
    path = summary_path(settings, rel)
    if not path.exists():
        raise Error(404, "not_found", "No such summary file")
    body = ('<div class="daynav"><a href="/summary">‹ all summaries</a><span class="src">%s</span></div><div class="doc">%s</div>'
            % (html.escape(rel), md_html(_text(path))))
    return page("Summary · " + path.stem, "summary", "", body)


def md_html(text):
    """A small block renderer for the notes: headings, lists (nested, checkboxes), tables, fences, quotes."""
    out, lines, i = [], text.split("\n"), 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(lines[i + 1:j])) + "</code></pre>")
            i = j + 1
            continue
        if l.lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in lines[i:j]]
            rows = [r for r in rows if not all(re.fullmatch(r":?-+:?", c or "-") for c in r)]
            if rows:
                out.append("<table><tr>" + "".join("<th>%s</th>" % inline(c, True) for c in rows[0]) + "</tr>"
                           + "".join("<tr>" + "".join("<td>%s</td>" % inline(c, True) for c in r) + "</tr>" for r in rows[1:]) + "</table>")
            i = j
            continue
        m = re.match(r"^(#{1,6}) (.*)", l)
        if m:
            out.append("<h%d>%s</h%d>" % (len(m.group(1)), inline(m.group(2), True), len(m.group(1))))
            i += 1
            continue
        if re.match(r"^\s*([-*+]|\d+[.)]) ", l):
            j = i
            while j < len(lines) and (re.match(r"^\s*([-*+]|\d+[.)]) ", lines[j]) or (lines[j].startswith("  ") and lines[j].strip())):
                j += 1
            out.append(_list_html(lines[i:j]))
            i = j
            continue
        if l.startswith(">"):
            j = i
            while j < len(lines) and lines[j].startswith(">"):
                j += 1
            out.append("<blockquote>" + md_html("\n".join(x[1:].lstrip() for x in lines[i:j])) + "</blockquote>")
            i = j
            continue
        if l.strip() in ("---", "***", "___"):
            out.append("<hr>")
            i += 1
            continue
        if not l.strip():
            i += 1
            continue
        j = i
        while j < len(lines) and lines[j].strip() and not re.match(r"^(#{1,6} |```|\s*([-*+]|\d+[.)]) |>|\|)", lines[j]):
            j += 1
        out.append("<p>" + inline(" ".join(x.strip() for x in lines[i:j]), True) + "</p>")
        i = max(j, i + 1)
    return "".join(out)


def _list_html(lines):
    out, stack, pending = [], [], None
    for l in lines:
        m = re.match(r"^(\s*)([-*+]|\d+[.)]) (.*)", l)
        if not m:
            if pending is not None:
                out[pending] = out[pending][:-5] + " " + inline(l.strip(), True) + "</li>"
            continue
        ind, tag, body = len(m.group(1)), "ol" if m.group(2)[0].isdigit() else "ul", m.group(3)
        while stack and ind < stack[-1][0]:
            out.append("</%s>" % stack.pop()[1])
        if not stack or ind > stack[-1][0]:
            stack.append((ind, tag))
            out.append("<%s>" % tag)
        cb = re.match(r"\[([ xX.])\] (.*)", body)
        if cb:
            body = {"x": "☑", ".": "◐"}.get(cb.group(1).lower(), "☐") + " " + cb.group(2)
        out.append("<li>%s</li>" % inline(body, True))
        pending = len(out) - 1
    while stack:
        out.append("</%s>" % stack.pop()[1])
    return "".join(out)
