"use strict";
const el = id => document.getElementById(id);

// ---------------------------------------------------------------------------
// Markdown rendering.
//
// Cards are Markdown files, so the detail view renders them. Block and inline
// styling follows pm's dashboard (.markdown-content), but nodes are built
// with createElement/textContent rather than escape-then-innerHTML: that
// pattern interpolates the link URL unescaped, so [x](javascript:...) stays
// live. Here a URL can only ever become an href after passing SAFE_URL.
// ---------------------------------------------------------------------------
const SAFE_URL = /^(https?:\/\/|mailto:)/i;

function inlineInto(parent, text) {
  // One pass, longest-anchored alternatives first; \[ ]\( ) before * and _.
  const pattern = /(`[^`]+`)|(\[[^\]]+\]\([^)\s]*\))|(\*\*[^*]+\*\*)|(~~[^~]+~~)|(\*[^*\n]+\*)/;
  let rest = text;
  while (rest) {
    const m = pattern.exec(rest);
    if (!m) { parent.append(document.createTextNode(rest)); return; }
    if (m.index) parent.append(document.createTextNode(rest.slice(0, m.index)));
    const token = m[0];
    if (token.startsWith("`")) {
      const code = document.createElement("code");
      code.textContent = token.slice(1, -1);
      parent.append(code);
    } else if (token.startsWith("[")) {
      const split = token.indexOf("](");
      const label = token.slice(1, split);
      const href = token.slice(split + 2, -1);
      if (SAFE_URL.test(href)) {
        const a = document.createElement("a");
        a.href = href;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = label;
        parent.append(a);
      } else {
        // Repo-relative targets: the server deliberately does not serve
        // repository documents, so show the path instead of a dead link.
        const span = document.createElement("span");
        span.className = "md-path";
        span.textContent = label;
        span.title = href;
        parent.append(span);
      }
    } else if (token.startsWith("**")) {
      const strong = document.createElement("strong");
      inlineInto(strong, token.slice(2, -2));   // recurse: **bold with `code`**
      parent.append(strong);
    } else if (token.startsWith("~~")) {
      const s = document.createElement("s");
      inlineInto(s, token.slice(2, -2));
      parent.append(s);
    } else {
      const em = document.createElement("em");
      inlineInto(em, token.slice(1, -1));
      parent.append(em);
    }
    rest = rest.slice(m.index + token.length);
  }
}

function renderMarkdown(text) {
  const out = document.createDocumentFragment();
  const lines = String(text || "").split("\n");
  let i = 0;
  const listItemOf = line => /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(line);

  while (i < lines.length) {
    const line = lines[i];

    if (/^\s*$/.test(line)) { i += 1; continue; }

    const fence = /^\s*(```|~~~)(.*)$/.exec(line);
    if (fence) {
      const marker = fence[1];
      const body = [];
      i += 1;
      while (i < lines.length && !lines[i].trimStart().startsWith(marker)) { body.push(lines[i]); i += 1; }
      i += 1;
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      if (fence[2].trim()) code.dataset.lang = fence[2].trim();
      code.textContent = body.join("\n");
      pre.append(code);
      out.append(pre);
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const h = document.createElement("h" + Math.min(heading[1].length, 6));
      inlineInto(h, heading[2].trim());
      out.append(h);
      i += 1;
      continue;
    }

    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
      out.append(document.createElement("hr"));
      i += 1;
      continue;
    }

    if (/^\s*>/.test(line)) {
      const body = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) { body.push(lines[i].replace(/^\s*>\s?/, "")); i += 1; }
      const quote = document.createElement("blockquote");
      quote.append(renderMarkdown(body.join("\n")));
      out.append(quote);
      continue;
    }

    // Table: a header row followed by a |---|---| delimiter.
    if (line.includes("|") && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(lines[i + 1])) {
      const cells = row => row.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      const table = document.createElement("table");
      const thead = document.createElement("thead");
      const hrow = document.createElement("tr");
      for (const c of cells(line)) { const th = document.createElement("th"); inlineInto(th, c); hrow.append(th); }
      thead.append(hrow);
      table.append(thead);
      i += 2;
      const tbody = document.createElement("tbody");
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        const tr = document.createElement("tr");
        for (const c of cells(lines[i])) { const td = document.createElement("td"); inlineInto(td, c); tr.append(td); }
        tbody.append(tr);
        i += 1;
      }
      table.append(tbody);
      out.append(table);
      continue;
    }

    const item = listItemOf(line);
    if (item) {
      const ordered = /\d/.test(item[2]);
      const list = document.createElement(ordered ? "ol" : "ul");
      while (i < lines.length) {
        const current = listItemOf(lines[i]);
        if (!current || /\d/.test(current[2]) !== ordered) break;
        // A bullet may wrap onto indented continuation lines; keep them with it.
        const parts = [current[3]];
        i += 1;
        while (i < lines.length && lines[i].trim() && !listItemOf(lines[i]) && /^\s/.test(lines[i])) {
          parts.push(lines[i].trim());
          i += 1;
        }
        const li = document.createElement("li");
        inlineInto(li, parts.join(" "));
        list.append(li);
      }
      out.append(list);
      continue;
    }

    const para = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\s*(```|~~~)|\s*>)/.test(lines[i]) && !listItemOf(lines[i])) {
      para.push(lines[i].trim());
      i += 1;
    }
    const p = document.createElement("p");
    inlineInto(p, para.join(" "));
    out.append(p);
  }
  return out;
}

let records = [];
let selected = null;
let generation = 0;
let plan = {declared: false, columns: [], tasks: [], tracks: [], runs: [], milestones: [], errors: []};
let asked = {questions: [], errors: []};

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Rdash": "1"},
    body: JSON.stringify(data),
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value.message || value.error || "Request failed");
  return value;
}

const meta = (card, key) => (card.metadata && card.metadata[key]) || "";
// `track:` and `cube:` may list several values, comma separated.
const listOf = (card, key) => meta(card, key).split(",").map(x => x.trim()).filter(Boolean);
// Short id for referencing a card: "MOE50-DATA-002" -> "DATA-002" (full id stays in tooltips).
const shortId = card => {
  const id = meta(card, "id");
  const m = /^[A-Za-z0-9]+-([A-Za-z]+-\d+)$/.exec(id);
  return m ? m[1] : id;
};
const title = card => {
  const name = meta(card, "title") || card.card;
  const id = shortId(card);
  return id ? id + " · " + name : name;
};

// Scheduler states collapse to four buckets for the lane badge. `unknown` is a
// real answer -- the scheduler was unreachable or has forgotten the job -- and
// is never folded into "done".
const JOB_BUCKET = {
  RUNNING: "run", COMPLETING: "run", CONFIGURING: "run",
  PENDING: "wait", REQUEUED: "wait", SUSPENDED: "wait",
  COMPLETED: "done",
  FAILED: "bad", CANCELLED: "bad", TIMEOUT: "bad", NODE_FAIL: "bad",
  OUT_OF_MEMORY: "bad", BOOT_FAIL: "bad", DEADLINE: "bad", PREEMPTED: "bad",
};
const BUCKET_LABEL = {run: "running", wait: "queued", done: "done", bad: "failed", unknown: "unknown"};

function jobSummary(card) {
  const counts = {};
  for (const job of card.jobs || []) {
    const bucket = JOB_BUCKET[String(job.state).toUpperCase()] || "unknown";
    counts[bucket] = (counts[bucket] || 0) + 1;
  }
  return counts;
}

function appendJobBadges(parent, card) {
  const counts = jobSummary(card);
  for (const bucket of ["run", "wait", "bad", "done", "unknown"]) {
    if (!counts[bucket]) continue;
    const tag = document.createElement("span");
    tag.className = "tag job job-" + bucket;
    tag.textContent = counts[bucket] + " " + BUCKET_LABEL[bucket];
    parent.append(tag);
  }
}

function chip(parent, text, tooltip) {
  const tag = document.createElement("span");
  tag.className = "tag";
  tag.textContent = text;
  if (tooltip) tag.title = tooltip;
  parent.append(tag);
}

// The checker always emits authority_verification and evidence_verification as
// standing unknowns, so a count that includes them reads 2/2 on every passing
// card and teaches the eye to skip it. Only per-card findings are surfaced, and
// they hang off the structure chip rather than a counter of their own.
const CONSTANT_FINDINGS = ["authority_verification", "evidence_verification"];

// The contract's own words and nothing else. A reader scanning this column
// wants to know what the card is going to do; the structural check is a
// property of the file, belongs to the inspection view, and carried no signal
// here -- it reads the same on every passing card. No step carries a state:
// the card does not record one, and the board does not invent one.
function contractCell(parent, card) {
  const c = card.contract || {};
  const tasks = c.tasks || [];
  if (tasks.length) {
    const list = document.createElement("ol");
    list.className = "contract-tasks";
    for (const task of tasks) {
      const li = document.createElement("li");
      li.textContent = taskLabel(task);
      list.append(li);
    }
    parent.append(list);
    return;
  }
  const note = document.createElement("div");
  note.className = "sub";
  note.textContent = !c.declared ? "no contract declared"
    : c.method ? "method kept outside this card" : "no method steps authored";
  note.title = c.method || "";
  parent.append(note);
}

// Kind, structure and missing-fact count, for the detail view only. Structure
// is not authority: a card can pass this and still be wrong about everything.
function contractStatus(parent, card) {
  const c = card.contract || {};
  const notable = (c.findings || []).filter(f =>
    f.status !== "present" && !CONSTANT_FINDINGS.includes(f.field));
  const status = [c.kind, !c.declared ? "not declared"
    : c.structure === "pass" ? "structure passes" : "structure " + c.structure];
  if (c.missing_facts) status.push(c.missing_facts + " missing facts");
  chip(parent, status.filter(Boolean).join(" · "),
       [c.scope, c.reason, ...notable.map(f => f.status + " · " + f.field + ": " + f.detail)]
         .filter(Boolean).join("\n"));
}

