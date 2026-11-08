"use strict";
// Exercise the real rendering/event handlers without browser dependencies.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.textContent = ""; this.value = ""; }
  append(...nodes) { for (const node of nodes) { node.parent = this; this.children.push(node); } }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  setAttribute(name, value) { this[name] = value; }
  set innerHTML(_) { throw new Error("Untrusted evidence must never use HTML parsing"); }
}
const descendants = node => [node, ...node.children.flatMap(descendants)];
const text = node => descendants(node).map(n => n.textContent).join("\n");
const find = (node, tag, label) => descendants(node).find(n => n.tag === tag && (!label || n.textContent === label));
const source = fs.readFileSync(path.join(__dirname, "../app/static/app.js"), "utf8");
const calls = [];
let response;
const context = vm.createContext({document: {
  createElement: tag => new Element(tag),
  createTextNode: value => Object.assign(new Element("text"), {textContent: value}),
}, api: async (url, data) => { calls.push({url, data}); return response(url, data); }});
vm.runInContext(source.slice(source.indexOf("function goalPanel("), source.indexOf("function show(card)")), context);
vm.runInContext(source.slice(source.indexOf("function attentionLabel("), source.indexOf("// A task groups")), context);
const card = () => ({card: "cards/probe.md", revision: "card-revision-1", artifacts: [
  {label: "baseline", state: "present"}, {label: "candidate", state: "present"},
]});
const receipt = (label = "baseline") => ({label, path: "/runs/" + label + ".txt", host: "cajal",
  revision: "card-revision-1", artifact_revision: "digest-" + label, kind: "text", mime: "text/plain",
  size: 23, observed_at: 1700000000, text: "<script>alert('sample')</script>"});
const render = (value = card()) => {
  const root = new Element("root"); const saved = [];
  context.evidencePanel(root, value, "alpha", (...args) => saved.push(args));
  const slots = descendants(root).filter(n => n.className === "evidence-slot");
  return {root, saved, slots};
};
const choose = (slot, label) => { const select = find(slot, "select"); select.value = label; select.onchange(); };
const inspect = slot => find(slot, "button", "Inspect artifact").onclick();
const save = slot => find(slot, "form").onsubmit({preventDefault() {}});
const saveButton = slot => find(slot, "button", "Save evidence feedback");
const normalize = value => JSON.parse(JSON.stringify(value));

