// Plan and Summary pages: one-line edits to plan/days and plan/weeks, ladder scrolling, summary filters.
// No inline script anywhere, so the board's Content-Security-Policy (default-src 'self') holds.
(function () {
  function post(path, body) {
    return fetch(path, {method: "POST", headers: {"Content-Type": "application/json", "X-Rdash": "1"}, body: JSON.stringify(body)})
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) alert(j.message || j.error || ("HTTP " + r.status)); location.reload(); }); })
      .catch(function (e) { alert("edit failed: " + e); });
  }
  function edit(li, text) {   // the file line keeps its checkbox; team tags ride at the end of the text
    var tags = li.dataset.tags ? " " + li.dataset.tags : "";
    post("/api/plan/edit", {path: li.dataset.path, line: parseInt(li.dataset.line, 10), orig: li.dataset.orig, op: "edit", text: text + tags});
  }
  document.addEventListener("change", function (ev) {
    var el = ev.target; if (!el.matches) return;
    var li = el.closest("li[data-path]"); if (!li) return;
    if (el.matches("input[data-op=toggle]")) {
      post("/api/plan/edit", {path: li.dataset.path, line: parseInt(li.dataset.line, 10), orig: li.dataset.orig, op: "toggle"});
    } else if (el.matches("select.team")) {
      li.dataset.tags = el.value === "comp" ? "" : "#" + el.value;
      edit(li, li.dataset.text);
    }
  });
  document.addEventListener("keydown", function (ev) {
    var el = ev.target; if (!el.matches) return;
    if (el.matches("input.addi")) {
      if (ev.key !== "Enter" || !el.value.trim()) return;
      post("/api/plan/edit", {path: el.dataset.path, line: parseInt(el.dataset.line, 10), orig: el.dataset.orig, op: "add",
                              group: el.dataset.group || null, text: el.value.trim()});
    } else if (el.matches("input.edit")) {
      if (ev.key === "Enter" && el.value.trim()) edit(el.closest("li[data-path]"), el.value.trim());
      else if (ev.key === "Escape") location.reload();
    }
  });
  document.addEventListener("click", function (ev) {
    var t = ev.target; if (!t.matches) return;
    var txt = t.closest(".txt");
    if (txt && !t.closest("a") && txt.closest("li[data-path]") && !txt.closest("li").querySelector("input.edit")) {
      var li = txt.closest("li"), inp = document.createElement("input");
      inp.className = "edit"; inp.value = li.dataset.text; inp.maxLength = 300;
      txt.replaceWith(inp); inp.focus(); inp.select();
      return;
    }
    if (t.matches("button[data-op=delete]")) {
      var li = t.closest("li[data-path]"); if (!li) return;
      if (!confirm("Delete this item from " + li.dataset.path + "?\n\n" + li.dataset.orig)) return;
      post("/api/plan/edit", {path: li.dataset.path, line: parseInt(li.dataset.line, 10), orig: li.dataset.orig, op: "delete"});
    } else if (t.matches("button[data-new]")) {
      post("/api/plan/new", {path: t.dataset.new, projects: t.dataset.projects ? t.dataset.projects.split(",") : []});
    } else if (t.matches(".chip")) {
      var k = t.dataset.k;
      document.querySelectorAll(".chip").forEach(function (c) { c.classList.toggle("on", c.dataset.k === k); });
      document.querySelectorAll("ul.ent li").forEach(function (li) { li.style.display = (k === "all" || li.dataset.k === k) ? "" : "none"; });
    } else if (t.matches(".larr")) {
      var s = document.getElementById("lscroll"), cur = s && s.querySelector(".lmon");
      if (cur) s.scrollBy({left: parseInt(t.dataset.dir, 10) * cur.offsetWidth, behavior: "smooth"});
    }
  });
  // The column count travels as data-n: an inline style attribute is blocked by the
  // board's Content-Security-Policy, while setting the property from here is allowed.
  var g = document.querySelector(".lgrid[data-n]");
  if (g) g.style.setProperty("--n", g.dataset.n);
  var s = document.getElementById("lscroll"), cur = s && s.querySelector(".lmon.now");
  if (cur) s.scrollLeft = cur.offsetLeft - 150 - cur.offsetWidth;   // -1 | 0 | +1 in view
})();
