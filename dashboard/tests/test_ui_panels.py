"""Exercise interactive panel contracts with the dependency-free Node DOM harness."""
import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "Node is required for the panel DOM harness")
class PanelTests(unittest.TestCase):
    def run_panel(self, filename):
        result = subprocess.run(
            [shutil.which("node"), str(Path(__file__).with_name(filename))],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_goal_decisions(self):
        self.run_panel("test_goal_panel.js")

    def test_artifact_inspection_and_feedback(self):
        self.run_panel("test_evidence_panel.js")