// A declared session id is an address, so the chip opens it. Claude Code's
// desktop app registers `claude://`, and a session it has recorded is reachable
// at this path by id -- the board never invents an id, it only links one the
// card declares. The href is built here rather than authored on the card so a
// card carries the session's identity, not one client's URL scheme.
const SESSION_LINK = {claude: id => /^local_[A-Za-z0-9-]{8,}$/.test(id) &&
  "claude://claude.ai/epitaxy/" + id};

// Which session owns a card and where it is -- not whether it is running. This
// answers "where do I go to pick this up": the machine and the working
// directory, which is what a reader needs to reattach or to know that a run
// happened somewhere they cannot reach. Liveness is deliberately not tracked,
// so nothing here claims it either way.
//
// It sits under the card title rather than in a column because it identifies
// the card's owner, and because a column of "not declared" bought a sixth of
// the board's width to say nothing.
function sessionLine(parent, card) {
  const sessions = card.sessions || {};
  for (const session of sessions.items || []) {
    const text = [session.provider, session.label].filter(Boolean).join(" · ");
    const href = session.id && (SESSION_LINK[session.provider] || (() => false))(session.id);
    if (href) {
      const a = document.createElement("a");
      a.className = "tag session-link";
      a.href = href;
      a.textContent = text;
      a.title = "id " + session.id + "\nopens this session in " + session.provider;
      parent.append(a);
    } else {
      chip(parent, text, session.id && "id " + session.id);
    }
    // An undeclared location is silence, not a line: the chip above already
    // says a session owns this card.
    const location = [session.host, session.cwd].filter(Boolean).join(" · ");
    if (!location) continue;
    const where = document.createElement("div");
    where.className = "sub session-where";
    where.textContent = location;
    where.title = session.cwd || "";
    parent.append(where);
  }
}

// The declared sbatch id is already recorded on the card, so the chip carries
// what the card does not: the scheduler's own name for the task, and its state.
function jobWhen(job) {
  const t = v => v ? v.replace("T", " ").slice(5, 16) : "";
  if (job.phase === "done") return [t(job.start), t(job.end)].filter(Boolean).join(" → ");
  if (job.phase === "in progress") return job.start ? "since " + t(job.start) : "";
  return "";
}

// "done" covers failures too, so a non-COMPLETED end keeps its scheduler word.
function jobPhase(job) {
  if (job.phase === "done" && String(job.state).toUpperCase() !== "COMPLETED") return "done · " + job.state;
  return job.phase || job.state;
}

function evaluationCell(parent, card) {
  const a = card.acceptance || {};
  chip(parent, a.declared ? a.settled + "/" + a.total + " settled" : "not declared");
  chip(parent, "verdict: " + (card.verdict || "not recorded"));
}

// Cards waiting on the researcher sort first. Next is derived server-side and
// never authored on the card.
const OWNER_ORDER = {you: 0, agent: 1, scheduler: 2, none: 3};

function attentionLabel(card) {
  const attention = card.attention || {};
  if (attention.owner === "agent") return attention.next === "in_session" && card.sessions?.running
    ? "Coordinator in flight" : "Agent can investigate";
  return {you: "Your decision", scheduler: "Waiting on scheduler", none: "Closed"}[attention.owner] || "Next action unknown";
}

function attentionLine(parent, card) {
  const next = document.createElement("div"); next.className = "sub attention-next";
  next.textContent = attentionLabel(card);
  next.title = [(card.attention || {}).reason, "Next-action ownership is a suggestion; it does not start a worker."].filter(Boolean).join("\n");
  parent.append(next);
}

// A task groups several cards (frontmatter `task:`). Known tasks read in
// pipeline order; any other value follows alphabetically; untasked cards last.
// ALWAYS_TASKS get a column even when empty, as a place to file questions
// (`task: qc` in a questions/ file) before any card serves them. A project
// that lists `tasks` in its rdash-tracks block gets exactly those columns, in
// that order, always shown; any other task a card or question names follows.
const TASK_ORDER = ["data", "deep-learning", "decoding", "evaluation", "qc"];
const ALWAYS_TASKS = ["qc"];
function alwaysTasks() { return plan.columns.length ? plan.columns : ALWAYS_TASKS; }
// Display names where a task value cannot carry the words (no spaces allowed).
const TASK_LABEL = {"deep-learning": "deep learning", "error-correction": "error correction", "qc": "QC"};
function taskLabel(task) { return TASK_LABEL[task] || task; }
const NO_TASK = "unassigned";
function shownTasks(tasks) {
  const filter = el("task-filter").value;
  return [...new Set([...tasks, ...alwaysTasks().filter(t => !filter || t === filter)])].sort(compareTasks);
}
function taskOf(card) { return meta(card, "task") || NO_TASK; }
function taskRank(task) {
  const order = plan.columns.length ? plan.columns : TASK_ORDER;
  const i = order.indexOf(task);
  return i >= 0 ? [0, i, ""] : task === NO_TASK ? [2, 0, ""] : [1, 0, task];
}
function compareTasks(a, b) {
  const [x, y] = [taskRank(a), taskRank(b)];
  return x[0] - y[0] || x[1] - y[1] || x[2].localeCompare(y[2]);
}

// Card progress for the Tasks view. A recorded verdict closes a card; launched
// jobs or an active research stage mean work has started; anything else is todo.
// Finished jobs alone never make a card done (job completion is not acceptance).
const ACTIVE_STAGES = ["formulating", "probing", "reviewing"];
function progress(card) {
  if (["met", "failed", "inconclusive"].includes(card.verdict)) return "done";
  const phases = (card.jobs || []).map(j => j.phase);
  if (phases.includes("in progress") || phases.length || ACTIVE_STAGES.includes(meta(card, "stage")))
    return "in-progress";
  return "todo";
}
const PROGRESS_LABEL = {"done": "done", "in-progress": "in progress", "todo": "todo"};
const PROGRESS_ORDER = {"in-progress": 0, "todo": 1, "done": 2};

// Tasks view. With questions/ files: one column per question, headed by its
// tile, its cards below in id order; cards serving no question get a last
// column. Without questions: one column per task. Colour is progress(); the
// line under the title says why, so the colour is never the only signal.
function renderTasks(board, matches) {
  if (asked.questions.length) return renderQuestionLanes(board, matches);
  const groups = {};
  for (const card of matches) (groups[taskOf(card)] ||= []).push(card);
  for (const q of visibleQuestions()) groups[q.task || NO_TASK] ||= [];
  for (const task of shownTasks([])) groups[task] ||= [];
  const lanes = document.createElement("div"); lanes.className = "task-lanes";
  for (const task of Object.keys(groups).sort(compareTasks)) {
    const cards = groups[task].sort((a, b) =>
      PROGRESS_ORDER[progress(a)] - PROGRESS_ORDER[progress(b)] ||
      meta(b, "updated").localeCompare(meta(a, "updated")) || a.card.localeCompare(b.card));
    const lane = document.createElement("section"); lane.className = "task-lane";
    const head = document.createElement("h2");
    const counts = {};
    for (const c of cards) counts[progress(c)] = (counts[progress(c)] || 0) + 1;
    head.textContent = taskLabel(task);
    const tally = document.createElement("span"); tally.className = "sub";
    tally.textContent = " " + ["done", "in-progress", "todo"].filter(k => counts[k])
      .map(k => counts[k] + " " + PROGRESS_LABEL[k]).join(" · ");
    head.append(tally); lane.append(head);
    questionTiles(lane, task, matches);
    for (const card of cards) {
      const state = progress(card);
      const tile = document.createElement("button");
      tile.type = "button"; tile.className = "task-card progress-" + state; tile.onclick = () => show(card);
      const name = document.createElement("strong"); name.textContent = title(card);
      const why = document.createElement("div"); why.className = "sub";
      const jobs = card.jobs || [];
      why.textContent = [PROGRESS_LABEL[state] + (card.verdict && state === "done" ? " · " + card.verdict : ""),
        jobs.length ? jobs.length + " job" + (jobs.length === 1 ? "" : "s") +
          (jobs.some(j => j.phase === "in progress") ? " running" : "") : "",
        meta(card, "stage")].filter(Boolean).join(" · ");
      tile.title = [meta(card, "id"), meta(card, "track"), meta(card, "question"), meta(card, "updated")]
        .filter(Boolean).join(" · ");
      tile.append(name, why); attentionLine(tile, card); lane.append(tile);
    }
    lanes.append(lane);
  }
  board.append(lanes);
  if (!matches.length) {
    const p = document.createElement("p"); p.textContent = "No cards match these filters."; board.append(p);
  }
}

