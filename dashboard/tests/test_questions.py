import tempfile
import unittest
from pathlib import Path

from dashboard.app import questions
from dashboard.app.config import Settings


class QuestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        project = root / "projects" / "alpha"
        (project / "cards").mkdir(parents=True)
        (project / "spec.md").write_text("# alpha\n")
        self.dir = project / "questions"
        self.settings = Settings.from_env({"RDASH_REPO_ROOT": str(root)})

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_directory(self):
        self.assertEqual(questions.read(self.settings, "alpha"), {"questions": [], "errors": []})

    def test_reads_frontmatter_and_sections(self):
        self.dir.mkdir()
        (self.dir / "README.md").write_text("# not a question\n")
        (self.dir / "Q-002_tuner.md").write_text(
            "---\nid: A-Q-002\ntitle: Tune input\ntask: data\nmilestone: M1\nstatus: open\n---\n"
            "# Q-002\n\n## Question\n\nCan we?\n\n## Conclusion\n\nNone yet.\n\n## Still open\n\nx\n")
        result = questions.read(self.settings, "alpha")
        self.assertEqual(result["errors"], [])
        [q] = result["questions"]
        self.assertEqual((q["key"], q["task"], q["milestone"], q["status"], q["question"], q["conclusion"]),
                         ("Q-002", "data", "M1", "open", "Can we?", "None yet."))

    def test_errors_are_reported(self):
        self.dir.mkdir()
        (self.dir / "Q-001_a.md").write_text("no frontmatter\n")
        (self.dir / "Q-003_b.md").write_text("---\ntitle: b\nstatus: maybe\n---\n")
        result = questions.read(self.settings, "alpha")
        self.assertEqual(len(result["errors"]), 2)
        self.assertEqual([(q["key"], q["status"]) for q in result["questions"]], [("Q-003", "open")])


if __name__ == "__main__":
    unittest.main()
