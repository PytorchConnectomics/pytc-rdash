"""Plan and Summary modes read plan/ and write one line at a time."""
import datetime as dt
import shutil
from pathlib import Path

from fixtures import RepoTest
from dashboard.app import ladder, planner
from dashboard.app.safety import Error

FIXTURES = Path(__file__).parent / "fixtures"
DAY = "plan/days/2026-11-09.md"


class PlannerTests(RepoTest):
    def setUp(self):
        super().setUp()
        (self.repo / "plan").mkdir()
        self.today = dt.date(2026, 11, 9)

    def test_sprints_are_plan_files_with_rungs(self):
        rows = planner.ladders(self.settings)
        self.assertEqual([(r["rel"], r["missing"]) for r in rows], [("plan/LADDER.md", True)])
        shutil.copyfile(FIXTURES / "LADDER.md", self.repo / "plan/LADDER.md")
        (self.repo / "plan/overview.md").write_text("# Overview\nno rungs here\n")
        (self.repo / "plan/sprint-b.md").write_text("# Sprint B\n\n## Rungs\n\n| Month | Rung | G1 | G2 | G3 |\n|---|---|---|---|---|\n| 2027-05 | x | [met] ran | — | bad-month |\n| 27-05 | y | — | — | — |\n")
        rows = planner.ladders(self.settings)
        self.assertEqual([r["rel"] for r in rows], ["plan/LADDER.md", "plan/sprint-b.md"])
        self.assertEqual(sorted(rows[0]["months"]), [(2026, 9), (2026, 10), (2026, 11), (2026, 12), (2027, 1), (2027, 2), (2027, 3)])
        self.assertEqual(rows[0]["months"][(2026, 10)][0]["g1"], dict(state="met", text="ran"))
        self.assertEqual(rows[1]["months"][(2027, 5)][0]["g3"]["state"], "target")
        self.assertEqual(len(rows[1]["errors"]), 1)
        # the board's own ladder view reads the same file, root LADDER.md only as the older location
        self.assertEqual(len(ladder.read(self.settings)["rows"]), 9)
        html = planner.render_ladder(self.settings, self.today)
        for needle in ("Oct 2026", 'class="lmon now">Nov 2026', "May 2027", 'class="g met"', "plan/sprint-b.md", 'data-n="9"'):
            self.assertIn(needle, html)
        self.assertNotIn("style=", html)   # the CSP blocks inline style attributes; the grid collapsed to one column once

    def test_rung_deliverables_are_grouped_tagged_and_edited_in_the_ladder_file(self):
        shutil.copyfile(FIXTURES / "LADDER.md", self.repo / "plan/LADDER.md")
        text = (self.repo / "plan/LADDER.md").read_text() + (
            "\n## Deliverables\n\n### 2026-10 — 20 µm\n\n- [x] ran the cube #chem\n  - note under it\n- [.] score it\n"
            "\n#### Explorative\n\n- [ ] write it up #optics #ephys\n"
            "\n### 2026-11 — 50 µm\n\n- [ ] decode\n\n### 2026-11 — 20 µm iteration\n\n#### Shovel-ready\n\n- [x] iter-01\n\n## After\n\n- [ ] not a deliverable\n")
        (self.repo / "plan/LADDER.md").write_text(text)
        lad = planner.ladders(self.settings)[0]
        oct_ = lad["months"][(2026, 10)][0]["items"]
        self.assertEqual([(i["state"], i["clean"], i["group"], i["teams"], i["sub"]) for i in oct_],
                         [("done", "ran the cube", "shovel", ["chem"], ["note under it"]), ("doing", "score it", "shovel", ["comp"], []),
                          ("todo", "write it up", "explore", ["optics", "ephys"], [])])
        by_name = {r["rung"]: [i["text"] for i in r["items"]] for r in lad["months"][(2026, 11)]}
        self.assertEqual(by_name, {"20 µm iteration": ["iter-01"], "50 µm": ["decode"], "100 µm": []})
        self.assertEqual(lad["months"][(2026, 9)][0]["items"], [])
        html = planner.render_ladder(self.settings, self.today)
        for needle in ('<span class="dn">1 / 3</span>', 'class="g met">ran</span>', 'class="g open">quality</span>', 'class="gate met"',
                       '<h5>shovel-ready</h5>', '<h5>explorative</h5>', 'select class="team t-chem"', 'class="chip t-ephys"',
                       'data-text="write it up"', 'data-tags="#optics #ephys"', 'placeholder="+ explorative item"'):
            self.assertIn(needle, html)
        self.assertNotIn("style=", html)
        self.assertNotIn(">G1<", html)                      # gates are named in words, not codes
        # edit keeps the checkbox and rewrites the text (tags ride along in the text)
        line = oct_[1]["line"]
        planner.apply_edit(self.settings, "plan/LADDER.md", line, oct_[1]["orig"], "edit", text="score   it well #meche")
        self.assertIn("- [.] score it well #meche\n", (self.repo / "plan/LADDER.md").read_text())
        with self.assertRaises(Error):
            planner.apply_edit(self.settings, "plan/LADDER.md", line, "- [.] score it well #meche", "edit", text="two\nlines")
        # add into an existing sub-block, into the untitled shovel run, and into a sub-block that has to be created
        lad = planner.ladders(self.settings)[0]
        blk = lad["months"][(2026, 10)][0]["block"]
        planner.apply_edit(self.settings, "plan/LADDER.md", blk["anchors"]["explore"]["line"], blk["anchors"]["explore"]["orig"], "add", text="try X", group="explore")
        planner.apply_edit(self.settings, "plan/LADDER.md", blk["line"], blk["orig"], "add", text="do Y", group="shovel")
        lad = planner.ladders(self.settings)[0]
        got = [(i["group"], i["clean"]) for i in lad["months"][(2026, 10)][0]["items"]]
        self.assertEqual(got, [("shovel", "ran the cube"), ("shovel", "score it well"), ("shovel", "do Y"), ("explore", "write it up"), ("explore", "try X")])
        blk = lad["months"][(2026, 11)][1]["block"] if lad["months"][(2026, 11)][1]["rung"] == "50 µm" else lad["months"][(2026, 11)][0]["block"]
        planner.apply_edit(self.settings, "plan/LADDER.md", blk["line"], blk["orig"], "add", text="guess Z", group="explore")
        body = (self.repo / "plan/LADDER.md").read_text()
        self.assertIn("- [ ] decode\n\n#### Explorative\n\n- [ ] guess Z\n\n### 2026-11 — 20 µm iteration", body)
        self.assertIn("- [ ] not a deliverable", body)
        with self.assertRaises(Error):
            planner.apply_edit(self.settings, "plan/LADDER.md", blk["line"], blk["orig"], "add", text="q", group="other")
        for bad in ("plan/../LADDER.md", "plan/sub/x.md", "LADDER.md", "plan/.hidden.md"):
            with self.assertRaises(Error):
                planner.plan_path(self.settings, bad)

    def test_day_file_parse_toggle_delete_and_create(self):
        self.assertFalse(planner.read_plan(self.settings, DAY)["exists"])
        self.assertIn("Create it", planner.render_daily(self.settings, self.today, self.today))
        self.assertEqual(planner.new_plan(self.settings, DAY, ["alpha", "beta"]), "created " + DAY)
        self.assertEqual(planner.new_plan(self.settings, DAY), "exists: " + DAY)
        path = self.repo / DAY
        path.write_text(path.read_text() + "- [ ] first\n  - a note\n- [.] doing\n- [x] done\n- plain note\n")
        info = planner.read_plan(self.settings, DAY)
        self.assertEqual([s["name"] for s in info["sections"]], ["alpha", "beta"])
        items = info["sections"][1]["items"]
        self.assertEqual([(i["state"], i["text"], i["sub"]) for i in items],
                         [("todo", "first", ["a note"]), ("doing", "doing", []), ("done", "done", []), ("note", "plain note", [])])
        line = items[0]["line"]
        self.assertEqual(planner.apply_edit(self.settings, DAY, line, "- [ ] first", "toggle"), "toggle: %s:%d" % (DAY, line + 1))
        self.assertIn("- [x] first\n  - a note\n", path.read_text())
        self.error(409, "stale_line", planner.apply_edit, self.settings, DAY, line, "- [ ] first", "toggle")
        self.error(400, "not_checkbox", planner.apply_edit, self.settings, DAY, line + 1, "  - a note", "toggle")
        planner.apply_edit(self.settings, DAY, line, "- [x] first", "delete")
        self.assertNotIn("first", path.read_text())
        self.assertNotIn("a note", path.read_text())
        self.assertIn("- [.] doing\n- [x] done\n", path.read_text())
        html = planner.render_daily(self.settings, self.today, self.today)
        self.assertIn('data-orig="- [.] doing"', html)
        self.assertIn("1/2 done", html)
        self.assertNotIn("<script>", html)   # no inline script: the board's CSP stays strict

    def test_week_files_and_path_rules(self):
        self.error(400, "invalid_path", planner.plan_path, self.settings, "plan/weeks/2026-11-10.md")   # a Tuesday
        self.error(400, "invalid_path", planner.plan_path, self.settings, "plan/days/../LADDER.md")
        self.error(400, "invalid_path", planner.plan_path, self.settings, "LADDER.md")
        self.error(400, "invalid_path", planner.plan_path, self.settings, "plan/days/2026-13-01.md")
        self.error(400, "invalid_path", planner.plan_path, self.settings, None)
        self.error(404, "not_found", planner.apply_edit, self.settings, DAY, 0, "", "toggle")
        week = "plan/weeks/2026-11-09.md"
        planner.new_plan(self.settings, week, ["alpha"])
        self.assertIn("Week of Mon 2026-11-09", (self.repo / week).read_text())
        html = planner.render_weekly(self.settings, dt.date(2026, 11, 11), self.today)   # any day maps to its Monday
        self.assertIn("this week", html)
        self.assertIn(week, html)
        self.assertIn("/plan/weekly?w=2026-11-02", html)

    def test_summary_kinds_cadence_and_view(self):
        folder = self.repo / "plan/summary"
        folder.mkdir()
        (folder / "2026-11-05-weekly.md").write_text("# Week 45\n\n## Past week\n- [x] shipped\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
        (folder / "2026-11-03-heads.md").write_text("# Heads 11/03\n")
        (folder / "2026-11-05-konrad.md").write_text("# Konrad\n")
        (folder / "2026-10-29-ed.md").write_text("# Ed\n")
        (folder / "2026-10-27-richie.md").write_text("# Richie\n")
        (folder / "README.md").write_text("# not dated\n")
        ents = planner.summaries(self.settings)
        self.assertEqual([(e["date"].isoformat(), e["kind"]) for e in ents],
                         [("2026-11-05", "weekly"), ("2026-11-05", "konrad"), ("2026-11-03", "heads"), ("2026-10-29", "ed"), ("2026-10-27", "note")])
        html = planner.render_summary(self.settings, self.today)
        self.assertIn("due Tue", html)       # this week's heads slot, still ahead on Monday 11/09
        self.assertIn("due Thu", html)
        self.assertIn('href="/summary/view?p=plan/summary/2026-11-05-weekly.md"', html)
        self.assertIn("Richie", html)
        view = planner.render_summary_view(self.settings, "plan/summary/2026-11-05-weekly.md")
        self.assertIn("<h2>Past week</h2>", view)
        self.assertIn("☑ shipped", view)
        self.assertIn("<table><tr><th>a</th>", view)
        self.error(400, "invalid_path", planner.render_summary_view, self.settings, "plan/summary/../LADDER.md")
        self.error(400, "invalid_path", planner.render_summary_view, self.settings, "LADDER.md")
        self.error(404, "not_found", planner.render_summary_view, self.settings, "plan/summary/nope.md")
        (folder / "link.md").symlink_to(folder / "2026-11-05-weekly.md")
        self.assertEqual(len(planner.summaries(self.settings)), 5)