function cardTile(parent, card) {
  const state = progress(card);
  const tile = document.createElement("button");
  tile.type = "button"; tile.className = "task-card progress-" + state; tile.onclick = () => show(card);
  const name = document.createElement("strong"); name.textContent = title(card);
  const why = document.createElement("div"); why.className = "sub";
  const jobs = card.jobs || [];
  why.textContent = [(meta(card, "id") || "").replace(/^[A-Z0-9]+-(?=[A-Z]+-\d)/, ""),
    PROGRESS_LABEL[state] + (card.verdict && state === "done" ? " · " + card.verdict : ""),
    jobs.length ? jobs.length + " job" + (jobs.length === 1 ? "" : "s") +
      (jobs.some(j => j.phase === "in progress") ? " running" : "") : "",
    taskLabel(taskOf(card))].filter(Boolean).join(" · ");
  tile.title = [meta(card, "id"), meta(card, "question"), meta(card, "updated")].filter(Boolean).join(" · ");
  tile.append(name, why); chip(tile, card.owner || "—"); attentionLine(tile, card); parent.append(tile);
}
const byId = (a, b) => (meta(a, "id") || a.card).localeCompare(meta(b, "id") || b.card, undefined, {numeric: true});
function renderQuestionLanes(board, matches) {
  const lanes = document.createElement("div"); lanes.className = "task-lanes";
  const keys = new Set(asked.questions.map(q => q.key));
  const lane = (head, cards) => {
    const section = document.createElement("section"); section.className = "task-lane";
    section.append(head);
    for (const card of [...cards].sort(byId)) cardTile(section, card);
    if (!cards.length) { const p = document.createElement("p"); p.className = "sub"; p.textContent = "no card yet"; section.append(p); }
    lanes.append(section);
  };
  for (const q of [...visibleQuestions()].sort((a, b) => a.key.localeCompare(b.key, undefined, {numeric: true}))) {
    const head = document.createElement("div");
    questionTiles(head, null, [], [q]);
    head.querySelector(".cell-cards").remove();
    lane(head, questionCards(q, matches));
  }
  const loose = matches.filter(c => !listOf(c, "question").some(k => keys.has(k)));
  if (loose.length) { const h = document.createElement("h2"); h.textContent = "no question"; lane(h, loose); }
  board.append(lanes);
  if (!matches.length) {
    const p = document.createElement("p"); p.textContent = "No cards match these filters."; board.append(p);
  }
}

// Questions: projects/<p>/questions/*.md, one per problem, filed under a task.
// A card serves one with `question: Q-NNN` (the file name's first part). The
// tile's colour is the question's own status; its line counts the cards'
// progress. Clicking it filters the board to that question's cards.
const QUESTION_STATE = {open: "in-progress", answered: "done", parked: "planned"};
function questionCards(q, cards) { return cards.filter(c => listOf(c, "question").includes(q.key)); }
function visibleQuestions() {
  const task = el("task-filter").value;
  return asked.questions.filter(q => (!task || (q.task || NO_TASK) === task) && questionShown(q));
}
function questionTiles(lane, task, matches, list) {
  for (const q of list || visibleQuestions().filter(q => (q.task || NO_TASK) === task)) {
    const tile = document.createElement("div");
    tile.className = "task-card question-tile progress-" + QUESTION_STATE[q.status];
    const name = document.createElement("button"); name.type = "button"; name.className = "question-name";
    name.textContent = q.key + " · " + q.title;
    name.title = "show this question";
    name.onclick = () => showQuestion(q);
    const badge = document.createElement("span"); badge.className = "track-status"; badge.textContent = q.status;
    const why = document.createElement("div"); why.className = "sub";
    const cards = questionCards(q, matches);
    why.textContent = [q.milestone && "blocks " + q.milestone, q.updated && "updated " + q.updated].filter(Boolean).join(" · ");
    tile.title = q.conclusion || q.question;
    tile.append(name, " ", badge, why); if (q.rung) chip(tile, q.rung); cardLinks(tile, cards); lane.append(tile);
  }
}
function showQuestion(q) {
  selected = null;
  el("q-title").textContent = q.key + " · " + q.title;
  el("q-path").textContent = q.file + " · " + q.status + (q.updated ? " · updated " + q.updated : "");
  el("q-body").replaceChildren();
  for (const key of ["rung", "eval_data", "metric", "train_data", "owner"]) if (q[key]) { const p = document.createElement("p"); p.textContent = key + ": " + q[key]; el("q-body").append(p); }
  el("q-body").append(renderMarkdown(q.body));
  el("q-filter").onclick = () => {
    hidden.questions = asked.questions.map(x => x.key).filter(k => k !== q.key);
    saveHidden(); buildShowPanel(); el("question").close(); render();
  };
  if (!el("question").open) el("question").showModal();
}

// Milestones: outputs the project must deliver, declared in the rdash-tracks
// block. Each names the runs that deliver it and, optionally, which tasks of
// those runs count. Progress is derived from the cards in those run cells or,
// for a milestone that names no runs, from the cards serving its questions;
// the authored status stays a separate badge.
function milestoneCells(m, cards) {
  const taskOfTrack = Object.fromEntries(plan.tracks.map(t => [t.name, t.task]));
  const cells = [];
  for (const run of plan.runs.filter(r => m.runs.includes(r.name))) {
    for (const [task, step] of Object.entries(run.path)) {
      if (m.tasks.length && !m.tasks.includes(task)) continue;
      const inCell = cards.filter(c => inRun(c, run, task, taskOfTrack));
      cells.push({run: run.name, task, step, cards: inCell, state: cellState(inCell)});
    }
  }
  if (!plan.runs.some(r => m.runs.includes(r.name)))
    for (const q of asked.questions.filter(q => q.milestone === m.id))
      for (const card of questionCards(q, cards))
        cells.push({run: q.key, task: taskOf(card), step: meta(card, "id") || card.card, cards: [card], state: progress(card)});
  return cells;
}
function renderMilestones(board, cards) {
  if (!plan.milestones.length) return;
  const strip = document.createElement("div"); strip.className = "milestones";
  for (const m of plan.milestones.filter(m => milestoneShown(m.id))) {
    const cells = milestoneCells(m, cards);
    const done = cells.filter(c => c.state === "done").length;
    const state = m.status === "done" ? "done" : m.status === "dropped" || m.status === "planned" && !done
      ? "planned" : cells.length && done === cells.length ? "done" : "in-progress";
    const tile = document.createElement("div");
    tile.className = "milestone progress-" + state + (m.status === "dropped" ? " dropped" : "");
    const name = document.createElement("strong"); name.textContent = m.id + " · " + (m.name || m.output);
    const badge = document.createElement("span"); badge.className = "track-status"; badge.textContent = m.status;
    name.append(" ", badge);
    const why = document.createElement("div"); why.className = "sub";
    const blocking = [...new Set(cells.filter(c => c.state !== "done").map(c => c.step))];
    const open = asked.questions.filter(q => q.milestone === m.id && q.status === "open").map(q => q.key);
    why.textContent = [m.name && m.output, cells.length ? done + "/" + cells.length + (m.runs.length ? " run steps" : " cards") + " done" : "no runs or cards",
      blocking.length ? "waiting on " + blocking.slice(0, 4).join(", ") + (blocking.length > 4 ? "…" : "") : "",
      open.length ? "open " + open.join(", ") : "", m.check && "check: " + m.check].filter(Boolean).join(" · ");
    tile.title = m.runs.join("\n");
    tile.append(name, why); strip.append(tile);
  }
  board.append(strip);
}

// Milestones view: one row per milestone (an approach, delivered by one or
// more runs), one column per task. A cell holds the questions filed under that
// task and milestone, then the tracks that belong to that milestone (track
// `milestone` in the spec), coloured by their cards. Questions without a milestone
// and tracks without one get their own row, so none disappears from the matrix.
function renderMilestoneMatrix(board, matches) {
  if (!el("project").value) return;
  const tasks = shownTasks([...plan.tasks, ...visibleQuestions().map(q => q.task || NO_TASK)]);
  const rows = plan.milestones.filter(m => milestoneShown(m.id))
    .map(m => ({m, label: m.id + (m.name ? " · " + m.name : ""), title: m.output}));
  const loose = visibleQuestions().filter(q => !plan.milestones.some(m => m.id === q.milestone));
  const unowned = plan.tracks.some(tr => !plan.milestones.some(m => m.id === tr.milestone));
  if ((loose.length || unowned) && milestoneShown(NO_MILESTONE)) rows.push({m: null, label: "—", title: "no milestone"});
  if (!rows.length) {
    const p = document.createElement("p");
    p.textContent = "No milestones in this project's rdash-tracks block and no questions/ files (format: projects/TEMPLATE/spec.md).";
    board.append(p); return;
  }
  const table = document.createElement("table"); table.className = "run-table milestone-table";
  const head = document.createElement("tr");
  for (const label of ["Milestone", ...tasks.map(taskLabel)]) {
    const th = document.createElement("th"); th.scope = "col"; th.textContent = label; head.append(th);
  }
  const thead = document.createElement("thead"); thead.append(head); table.append(thead);
  const body = document.createElement("tbody");
  const taskOfTrack = Object.fromEntries(plan.tracks.map(t => [t.name, t.task]));
  for (const row of rows) {
    const tr = document.createElement("tr"); if (row.m && row.m.status === "dropped") tr.className = "dropped";
    const th = document.createElement("th"); th.scope = "row";
    const name = document.createElement("strong"); name.textContent = row.label;
    const what = document.createElement("div"); what.className = "sub"; what.textContent = row.title;
    th.append(name, what);
    if (row.m) { const badge = document.createElement("span"); badge.className = "track-status"; badge.textContent = row.m.status; name.append(" ", badge); }
    tr.append(th);
    for (const task of tasks) {
      const td = document.createElement("td"); td.dataset.label = taskLabel(task); td.className = "matrix-cell";
      const qs = (row.m ? visibleQuestions().filter(q => q.milestone === row.m.id) : loose)
        .filter(q => (q.task || NO_TASK) === task);
      questionTiles(td, task, matches, qs);
      // A track sits in the row of the milestone it belongs to (`milestone` in
      // the spec), or in the no-milestone row; never in several rows.
      const owned = plan.tracks.filter(tr => tr.task === task &&
        (row.m ? tr.milestone === row.m.id : !plan.milestones.some(m => m.id === tr.milestone)));
      for (const track of owned) {
        const cards = matches.filter(c => taskOf(c) === task && listOf(c, "track").includes(track.name));
        const tile = document.createElement("div");
        tile.className = "task-card track-tile progress-" + cellState(cards) + (track.status === "dropped" ? " dropped" : "");
        const label = document.createElement("strong"); label.textContent = track.name;
        const badge = document.createElement("span"); badge.className = "track-status"; badge.textContent = track.status;
        label.append(" ", badge);
        const why = document.createElement("div"); why.className = "sub"; why.textContent = cellTally(cards);
        tile.title = track.desc || "";
        tile.append(label, why); cardLinks(tile, cards); td.append(tile);
      }
      if (!td.children.length) td.textContent = "—";
      tr.append(td);
    }
    body.append(tr);
  }
  table.append(body); board.append(table);
}

