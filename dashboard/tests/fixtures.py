import os
import shutil
import tempfile
import unittest
from pathlib import Path

from dashboard.app.config import Settings
from dashboard.app.safety import Error


SOURCE = Path(__file__).resolve().parents[2]
SAMPLE = (Path(__file__).parent / "fixtures/sample.md").read_bytes()


class RepoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rdash-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.cache = self.root / "cache"
        self.card = self.repo / "projects/alpha/cards/question.md"
        self.card.parent.mkdir(parents=True)
        self.card.write_bytes(SAMPLE)
        (self.repo / "projects/beta").mkdir()
        (self.repo / "projects/beta/spec.md").write_text("# Beta\n")
        (self.repo / "dashboard").mkdir()
        shutil.copyfile(SOURCE / "dashboard/TEMPLATE.md", self.repo / "dashboard/TEMPLATE.md")
        self.settings = Settings(self.repo, self.cache, 0)

    def error(self, status, code, function, *args, **kwargs):
        with self.assertRaises(Error) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.status, status)
        self.assertEqual(caught.exception.payload["error"], code)
        return caught.exception

    def env(self, port):
        return dict(os.environ, RDASH_REPO_ROOT=str(self.repo), RESEARCH_DASH_CACHE=str(self.cache),
                    RESEARCH_DASH_PORT=str(port), PYTHONDONTWRITEBYTECODE="1")
