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
        for needle in ("Oct 2026", 'class="lmon now">Nov 2026', "May 2027", 'class="g met"', "plan/sprint-b.md", "--n:9"):
            self.assertIn(needle, html)

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