(async () => {
  assert.equal(context.attentionLabel({attention: {owner: "agent", next: "read_evidence"}}), "Agent can investigate");
  assert.equal(context.attentionLabel({attention: {owner: "agent", next: "in_session"}, sessions: {declared: true}}), "Agent can investigate");
  assert.equal(context.attentionLabel({attention: {owner: "agent", next: "in_session"}, sessions: {running: true}}), "Coordinator in flight");
  response = async (_url, data) => data ? {...card(), revision: "card-revision-2"} : receipt();
  const first = render(); const slot = first.slots[0];
  assert.equal(first.slots.length, 2);
  assert.match(text(first.root), /Check their dataset, sample and run before comparing/);
  assert.equal(saveButton(slot).disabled, true);
  assert.equal(find(slot, "input").disabled, true);
  find(slot, "input").value = "Uninspected"; await save(slot);
  assert.equal(calls.length, 0);
  choose(slot, "baseline"); await inspect(slot);
  assert.equal(saveButton(slot).disabled, false);
  assert.equal(find(slot, "pre").textContent, receipt().text);
  assert.equal(find(slot, "script"), undefined);
  assert.match(text(slot), /Artifact revision digest-baseline/);
  assert.match(calls[0].url, /revision=card-revision-1&label=baseline$/);
  find(slot, "input").value = "Check whether the thin axon is connected.";
  await save(slot);
  assert.deepEqual(normalize(calls.at(-1)), {url: "/api/evidence/feedback", data: {
    project: "alpha", card: "cards/probe.md", revision: "card-revision-1", label: "baseline",
    artifact_revision: "digest-baseline", text: "Check whether the thin axon is connected.",
  }});
  assert.equal(first.saved[0][0].revision, "card-revision-2");
  assert.match(first.saved[0][1], /saved to Ideas and discussion/);
  assert.equal(saveButton(slot).disabled, true);

  // Changing the selected artifact immediately invalidates inspected content.
  const changed = render(); response = async () => receipt();
  choose(changed.slots[0], "baseline"); await inspect(changed.slots[0]);
  choose(changed.slots[0], "candidate");
  assert.equal(saveButton(changed.slots[0]).disabled, true);
  assert.equal(find(changed.slots[0], "pre"), undefined);

  // A late response for A cannot enable feedback on the newly selected B.
  let complete;
  response = () => new Promise(resolve => { complete = resolve; });
  const race = render(); choose(race.slots[0], "baseline");
  const pending = inspect(race.slots[0]); choose(race.slots[0], "candidate");
  complete(receipt()); await pending;
  assert.equal(saveButton(race.slots[0]).disabled, true);
  assert.equal(find(race.slots[0], "pre"), undefined);

  // The exact image must display before its receipt authorizes feedback.
  response = async () => ({...receipt(), kind: "image", mime: "image/png",
    content_url: "/api/evidence/content?project=alpha&artifact_revision=digest-baseline"});
  const images = render(); choose(images.slots[0], "baseline"); await inspect(images.slots[0]);
  const img = find(images.slots[0], "img"); assert.ok(img);
  assert.equal(saveButton(images.slots[0]).disabled, true);
  img.onload(); assert.equal(saveButton(images.slots[0]).disabled, false);
  img.onerror(); assert.equal(saveButton(images.slots[0]).disabled, true);
  assert.match(text(images.root), /image changed or could not be loaded/);
  choose(images.slots[0], "candidate"); img.onload();
  assert.equal(saveButton(images.slots[0]).disabled, true);

  for (const bad of [{...receipt(), revision: "other-card"}, {...receipt(), label: "other-label"},
    {...receipt(), kind: "image", content_url: "https://elsewhere.example/image.png"}]) {
    response = async () => bad;
    const invalid = render(); choose(invalid.slots[0], "baseline"); await inspect(invalid.slots[0]);
    assert.equal(saveButton(invalid.slots[0]).disabled, true);
    assert.match(text(invalid.root), /Evidence unavailable/);
    assert.equal(find(invalid.root, "img"), undefined);
  }

  // Failed reads and stale feedback never preserve an inspection authority.
  response = async () => { throw new Error("Host unavailable"); };
  const offline = render(); choose(offline.slots[0], "baseline"); await inspect(offline.slots[0]);
  assert.match(text(offline.root), /Host unavailable.*Refresh the card/);
  assert.equal(saveButton(offline.slots[0]).disabled, true);
  response = async (_url, data) => { if (data) throw new Error("stale_artifact"); return receipt(); };
  const stale = render(); choose(stale.slots[0], "baseline"); await inspect(stale.slots[0]);
  find(stale.slots[0], "input").value = "A meaningful note"; await save(stale.slots[0]);
  assert.equal(saveButton(stale.slots[0]).disabled, true);
  assert.equal(stale.saved.length, 0);
  assert.match(text(stale.root), /stale_artifact.*Refresh the card/);
  assert.equal(find(stale.slots[0], "input").value, "A meaningful note");

  response = async () => ({...card(), revision: "card-revision-3"});
  await find(stale.root, "button", "Refresh card").onclick();
  assert.equal(stale.saved[0][0].revision, "card-revision-3");
  assert.match(stale.saved[0][1], /Card refreshed/);
  response = async () => receipt();
  const readonly = render({...card(), read_only: true}); choose(readonly.slots[0], "baseline");
  await inspect(readonly.slots[0]); assert.equal(saveButton(readonly.slots[0]).disabled, true);
  assert.match(text(readonly.root), /card is read-only/);
  const empty = render({...card(), artifacts: []});
  assert.equal(empty.slots.length, 0); assert.match(text(empty.root), /No artifacts are declared/);

  // Decision context uses recorded values without inventing evidence or cost.
  const goal = new Element("root");
  context.goalPanel(goal, {id: "g", pending_decisions: [{id: "d", question: "Next step?",
    alternatives: ["more samples", "stop"], evidence: [{sample: "<img onerror=alert(1)>"}], expected_cost: {gpu_hours: 2}}]});
  assert.match(text(goal), /Alternatives[\s\S]*more samples/);
  assert.match(text(goal), /Evidence[\s\S]*<img onerror=alert\(1\)>/);
  assert.match(text(goal), /Expected cost[\s\S]*gpu_hours/);
  assert.equal(find(goal, "img"), undefined);
  const noContext = new Element("root");
  context.goalPanel(noContext, {id: "g", pending_decisions: [{id: "d", question: "Next step?", alternatives: [], evidence: {}}]});
  assert.equal(descendants(noContext).filter(n => n.textContent === "Not recorded").length, 3);
  console.log("Evidence panel: safe previews, exact feedback, races, image loading, stale errors, refresh, and decision context passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