// Tracks: a track is one planned approach within a task, declared in spec.md
// `## TRACKS`; a run is one track per task on one cube. Cards say which tracks
// they serve (`track: a, b`) and, optionally, which cubes (`cube:`); a card with
// no cube serves every cube. Cell colour comes from the cards' progress(); a
// track with no card yet is grey (planned).
function cubeOk(card, cube) { const cubes = listOf(card, "cube"); return !cube || !cubes.length || cubes.includes(cube); }
function cellState(cards) {
  if (!cards.length) return "planned";
  const states = cards.map(progress);
  if (states.every(s => s === "done")) return "done";
  if (states.some(s => s !== "todo")) return "in-progress";
  return "todo";
}
function cellTally(cards) {
  const counts = {};
  for (const c of cards) counts[progress(c)] = (counts[progress(c)] || 0) + 1;
  return ["done", "in-progress", "todo"].filter(k => counts[k]).map(k => counts[k] + " " + PROGRESS_LABEL[k]).join(" · ")
    || "no card yet";
}
// A card belongs in a run's cell when its task is that cell's task, it serves
// the run's cube, it names at least one track on the run's path, and wherever
// it names tracks of a task the run also covers, the run's track is among them.
function inRun(card, run, task, taskOfTrack) {
  if (taskOf(card) !== task || !cubeOk(card, run.cube)) return false;
  const names = listOf(card, "track").filter(t => taskOfTrack[t]);
  const path = Object.values(run.path);
  if (!names.some(t => path.includes(t))) return false;
  return Object.entries(run.path).every(([t, step]) => {
    const mine = names.filter(n => taskOfTrack[n] === t);
    return !mine.length || mine.includes(step);
  });
}
function cardLinks(parent, cards) {
  const list = document.createElement("div"); list.className = "cell-cards";
  const id = c => meta(c, "id") || c.card;
  for (const card of [...cards].sort((a, b) => id(a).localeCompare(id(b), undefined, {numeric: true}))) {
    const b = document.createElement("button"); b.type = "button";
    b.className = "cell-card progress-" + progress(card);
    b.textContent = (meta(card, "id") || card.card).replace(/^[A-Z0-9]+-(?=[A-Z]+-\d)/, "");
    b.title = title(card) + " · " + PROGRESS_LABEL[progress(card)];
    b.onclick = event => { event.stopPropagation(); show(card); };
    list.append(b);
  }
  parent.append(list);
}
// Batches view: a project that runs a fixed pipeline on each incoming volume keeps
// one card per batch (`task: batch`) with a `## Steps` checklist. Newest batch
// first and open; older ones collapse to one line. A step's colour comes from its
// checkbox (the person's or agent's sign-off) and, until it is ticked, from the
// live state of the jobs launched for it; a finished job alone never ticks it.
const isBatch = card => taskOf(card) === "batch";
// Batch and volume filters. A card names its batch with `batch:` and the data
// volume(s) it touches with `volume:` (`cube:` read the same); a card without one
// is project-wide and shows under every batch or volume. A batch card lists its
// volumes with `volumes:`.
const batchName = card => meta(card, "batch") || (isBatch(card) ? meta(card, "title") : "");
const volumesOf = card => [...listOf(card, "volume"), ...listOf(card, "cube")];
function batchOk(card) {
  const b = el("batch-filter").value;
  return !b || !batchName(card) || batchName(card) === b;
}
function volumeOk(card) {
  const v = el("volume-filter").value, own = isBatch(card) ? listOf(card, "volumes") : volumesOf(card);
  return !v || !own.length || own.includes(v);
}
const batchDate = card => meta(card, "batch_date") || meta(card, "created");
function stepState(card, step) {
  if (step.checked) return "done";
  const ids = (card.step_jobs || {})[step.key] || [];
  const buckets = (card.jobs || []).filter(j => ids.includes(j.id))
    .map(j => JOB_BUCKET[String(j.state).toUpperCase()] || "unknown");
  if (buckets.some(b => b === "run" || b === "wait")) return "in-progress";
  if (buckets.length && buckets[buckets.length - 1] === "bad") return "failed";
  return "todo";
}
const STEP_LABEL = {"done": "done", "in-progress": "running", "failed": "job failed", "todo": "todo"};
function batchTally(card) {
  const steps = card.steps || [];
  return steps.filter(s => s.checked).length + "/" + steps.length + " steps";
}
function renderBatches(board, cards) {
  const batches = cards.filter(c => isBatch(c) && batchOk(c)).sort((a, b) =>
    batchDate(b).localeCompare(batchDate(a)) || b.card.localeCompare(a.card));
  if (!batches.length) {
    const p = document.createElement("p");
    p.textContent = "No batch cards. A batch card has `task: batch` and a `## Steps` checklist.";
    board.append(p); return;
  }
  const list = document.createElement("div"); list.className = "batches";
  batches.forEach((card, index) => {
    const box = document.createElement("details"); box.className = "batch";
    box.open = index === 0;
    const head = document.createElement("summary");
    const name = document.createElement("strong"); name.textContent = title(card);
    const sub = document.createElement("span"); sub.className = "sub";
    const steps = card.steps || [];
    const next = steps.find(s => !s.checked);
    sub.textContent = " " + [batchDate(card), batchTally(card),
      next ? "next: " + (next.key || next.text) : (steps.length ? "complete" : "")].filter(Boolean).join(" · ");
    const open = document.createElement("button"); open.type = "button"; open.className = "link";
    open.textContent = "card"; open.onclick = event => { event.preventDefault(); show(card); };
    head.append(name, sub, " ", open); box.append(head);
    if (card.summary) {
      const p = document.createElement("div"); p.className = "batch-summary";
      inlineInto(p, card.summary); box.append(p);
    }
    const ol = document.createElement("ol"); ol.className = "batch-steps";
    for (const step of steps) {
      const state = stepState(card, step);
      const li = document.createElement("li"); li.className = "batch-step progress-" + state;
      const key = document.createElement("strong"); key.textContent = (step.checked ? "✓ " : "☐ ") + (step.key || "");
      const text = document.createElement("span"); inlineInto(text, " " + step.text);
      const why = document.createElement("span"); why.className = "sub";
      const ids = (card.step_jobs || {})[step.key] || [];
      why.textContent = " · " + STEP_LABEL[state] + (ids.length ? " · job " + ids[ids.length - 1] : "");
      li.append(key, text, why); ol.append(li);
    }
    box.append(ol); list.append(box);
  });
  board.append(list);
}

// Runs view: what was submitted, from receipts rather than cards. Recorded runs
// are this project's receipts (newest first); unrecorded are recent jobs on the
// hosts that no receipt or card names -- prototypes are fine, they are listed so
// one that matters can be attached (`hub.sh attach`). Fetched only for this view.
let runs = {project: null, data: null, error: ""};
function runCell(tr, value, className) {
  const td = document.createElement("td"); td.textContent = value === undefined || value === null || value === "" ? "—" : String(value);
  if (className) td.className = className; tr.append(td); return td;
}
function runTable(columns) {
  const table = document.createElement("table"); table.className = "runs-table";
  const head = document.createElement("tr");
  for (const c of columns) { const th = document.createElement("th"); th.textContent = c; head.append(th); }
  const thead = document.createElement("thead"); thead.append(head); table.append(thead);
  const body = document.createElement("tbody"); table.append(body);
  return [table, body];
}
function codeLabel(code) {
  if (!code) return "";
  if (code.error && !code.commit) return code.error;
  return (code.path || "").split("/").pop() + "@" + (code.commit || "").slice(0, 10) + (code.dirty ? " + diff" : "");
}
async function loadRuns(refresh) {
  const project = el("project").value;
  runs = {project, data: null, error: ""};
  try {
    runs.data = await api("/api/runs?project=" + encodeURIComponent(project) + (refresh ? "&refresh=1" : ""));
  } catch (error) { runs.error = error.message; }
  if (view === "runs" && el("project").value === project) render();
}
function renderRuns(board) {
  const project = el("project").value;
  if (runs.project !== project) { loadRuns(false); }
  if (!runs.data) {
    const p = document.createElement("p"); p.textContent = runs.error || "Loading runs…"; board.append(p); return;
  }
  const byCard = Object.fromEntries(records.map(c => [c.card, c]));
  const sync = runs.data.sync;
  const syncLine = document.createElement("p"); syncLine.className = sync && sync.state === "ok" ? "sub" : "error";
  syncLine.textContent = sync ? "Hub sync " + sync.state + " at " + sync.at + ": " + sync.message
                              : "Hub sync has not run on this board (dwos-rdash-sync.timer); receipts are not being collected.";
  board.append(syncLine);
  const h = document.createElement("h2"); h.textContent = "Recorded runs (" + runs.data.recorded.length + ")";
  board.append(h);
  if (runs.data.recorded.length) {
    const [table, body] = runTable(["Submitted", "Job", "State", "Card", "Step", "Via", "Code", "By"]);
    for (const r of runs.data.recorded) {
      const tr = document.createElement("tr");
      runCell(tr, (r.submitted_at || "").replace("T", " ").slice(0, 16));
      runCell(tr, r.host + " " + r.job + (r.job_name ? " · " + r.job_name : ""));
      const bucket = JOB_BUCKET[String(r.state).toUpperCase()] || "unknown";
      const state = runCell(tr, BUCKET_LABEL[bucket]); state.className = "tag job job-" + bucket;
      const cardCell = runCell(tr, r.card ? "" : (r.focus || "project"));
      if (r.card) {
        const card = byCard[r.card];
        const link = document.createElement("button"); link.type = "button"; link.className = "link";
        link.textContent = card ? title(card) : r.card;
        if (card) link.onclick = () => show(card);
        cardCell.replaceChildren(link);
      }
      runCell(tr, r.step);
      runCell(tr, r.via);
      runCell(tr, codeLabel(r.code)).title = r.code ? JSON.stringify(r.code) : "";
      runCell(tr, r.submitted_by);
      body.append(tr);
    }
    board.append(table);
  } else {
    const p = document.createElement("p"); p.className = "sub";
    p.textContent = "No receipts yet. A launch through rsub or fsubmit leaves one beside the run; the hub collects it within a minute.";
    board.append(p);
  }
  const un = runs.data.unrecorded || {jobs: [], hosts: {}};
  const mine = un.jobs.filter(j => j.project === project);
  const other = un.jobs.filter(j => j.project !== project);
  const h2 = document.createElement("h2");
  h2.textContent = "Unrecorded since " + un.since + " (" + mine.length + " here, " + other.length + " not matched to this project)";
  board.append(h2);
  const note = document.createElement("p"); note.className = "sub";
  note.textContent = "Jobs no receipt or card names. Fine for prototypes; to record one: hub.sh attach <host> <job> " + project +
    " [cards/<card>.md]. Hosts: " + Object.entries(un.hosts).map(([k, v]) => k + " " + v).join(", ");
  board.append(note);
  for (const [label, rows, open] of [["Matched to this project", mine, true], ["Other unrecorded jobs", other, false]]) {
    if (!rows.length) continue;
    const box = document.createElement("details"); box.open = open;
    const summary = document.createElement("summary"); summary.textContent = label + " (" + rows.length + ")"; box.append(summary);
    const [table, body] = runTable(["Submitted", "Job", "Name", "Tasks", "States", "Working directory"]);
    for (const j of rows.slice(0, 200)) {
      const tr = document.createElement("tr");
      runCell(tr, (j.submit || "").replace("T", " ").slice(0, 16));
      runCell(tr, j.host + " " + j.job);
      runCell(tr, j.name);
      runCell(tr, j.tasks);
      runCell(tr, Object.entries(j.states).map(([k, v]) => v + " " + k.toLowerCase()).join(", "));
      runCell(tr, j.workdir, "path");
      body.append(tr);
    }
    box.append(table); board.append(box);
  }
}

