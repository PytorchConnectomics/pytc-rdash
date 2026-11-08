"use strict";
// Dependency-free DOM harness for panel rendering and command payloads.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.textContent = ""; this.value = ""; }
  append(...nodes) { for (const node of nodes) { node.parent = this; this.children.push(node); } }
  setAttribute(name, value) { this[name] = value; }
  get firstChild() { return this.children[0]; }
  replaceWith(node) { this.parent.children[this.parent.children.indexOf(this)] = node; node.parent = this.parent; }
}
const descendants = node => [node, ...node.children.flatMap(descendants)];
const text = node => descendants(node).map(n => n.textContent).join("\n");
const find = (node, tag, label) => descendants(node).find(n => n.tag === tag && (!label || n.textContent === label));
const source = fs.readFileSync(path.join(__dirname, "../app/static/app.js"), "utf8");
const calls = [];
let reject = false;
let current;
const context = vm.createContext({document: {
  createElement: tag => new Element(tag),
  createTextNode: value => Object.assign(new Element("text"), {textContent: value}),
}, api: async (url, data) => {
  calls.push({url, data});
  if (reject) throw new Error("stale_revision");
  return data ? {id: "command-1", state: "pending"} : current;
}});
vm.runInContext(source.slice(source.indexOf("function goalPanel("), source.indexOf("function show(card)")), context);
const fixture = () => ({id: "demo", project: "alpha", phase: "decision_required", goal_revision: "revision-1",
  budget: {cpu_hours: 12, jobs: 4, coordinator_runs: 12}, consumed_cpu_hours: 2, held_cpu_hours: 3,
  unsettled_cpu_hours: 1, consumed_jobs: 1, held_jobs: 1, coordinator_runs_used: 2,
  assignment_in_flight: ["a01-tissue"], next_event: "assignment_terminal", rationale: "Wait for verified tissue.",
  assignments: {a: {parameters: {pct: {authorization: "human_decision", allowed_values: [99, 99.5]}}}},
  pending_decisions: [{id: "decision-1", assignment: "a", parameter: "pct", question: "Choose pct"}]});
const render = goal => { const root = new Element("root"); context.goalPanel(root, goal); return root; };
const tick = () => new Promise(resolve => setImmediate(resolve));

(async () => {
  const root = render(fixture());
  assert.match(text(root), /unsettled \(included in held\) 1 · remaining 7/);
  assert.match(text(root), /Assignment in flight: a01-tissue/);
  assert.match(text(root), /Event permitting continuation: assignment_terminal/);
  assert.match(text(root), /Coordinator rationale: Wait for verified tissue\./);
  assert.doesNotMatch(text(root), /Owner:|Next:/);
  find(root, "select").value = "1";
  find(root, "form").onsubmit({preventDefault() {}});
  await tick();
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0])), {url: "/api/goal/command", data: {
    project: "alpha", goal: "demo", goal_revision: "revision-1", kind: "resolve_decision",
    payload: {decision_id: "decision-1", value: 99.5},
  }});
  assert.match(text(root), /queued/);
  assert.equal(find(root, "button", "Resolve decision").disabled, true);

  reject = true;
  const stale = render(fixture()); find(stale, "select").value = "0";
  find(stale, "form").onsubmit({preventDefault() {}}); await tick();
  assert.match(text(stale), /stale_revision.*Refresh the goal/);
  reject = false; current = {...fixture(), goal_revision: "revision-2", pending_decisions: []};
  await find(stale, "button", "Refresh goal").onclick();
  assert.match(text(stale), /Pending decisions: 0/);

  const ambiguous = fixture(); ambiguous.pending_decisions[0].reason = "ambiguous_submission";
  const adopt = render(ambiguous); const select = find(adopt, "select");
  select.value = "0"; select.onchange();
  find(adopt, "input").value = "12345";
  find(adopt, "form").onsubmit({preventDefault() {}}); await tick();
  assert.deepEqual(JSON.parse(JSON.stringify(calls.at(-1).data.payload.value)), {action: "adopt", job_id: "12345"});

  const conflict = render({goal_ids: ["demo", "other"], goals: [fixture(), {...fixture(), id: "other"}]});
  assert.match(text(conflict), /Multiple goals reference this card: demo, other/);
  assert.equal(descendants(conflict).filter(n => n.tag === "button" && n.textContent === "Refresh goal").length, 2);
  assert.match(text(render({id: "demo", phase: "unknown"})), /Pending decisions: unknown/);
  console.log("Goal panel: rendering, revision-bound resolution, stale errors, refresh, adoption, and conflicts passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