// Show panel: per-viewer choice of which milestones and questions the Milestones
// and Tasks views draw, plus a switch to hide done cards. Remembered per project
// in this browser only; nothing is written to the cards.
let hidden = {milestones: [], questions: [], doneCards: false};
const NO_MILESTONE = "(none)";
function hideKey() { return "rdash-hide:" + el("project").value; }
function loadHidden() {
  hidden = {milestones: [], questions: [], doneCards: false};
  try { Object.assign(hidden, JSON.parse(localStorage.getItem(hideKey()) || "{}")); } catch (_) {}
}
function saveHidden() { try { localStorage.setItem(hideKey(), JSON.stringify(hidden)); } catch (_) {} }
const milestoneShown = id => !hidden.milestones.includes(id || NO_MILESTONE);
const questionShown = q => !hidden.questions.includes(q.key) && milestoneShown(
  plan.milestones.some(m => m.id === q.milestone) ? q.milestone : NO_MILESTONE);
function buildShowPanel() {
  const box = el("show-options"); box.replaceChildren();
  const group = (label, items, list) => {
    if (!items.length) return;
    const fs = document.createElement("fieldset"); const lg = document.createElement("legend");
    lg.textContent = label; fs.append(lg);
    for (const [key, text] of [["*all", "all"], ["*none", "none"]]) {
      const b = document.createElement("button"); b.type = "button"; b.className = "link"; b.textContent = text;
      b.onclick = () => { hidden[list] = key === "*all" ? [] : items.map(i => i[0]); saveHidden(); buildShowPanel(); render(); };
      lg.append(" ", b);
    }
    for (const [key, text] of items) {
      const row = document.createElement("label"); const cb = document.createElement("input");
      cb.type = "checkbox"; cb.checked = !hidden[list].includes(key);
      cb.onchange = () => {
        hidden[list] = cb.checked ? hidden[list].filter(k => k !== key) : [...hidden[list], key];
        saveHidden(); updateShowCount(); render();
      };
      row.append(cb, " " + text); fs.append(row);
    }
    box.append(fs);
  };
  const ms = plan.milestones.map(m => [m.id, m.id + (m.name ? " · " + m.name : "")]);
  if (asked.questions.some(q => !plan.milestones.some(m => m.id === q.milestone))) ms.push([NO_MILESTONE, "no milestone"]);
  group("Milestones", ms, "milestones");
  group("Questions", [...asked.questions].sort((a, b) => a.key.localeCompare(b.key, undefined, {numeric: true}))
    .map(q => [q.key, q.key + " · " + q.title + (q.status !== "open" ? " (" + q.status + ")" : "")]), "questions");
  const row = document.createElement("label"); const cb = document.createElement("input");
  cb.type = "checkbox"; cb.checked = hidden.doneCards;
  cb.onchange = () => { hidden.doneCards = cb.checked; saveHidden(); updateShowCount(); render(); };
  row.className = "show-done"; row.append(cb, " Hide done cards"); box.append(row);
  updateShowCount();
}
function updateShowCount() {
  const n = hidden.milestones.length + hidden.questions.length + (hidden.doneCards ? 1 : 0);
  el("show-label").textContent = n ? "Show (" + n + " hidden)" : "Show";
}

function fillSelect(id, label, values, keep) {
  el(id).replaceChildren();
  const all = document.createElement("option"); all.value = ""; all.textContent = label; el(id).append(all);
  for (const v of values) { const o = document.createElement("option"); o.value = v; o.textContent = v; el(id).append(o); }
  el(id).value = values.includes(keep) ? keep : "";
}
function fillBatchFilters() {
  const batchCards = records.filter(isBatch).sort((a, b) => batchDate(b).localeCompare(batchDate(a)));
  const names = [...new Set([...batchCards.map(batchName), ...records.map(c => meta(c, "batch"))].filter(Boolean))];
  fillSelect("batch-filter", "All batches", names, el("batch-filter").value);
  const chosen = el("batch-filter").value;
  const inBatch = records.filter(c => !chosen || batchName(c) === chosen);
  const volumes = [...new Set(inBatch.flatMap(c => isBatch(c) ? listOf(c, "volumes") : volumesOf(c)))].sort();
  fillSelect("volume-filter", "All volumes", volumes, el("volume-filter").value);
  el("batch-filter").hidden = !names.length;
  el("volume-filter").hidden = !volumes.length;
}


function cardOwnerOk(card) {
  const value = el("card-owner").value;
  return !value || (value === "__none__" ? !card.owner : card.owner === value);
}
function fillCardOwners() {
  let saved = "";
  try { saved = localStorage.getItem("rdash-card-owner:" + el("project").value) || ""; } catch (_) {}
  const select = el("card-owner"); select.replaceChildren();
  for (const [value, label] of [["", "All owners"], ...[...new Set(records.map(c => c.owner).filter(Boolean))].sort().map(x => [x,x]), ["__none__", "(none)"]]) {
    const option = document.createElement("option"); option.value = value; option.textContent = label; select.append(option);
  }
  select.value = [...select.options].some(o => o.value === saved) ? saved : "";
}
function renderLadder(board) {
  if (ladderData.missing) { board.textContent = "LADDER.md is missing."; return; }
  const legend = document.createElement("p"); legend.textContent = "Gates: met ● · open ○ · failed ◉ · target italic · none blank"; board.append(legend);
  let month = "";
  for (const row of ladderData.rows) {
    if (row.month !== month) { month = row.month; const h = document.createElement("h2"); h.textContent = month; h.className = "ladder-month"; if (month === new Date().toISOString().slice(0,7)) h.classList.add("current"); board.append(h); }
    const section = document.createElement("section"); section.className = "ladder-row";
    const head = document.createElement("h3"); head.textContent = [row.rung, row.data, row.status].filter(Boolean).join(" · "); section.append(head);
    for (const key of ["g1", "g2", "g3"]) { const cell = document.createElement("p"); cell.className = "gate gate-" + row[key].state; cell.textContent = key.toUpperCase() + " " + row[key].text; section.append(cell); }
    const bar = document.createElement("div"); bar.className = "gate-bar"; for (const key of ["g1", "g2", "g3"]) { const part = document.createElement("span"); part.className = "segment " + row[key].state; bar.append(part); } section.append(bar);
    const note = document.createElement("p"); note.textContent = row.notebook_question || ""; section.append(note); board.append(section);
  }
}
function renderWeek(board) {
  for (const notebook of focusData.notebooks) {
    const selectedOwner = el("card-owner").value; if (selectedOwner && (selectedOwner === "__none__" ? notebook.owner : selectedOwner !== notebook.owner)) continue;
    const section = document.createElement("section"); const h = document.createElement("h2"); h.textContent = notebook.id + " · " + notebook.title; section.append(h);
    const decision = document.createElement("p"); decision.textContent = "Decision needed: " + (notebook.decision || "—"); section.append(decision);
    const list = document.createElement("ul"); for (const item of notebook.next.filter(i => !i.done)) { const li = document.createElement("li"); li.textContent = item.text; list.append(li); } section.append(list);
    if (!notebook.has_next) { const p = document.createElement("p"); p.textContent = "no Next list"; section.append(p); } board.append(section);
  }
}

let ladderData = {rows: [], gates: [], missing: true};
let focusData = {notebooks: []};
let view = "tasks";
try { const v = localStorage.getItem("rdash-view"); if (v === "milestones" || v === "batches" || v === "runs" || v === "ladder" || v === "week") view = v; } catch (_) {}
function setView(next) {
  view = next;
  try { localStorage.setItem("rdash-view", view); } catch (_) {}
  el("show-panel").hidden = view === "batches" || view === "runs";
  for (const [id, name] of [["view-ladder", "ladder"], ["view-week", "week"], ["view-runs", "runs"], ["view-batches", "batches"], ["view-milestones", "milestones"], ["view-tasks", "tasks"]])
    el(id).setAttribute("aria-pressed", String(view === name));
  render();
}

function render() {
  const board = el("board");
  board.replaceChildren();
  if (view === "ladder") { renderLadder(board); return; }
  if (view === "week") { renderWeek(board); return; }
  // Rows waiting on the researcher sort first; `unknown` owns as "you", never
  // as closed, so unreachable state cannot hide at the bottom of the board.
  const owner = c => (c.attention || {}).owner || "you";
  const hiddenQ = new Set(asked.questions.filter(q => !questionShown(q)).map(q => q.key));
  const matches = records.filter(c => !c.read_only && !isBatch(c) &&
    !(hidden.doneCards && progress(c) === "done") &&
    !(listOf(c, "question").length && listOf(c, "question").every(k => hiddenQ.has(k))) &&
    cardOwnerOk(c) && batchOk(c) && volumeOk(c) &&
    (!el("task-filter").value || taskOf(c) === el("task-filter").value) &&
    (!el("stage-filter").value || meta(c, "stage") === el("stage-filter").value) &&
    (!el("owner").value || owner(c) === el("owner").value));
  matches.sort((a, b) => (OWNER_ORDER[owner(a)] ?? 0) - (OWNER_ORDER[owner(b)] ?? 0) ||
    meta(b, "updated").localeCompare(meta(a, "updated")) || a.card.localeCompare(b.card));
  const problems = asked.errors;
  if (problems.length) {
    const box = document.createElement("div"); box.className = "track-errors";
    for (const text of problems) { const p = document.createElement("p"); p.textContent = text; box.append(p); }
    board.append(box);
  }
  if (view === "runs") renderRuns(board);
  else if (view === "batches") renderBatches(board, records.filter(c => !c.read_only && cardOwnerOk(c)));
  else {
    if (view !== "milestones") renderMilestones(board, records.filter(c => !c.read_only && !isBatch(c) && cardOwnerOk(c)));
    if (view === "milestones") renderMilestoneMatrix(board, matches);
    else renderTasks(board, matches);
  }
  const orphans = records.filter(c => c.read_only);
  if (orphans.length) {
    const section = document.createElement("section"); section.className = "unreadable";
    const h = document.createElement("h2"); h.textContent = "Unreadable (" + orphans.length + ")";
    section.append(h);
    for (const card of orphans) {
      const button = document.createElement("button"); button.className = "card readonly";
      button.textContent = title(card) + " · " + (card.reason || card.error);
      button.onclick = () => show(card); section.append(button);
    }
    board.append(section);
  }
}

function showSummary(card) {
  const container = el("summaries"); container.replaceChildren();
  const strip = document.createElement("section");
  const counts = {};
  for (const artifact of card.artifacts || []) counts[artifact.state] = (counts[artifact.state] || 0) + 1;
  chip(strip, Object.entries(counts).map(([state, n]) => n + " " + state).join(" / ") || "No artifacts declared");
  evaluationCell(strip, card);
  sessionLine(strip, card);
  attentionLine(strip, card);
  container.append(strip);
  if (card.goal) goalPanel(container, card.goal);
  const list = el("acceptance-items"); list.replaceChildren();
  for (const item of (card.acceptance || {}).items || []) {
    const label = document.createElement("label");
    const checkbox = document.createElement("input"); checkbox.type = "checkbox";
    checkbox.checked = item.checked; checkbox.disabled = true;
    label.append(checkbox, document.createTextNode(item.text +
      (item.references.length ? " — evidence: " + item.references.join(", ") : "")));
    list.append(label);
  }
}

function goalPanel(parent, goal) {
  const panel = document.createElement("section"); panel.className = "goal-panel";
  parent.append(panel);
  const heading = document.createElement("h3");
  heading.textContent = "Goal · " + (goal.id || "conflicting goals"); panel.append(heading);
  const line = (label, value) => {
    const p = document.createElement("p");
    p.textContent = label + ": " + (value === null || value === undefined ? "unknown" : String(value));
    panel.append(p);
  };
  if (goal.goal_ids) {
    line("Multiple goals reference this card", goal.goal_ids.join(", "));
    line("Resolve the card binding", "Inspect each goal below; correct the authored goal.json card references.");
    for (const item of goal.goals) goalPanel(panel, item);
    return;
  }
  line("Phase", goal.phase);
  if (goal.projection_error) line("Projection error", goal.projection_error);
  const budget = goal.budget || {};
  const balance = (used, held, limit) => [used, held, limit].every(Number.isFinite)
    ? String(Number((limit - used - held).toFixed(3))) : "unknown";
  line("CPU-hours", "consumed " + (goal.consumed_cpu_hours ?? "unknown") +
    " · held " + (goal.held_cpu_hours ?? "unknown") + " · unsettled (included in held) " +
    (goal.unsettled_cpu_hours ?? "unknown") + " · remaining " +
    balance(goal.consumed_cpu_hours, goal.held_cpu_hours, budget.cpu_hours) + " / " + (budget.cpu_hours ?? "unknown"));
  line("Jobs", "consumed " + (goal.consumed_jobs ?? "unknown") + " · held " + (goal.held_jobs ?? "unknown") +
    " · remaining " + balance(goal.consumed_jobs, goal.held_jobs, budget.jobs) + " / " + (budget.jobs ?? "unknown"));
  line("Coordinator runs", (goal.coordinator_runs_used ?? "unknown") + " / " + (budget.coordinator_runs ?? "unknown"));
  line("Assignment in flight", Array.isArray(goal.assignment_in_flight)
    ? goal.assignment_in_flight.join(", ") || "none" : "unknown");
  line("Event permitting continuation", goal.next_event || "not recorded");
  line("Coordinator rationale", goal.rationale || "not recorded");
  const status = document.createElement("p"); status.setAttribute("role", "status");
  const refresh = document.createElement("button"); refresh.type = "button"; refresh.textContent = "Refresh goal";
  refresh.onclick = async () => {
    refresh.disabled = true;
    try {
      const current = await api("/api/goal?project=" + encodeURIComponent(goal.project) + "&goal=" + encodeURIComponent(goal.id));
      const holder = document.createElement("div"); goalPanel(holder, current);
      panel.replaceWith(holder.firstChild);
    } catch (error) { status.textContent = error.message; status.className = "error"; }
    finally { refresh.disabled = false; }
  };
  const send = async (button, kind, payload = {}) => {
    button.disabled = true; status.className = "";
    try {
      const result = await api("/api/goal/command", {project: goal.project, goal: goal.id,
        goal_revision: goal.goal_revision, kind, payload});
      status.textContent = "Command " + result.id + " queued; refresh to observe the supervisor's result.";
    } catch (error) {
      status.textContent = error.message + " Refresh the goal before retrying."; status.className = "error";
      button.disabled = false;
    }
  };
  const pending = goal.pending_decisions || [];
  line("Pending decisions", goal.phase === "unknown" ? "unknown" : pending.length);
  for (const decision of pending) {
    const form = document.createElement("form"); form.className = "goal-decision";
    const label = document.createElement("label");
    label.append(document.createTextNode(decision.question + " (" + decision.id + ")"));
    const select = document.createElement("select"); label.append(select); form.append(label);
    const parameter = ((goal.assignments || {})[decision.assignment]?.parameters || {})[decision.parameter];
    const ambiguous = decision.reason === "ambiguous_submission";
    const values = ambiguous ? ["adopt", "confirm_not_submitted", "abandon"] :
      parameter?.authorization === "human_decision" ? parameter.allowed_values || [] : [];
    const placeholder = document.createElement("option"); placeholder.value = "";
    placeholder.textContent = "Choose a resolution"; select.append(placeholder); select.required = true;
    values.forEach((value, i) => {
      const option = document.createElement("option"); option.value = String(i);
      option.textContent = JSON.stringify(value); select.append(option);
    });
    const jobLabel = document.createElement("label"); jobLabel.textContent = "Job ID to adopt";
    const jobId = document.createElement("input"); jobId.pattern = "[1-9][0-9]*"; jobLabel.append(jobId);
    jobLabel.hidden = true;
    select.onchange = () => {
      jobLabel.hidden = !ambiguous || values[Number(select.value)] !== "adopt" || select.value === "";
      jobId.required = !jobLabel.hidden;
    };
    if (ambiguous) form.append(jobLabel);
    const recommendation = document.createElement("p");
    recommendation.textContent = "Recommendation: " + (decision.recommendation === null || decision.recommendation === undefined
      ? "not recorded" : JSON.stringify(decision.recommendation)); form.append(recommendation);
    for (const [name, value] of [["Alternatives", decision.alternatives], ["Evidence", decision.evidence],
      ["Expected cost", decision.expected_cost]]) {
      const detail = document.createElement("div"); detail.className = "decision-context";
      const heading = document.createElement("strong"); heading.textContent = name; detail.append(heading);
      const empty = value === null || value === undefined || value === "" ||
        (typeof value === "object" && Object.keys(value).length === 0);
      const content = document.createElement(empty || typeof value === "string" ? "p" : "pre");
      content.textContent = empty ? "Not recorded" : typeof value === "string" ? value : JSON.stringify(value, null, 2);
      detail.append(content); form.append(detail);
    }
    const button = document.createElement("button"); button.type = "submit"; button.textContent = "Resolve decision";
    button.disabled = !values.length || !goal.goal_revision;
    form.onsubmit = event => {
      event.preventDefault();
      if (select.value === "" || button.disabled) return;
      const choice = values[Number(select.value)];
      const value = ambiguous ? (choice === "adopt" ? {action: choice, job_id: jobId.value} : {action: choice}) : choice;
      send(button, "resolve_decision", {decision_id: decision.id, value});
    };
    form.append(button);
    if (!values.length) {
      const note = document.createElement("p"); note.textContent = "This decision requires operator reconciliation."; form.append(note);
    }
    panel.append(form);
  }
  if (goal.goal_revision && ["running", "waiting", "paused"].includes(goal.phase)) {
    const button = document.createElement("button"); button.type = "button";
    const kind = goal.phase === "paused" ? "resume" : "pause";
    button.textContent = kind === "pause" ? "Pause dispatch" : "Resume dispatch";
    button.onclick = () => send(button, kind); panel.append(button);
  }
  for (const command of goal.commands || []) {
    line("Command " + command.id, command.kind + " · " + command.state + (command.reason ? " · " + command.reason : ""));
  }
  panel.append(refresh, status);
}

function evidencePanel(parent, card, project, onSaved) {
  const panel = document.createElement("section"); panel.className = "evidence-panel";
  const heading = document.createElement("h3"); heading.textContent = "Inspect evidence";
  const intro = document.createElement("p"); intro.className = "sub";
  intro.textContent = "Choose declared artifacts to inspect side by side. Check their dataset, sample and run before comparing them.";
  const status = document.createElement("p"); status.setAttribute("role", "status");
  const refresh = document.createElement("button"); refresh.type = "button"; refresh.textContent = "Refresh card";
  refresh.onclick = async () => {
    refresh.disabled = true;
    try {
      const current = await api("/api/card?project=" + encodeURIComponent(project) + "&card=" + encodeURIComponent(card.card));
      onSaved(current, "Card refreshed. Inspect an artifact to attach feedback to its current content.");
    } catch (error) { status.textContent = "Card refresh failed: " + error.message; status.className = "error"; }
    finally { refresh.disabled = false; }
  };
  panel.append(heading, intro, refresh, status); parent.append(panel);
  const artifacts = card.artifacts || [];
  if (!artifacts.length) {
    const empty = document.createElement("p"); empty.textContent = "No artifacts are declared on this card.";
    panel.append(empty); return;
  }
  const grid = document.createElement("div"); grid.className = "evidence-grid"; panel.append(grid);
  for (let slot = 0; slot < Math.min(2, artifacts.length); slot += 1) {
    let request = 0;
    let inspected = null;
    const area = document.createElement("section"); area.className = "evidence-slot"; grid.append(area);
    const label = document.createElement("label"); label.textContent = slot ? "Artifact B (optional)" : "Artifact A";
    const select = document.createElement("select"); label.append(select);
    const placeholder = document.createElement("option"); placeholder.value = "";
    placeholder.textContent = "Choose a declared artifact"; select.append(placeholder);
    for (const artifact of artifacts) {
      const option = document.createElement("option"); option.value = artifact.label;
      option.textContent = artifact.label + " · " + (artifact.state || "state unknown"); select.append(option);
    }
    const inspect = document.createElement("button"); inspect.type = "button"; inspect.textContent = "Inspect artifact";
    inspect.disabled = true;
    const message = document.createElement("p"); message.className = "sub"; message.setAttribute("role", "status");
    message.textContent = "Select an artifact to load its current content.";
    const preview = document.createElement("div"); preview.className = "evidence-preview";
    const provenance = document.createElement("p"); provenance.className = "evidence-provenance";
    const form = document.createElement("form"); form.className = "evidence-feedback";
    const feedbackLabel = document.createElement("label"); feedbackLabel.textContent = "Feedback on this artifact";
    const feedback = document.createElement("input"); feedback.type = "text"; feedback.maxLength = 1000;
    feedback.placeholder = "What do you observe, or what should we check next?";
    feedback.disabled = true; feedback.required = true; feedbackLabel.append(feedback);
    const save = document.createElement("button"); save.type = "submit"; save.textContent = "Save evidence feedback"; save.disabled = true;
    form.append(feedbackLabel, save); area.append(label, inspect, message, preview, provenance, form);
    const clearReceipt = () => { inspected = null; feedback.disabled = true; save.disabled = true; };
    const fail = error => {
      clearReceipt(); message.className = "error";
      message.textContent = "Evidence unavailable: " + error.message + " Refresh the card and inspect again before saving feedback.";
    };
    const ready = (receipt, token) => {
      if (token !== request) return;
      inspected = receipt;
      feedback.disabled = !!card.read_only;
      save.disabled = !!card.read_only;
      message.className = "sub";
      message.textContent = card.read_only ? "Preview loaded. This card is read-only." :
        "Preview loaded. Feedback will reference this exact content and card revision.";
    };
    select.onchange = () => {
      request += 1; clearReceipt(); preview.replaceChildren(); provenance.textContent = ""; feedback.value = "";
      inspect.disabled = !select.value || !card.revision;
      message.className = "sub"; message.textContent = "Inspect the selected artifact before adding feedback.";
    };
    inspect.onclick = async () => {
      if (!select.value || inspect.disabled) return;
      const token = ++request;
      const selectedLabel = select.value;
      clearReceipt(); inspect.disabled = true; preview.replaceChildren(); provenance.textContent = "";
      message.className = "sub"; message.textContent = "Loading evidence…";
      try {
        const receipt = await api("/api/evidence?project=" + encodeURIComponent(project) +
          "&card=" + encodeURIComponent(card.card) + "&revision=" + encodeURIComponent(card.revision) +
          "&label=" + encodeURIComponent(selectedLabel));
        if (token !== request) return;
        if (receipt.revision !== card.revision || receipt.label !== selectedLabel || !receipt.artifact_revision)
          throw new Error("The preview does not match the requested card and artifact.");
        const observed = typeof receipt.observed_at === "number" ? new Date(receipt.observed_at * 1000).toLocaleString() :
          receipt.observed_at || "unknown";
        provenance.textContent = [receipt.host || "host unknown", receipt.path, receipt.size + " bytes", "Observed " + observed,
          "Artifact revision " + receipt.artifact_revision, "Card revision " + receipt.revision].join(" · ");
        if (receipt.kind === "text" && typeof receipt.text === "string") {
          const pre = document.createElement("pre"); pre.textContent = receipt.text; preview.append(pre); ready(receipt, token);
        } else if (receipt.kind === "image" && /^\/api\/evidence\/content\?/.test(receipt.content_url || "")) {
          const img = document.createElement("img"); img.alt = receipt.label;
          img.onload = () => ready(receipt, token);
          img.onerror = () => { if (token === request) fail(new Error("The image changed or could not be loaded.")); };
          img.src = receipt.content_url; preview.append(img);
          message.textContent = "Loading the revision-checked image…";
        } else throw new Error("This artifact has no supported preview.");
      } catch (error) { if (token === request) fail(error); }
      finally { if (token === request) inspect.disabled = !select.value; }
    };
    form.onsubmit = async event => {
      event.preventDefault();
      const text = feedback.value.trim();
      if (!inspected || save.disabled || !text) return;
      const receipt = inspected;
      save.disabled = true; feedback.disabled = true; select.disabled = true; inspect.disabled = true;
      message.className = "sub"; message.textContent = "Saving feedback to the card discussion…";
      try {
        const current = await api("/api/evidence/feedback", {project, card: card.card, revision: receipt.revision,
          label: receipt.label, artifact_revision: receipt.artifact_revision, text});
        clearReceipt(); feedback.value = "";
        message.textContent = "Feedback saved to Ideas and discussion. Inspect again before adding more feedback.";
        onSaved(current, "Evidence feedback saved to Ideas and discussion. Next: review the note with this card's research question.");
      } catch (error) { fail(error); }
      finally { select.disabled = false; inspect.disabled = !select.value; }
    };
  }
}

function show(card) {
  selected = card;
  el("title").textContent = title(card);
  el("path").textContent = card.card + " · owner: " + (card.owner || "—");
  el("readonly").textContent = card.read_only ? (card.error + ": " + card.reason) : "";
  const jobsEl = el("jobs");
  jobsEl.replaceChildren();
  for (const job of card.jobs || []) {
    const bucket = JOB_BUCKET[String(job.state).toUpperCase()] || "unknown";
    const tag = document.createElement("span");
    tag.className = "tag job job-" + bucket;
    // The dialog has room for the id the row omits.
    tag.textContent = [job.name, job.id, jobPhase(job), jobWhen(job), job.stale && "last known", job.reason].filter(Boolean).join(" · ");
    jobsEl.append(tag);
  }
  for (const r of card.receipts || []) {
    const line = document.createElement("span"); line.className = "tag receipt";
    line.textContent = ["receipt", r.host + " " + r.job, r.step, r.via, (r.submitted_at || "").slice(0, 16).replace("T", " "),
                        codeLabel(r.code), r.research && "scripts " + (r.research.revision || "")].filter(Boolean).join(" · ");
    line.title = JSON.stringify(r, null, 1);
    jobsEl.append(line);
  }
  jobsEl.hidden = !(card.jobs || []).length && !(card.receipts || []).length;
  showSummary(card);
  showBody(card);
  el("stage").value = meta(card, "stage") || "idea";
  el("note").value = "";
  el("save-error").textContent = "";
  el("evidence-save-status").textContent = "";
  el("update").hidden = !!card.read_only;
  if (!el("detail").open) el("detail").showModal();
}

let showRaw = false;

function liveTable(parent, heading, columns, rows) {
  const h = document.createElement("h3"); h.textContent = heading; parent.append(h);
  if (!rows.length) { chip(parent, "Not declared"); return; }
  const table = document.createElement("table");
  const head = document.createElement("tr");
  for (const column of columns) { const th = document.createElement("th"); th.textContent = column; head.append(th); }
  table.append(head);
  for (const values of rows) {
    const tr = document.createElement("tr");
    for (const value of values) {
      const td = document.createElement("td"); td.textContent = value === undefined ? "—" : String(value); tr.append(td);
    }
    table.append(tr);
  }
  parent.append(table);
  return table;
}

function snapshotParts(text) {
  const match = /<!-- radd-status:begin -->([\s\S]*?)<!-- radd-status:end -->/.exec(text);
  if (!match) return {text, snapshot: null};
  return {text: text.slice(0, match.index) + text.slice(match.index + match[0].length), snapshot: match[1]};
}

function snapshotLabel(snapshot) {
  const match = /Generated (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) UTC/.exec(snapshot);
  const generated = match ? Date.parse(match[1] + "T" + match[2] + ":00Z") : NaN;
  return "Generated handoff snapshot · " + (Number.isFinite(generated)
    ? Math.max(0, Math.floor((Date.now() - generated) / 60000)) + " minutes old" : "generation age unknown");
}

function showBody(card) {
  const body = el("body");
  const acceptancePanel = el("acceptance-panel");
  body.replaceChildren();
  acceptancePanel.hidden = showRaw;
  if (showRaw) {
    body.className = "raw";
    body.textContent = card.body;
    body.append(acceptancePanel);
  } else {
    body.className = "markdown-content";
    const metrics = card.results || [];
    const table = liveTable(body, "Result vs. contract", ["Name", "Value / state", "Baseline", "Delta", "As of", "Source"],
      metrics.map(r => [r.name, r.state === "present" ? r.value : r.state + (r.reason ? " · " + r.reason : ""),
        r.baseline, r.delta, r.as_of === undefined ? undefined : new Date(r.as_of * 1000).toLocaleString(), r.source]));
    if (table) metrics.forEach((r, i) => {
      if (r.delta !== undefined && r.direction && r.delta !== 0) {
        table.children[i + 1].children[3].className = ((r.delta > 0) === (r.direction === "higher")) ? "delta-favorable" : "delta-unfavorable";
      }
    });
    const project = el("project").value;
    evidencePanel(body, card, project, (current, message) => {
      if (selected !== card || el("project").value !== project) return;
      const draft = el("note").value;
      const draftStage = el("stage").value;
      records = records.map(record => record.card === current.card ? current : record);
      show(current); render(); el("evidence-save-status").textContent = message;
      el("note").value = draft;
      if (draftStage !== (meta(card, "stage") || "idea")) el("stage").value = draftStage;
    });
    const parts = snapshotParts(card.body);
    // Keep authored sections and Markdown intact; move discussion below observations.
    const discussion = /^## Ideas and discussion\s*$/m.exec(parts.text);
    const contractText = discussion ? parts.text.slice(0, discussion.index) : parts.text;
    const h = document.createElement("h3"); h.textContent = "Contract"; body.append(h);
    const findings = document.createElement("div");
    contractCell(findings, card); contractStatus(findings, card); body.append(findings);
    body.append(renderMarkdown(contractText), acceptancePanel);
    liveTable(body, "Live artifacts", ["Name / path", "State", "Size (bytes)", "Modified"],
      (card.artifacts || []).map(a => [a.label + " · " + a.path, a.state + (a.reason ? " · " + a.reason : ""),
        a.size, a.mtime === undefined ? undefined : new Date(a.mtime * 1000).toLocaleString()]));
    if (parts.snapshot !== null) {
      const details = document.createElement("details");
      const summary = document.createElement("summary"); summary.textContent = snapshotLabel(parts.snapshot);
      details.append(summary, renderMarkdown(parts.snapshot)); body.append(details);
    }
    if (discussion) body.append(renderMarkdown(parts.text.slice(discussion.index)));
  }
  el("raw-toggle").textContent = showRaw ? "Rendered" : "Raw";
}

async function refresh(selectRef) {
  const token = ++generation;
  const project = el("project").value;
  el("error").textContent = "";
  records = [];
  if (!project) { el("status").textContent = "Select a project."; render(); return; }
  el("status").textContent = "Loading…";
  const [cards, projects, tracks, questions, focus] = await Promise.all([
    api("/api/cards?project=" + encodeURIComponent(project)),
    api("/api/projects"),
    api("/api/tracks?project=" + encodeURIComponent(project)),
    api("/api/questions?project=" + encodeURIComponent(project)),
    api("/api/focus?project=" + encodeURIComponent(project)),
  ]);
  if (token !== generation) return;
  records = cards;
  plan = tracks;
  asked = questions;
  focusData = focus;
  fillCardOwners();
  loadHidden();
  buildShowPanel();
  const info = projects.find(p => p.id === project);
  el("ignored").textContent = info && info.ignored_paths
    ? info.ignored_paths + " path(s) outside supported card discovery"
    : "";
  el("status").textContent = "";

  fillBatchFilters();

  const tasks = [...new Set([...cards.filter(c => !isBatch(c)).map(taskOf), ...alwaysTasks()])].sort(compareTasks);
  const keepTask = el("task-filter").value;
  el("task-filter").replaceChildren();
  const anyTask = document.createElement("option");
  anyTask.value = ""; anyTask.textContent = "All tasks";
  el("task-filter").append(anyTask);
  for (const t of tasks) {
    const o = document.createElement("option"); o.value = t; o.textContent = taskLabel(t);
    el("task-filter").append(o);
  }
  if (tasks.includes(keepTask)) el("task-filter").value = keepTask;


  if (view === "runs") { runs.project = null; loadRuns(true); }
  render();
  if (selectRef) {
    const found = records.find(c => c.card === selectRef);
    if (found) show(found);
  }
}

el("update").onsubmit = async event => {
  event.preventDefault();
  const button = event.target.querySelector("button");
  button.disabled = true;
  el("save-error").textContent = "";
  try {
    // Stage and note are separate endpoints; the note carries the fresh revision.
    let current = selected;
    const stage = el("stage").value;
    if (stage !== meta(selected, "stage")) {
      current = await api("/api/stage", {project: el("project").value, card: selected.card,
                                         revision: current.revision, stage});
    }
    const note = el("note").value.trim();
    if (note) {
      current = await api("/api/discussion", {project: el("project").value, card: selected.card,
                                              revision: current.revision, text: note});
    }
    el("detail").close();
    await refresh();
  } catch (error) {
    el("save-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
};

el("idea").onsubmit = async event => {
  event.preventDefault();
  const button = event.target.querySelector("button");
  button.disabled = true;
  el("idea-error").textContent = "";
  try {
    const payload = {project: el("project").value, title: el("idea-title").value,
                     track: el("idea-track").value};
    // Optional: omitted rather than sent empty, so the card keeps the template.
    const body = el("idea-body").value.trim();
    if (body) payload.idea = body;
    const result = await api("/api/idea", payload);
    el("compose").close();
    el("idea-title").value = "";
    el("idea-body").value = "";
    await refresh(result.card);
  } catch (error) {
    el("idea-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
};

el("new").onclick = () => {
  if (!el("project").value) { el("error").textContent = "Select a project first."; return; }
  el("idea-error").textContent = "";
  el("compose").showModal();
};
el("raw-toggle").onclick = () => { showRaw = !showRaw; if (selected) showBody(selected); };
el("detail-close").onclick = () => el("detail").close();
el("compose-close").onclick = () => el("compose").close();
el("refresh").onclick = () => refresh(selected && selected.card).catch(e => el("error").textContent = e.message);
el("task-filter").onchange = render;
el("batch-filter").onchange = () => { fillBatchFilters(); render(); };
el("volume-filter").onchange = render;
el("question-close").onclick = () => el("question").close();
el("view-ladder").onclick = () => setView("ladder");
el("view-week").onclick = () => setView("week");
el("card-owner").onchange = () => { try { localStorage.setItem("rdash-card-owner:" + el("project").value, el("card-owner").value); } catch (_) {} render(); };
el("view-tasks").onclick = () => setView("tasks");
el("view-batches").onclick = () => setView("batches");
el("view-milestones").onclick = () => setView("milestones");
el("view-runs").onclick = () => setView("runs");
setView(view);
el("owner").onchange = render;
el("stage-filter").onchange = render;

el("project").onchange = () => {
  try { localStorage.setItem("rdash-project", el("project").value); } catch (_) {}
  refresh().catch(e => el("error").textContent = e.message);
};

(async () => {
  ladderData = await api("/api/ladder");
  render();
  // Columns come from the server (cards.STAGES) rather than the markup, so a new
  // stage needs one Python edit and no HTML change.
  const health = await api("/api/health");
  el("board-owner").textContent = "owner: " + (health.owner || "—") + (health.require_owner && !health.owner ? " · Set RDASH_OWNER to your handle; new cards carry the owner" : "");
  el("new").disabled = health.require_owner && !health.owner;
  const stages = await api("/api/stages");
  for (const stage of stages) {
    for (const target of ["stage-filter", "stage"]) {
      const option = document.createElement("option");
      option.value = stage;
      option.textContent = stage;
      el(target).append(option);
    }
  }
  for (const project of await api("/api/projects")) {
    const option = document.createElement("option");
    option.value = project.id;
    option.textContent = project.label + " (" + project.card_count + ")";
    el("project").append(option);
  }
  try {
    const saved = localStorage.getItem("rdash-project");
    if ([...el("project").options].some(o => o.value === saved)) el("project").value = saved;
  } catch (_) {}
  await refresh();
  // Job state is observed live and never stored, so tracking is re-reading it:
  // every 30 minutes while the page is visible, and on return to the tab.
  const TRACK_MS = 30 * 60 * 1000;
  let last = Date.now();
  const track = () => {
    if (document.hidden) return;
    last = Date.now();
    refresh(selected && selected.card).catch(e => el("error").textContent = e.message);
  };
  setInterval(track, TRACK_MS);
  document.addEventListener("visibilitychange", () => { if (Date.now() - last >= TRACK_MS) track(); });
})().catch(e => el("error").textContent = e.message);
