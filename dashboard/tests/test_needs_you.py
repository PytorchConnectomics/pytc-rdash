import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from dashboard.app import cards
from dashboard.app.attention import owner_and_next
from dashboard.app.needs_you import collect, frontmatter_state, parse

VALID = "# T\n\n## Needs you\n\n1. Accept the seed42 anchor\n2. Fund a seed100 re-run (4 GPUh)\nRecommendation: 1, the anchor is already measured\n"


def record(**overrides):
    base = dict(read_only=False, verdict=None, jobs=[], artifacts=[], state=None, needs_you=None,
                contract=dict(declared=True, structure="pass", missing_facts=0),
                acceptance=dict(declared=True, total=2, settled=2), sessions=dict(declared=False))
    base.update(overrides)
    return base


class BlockTests(unittest.TestCase):
    def test_valid_block(self):
        block = parse(VALID)
        self.assertTrue(block["valid"])
        self.assertEqual(len(block["options"]), 2)
        self.assertEqual(block["recommendation"], "1, the anchor is already measured")

    def test_missing_section_more_than_three_options_and_no_recommendation(self):
        self.assertFalse(parse("# T\n")["valid"])
        four = "## Needs you\n1. a\n2. b\n3. c\n4. d\nRecommendation: a\n"
        self.assertIn("more than 3 options", parse(four)["problems"])
        self.assertIn("no `Recommendation:` line", parse("## Needs you\n1. a\n")["problems"])

    def test_frontmatter_state(self):
        self.assertEqual(frontmatter_state("---\nstate: needs-you\n---\n# x\n"), "needs-you")
        self.assertIsNone(frontmatter_state("---\nstate: later\n---\n"))
        self.assertIsNone(frontmatter_state("# no frontmatter\n"))


class AttentionStateTests(unittest.TestCase):
    def test_valid_bell_rings_before_any_inferred_owner(self):
        got = owner_and_next(record(state="needs-you", needs_you=parse(VALID), jobs=[dict(state="RUNNING")]))
        self.assertEqual((got["next"], got["owner"]), ("needs_you", "you"))
        self.assertIn("anchor is already measured", got["reason"])

    def test_malformed_bell_goes_back_to_the_agent(self):
        got = owner_and_next(record(state="needs-you", needs_you=parse("# T\n")))
        self.assertEqual((got["next"], got["owner"]), ("fix_needs_you", "agent"))

    def test_paused_and_done_are_silent_and_working_falls_through(self):
        self.assertEqual(owner_and_next(record(state="paused"))["owner"], "none")
        self.assertEqual(owner_and_next(record(state="done"))["next"], "closed")
        # done with a live job is not closed: the existing derivation decides
        self.assertEqual(owner_and_next(record(state="done", jobs=[dict(state="RUNNING")]))["next"], "wait")
        self.assertEqual(owner_and_next(record(state="working"))["next"], "record_verdict")

    def test_unreadable_frontmatter_still_comes_first(self):
        got = owner_and_next(record(read_only=True, state="needs-you", needs_you=parse(VALID)))
        self.assertEqual(got["next"], "fix_frontmatter")


class CardParseTests(unittest.TestCase):
    HEAD = "---\nid: P-1\ntitle: t\nproject: p\nstage: idea\ncreated: 2026-11-08\nupdated: 2026-11-08\n"

    def test_unknown_state_is_unsupported_frontmatter(self):
        with self.assertRaisesRegex(ValueError, "Unknown state"):
            cards.parse((self.HEAD + "state: waiting\n---\n# t\n").encode(), "p")

    def test_record_carries_state_and_block(self):
        rec = cards._record((self.HEAD + "state: needs-you\n---\n" + VALID).encode(), "p", "x.md")
        self.assertEqual(rec["state"], "needs-you")
        self.assertTrue(rec["needs_you"]["valid"])
        rec = cards._record((self.HEAD + "---\n# t\n").encode(), "p", "x.md")
        self.assertIsNone(rec["state"])
        self.assertIsNone(rec["needs_you"])


class CollectTests(unittest.TestCase):
    def test_two_workbenches_one_list_bells_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            bc = Path(tmp, "bc"); ms = Path(tmp, "ms")
            (bc / "projects/p1/focus").mkdir(parents=True)
            (bc / "projects/p1/cards").mkdir(parents=True)
            (ms / "projects/msi-1/focus").mkdir(parents=True)
            (bc / "projects/p1/focus/F-001.md").write_text("---\nstate: working\n---\n# F-001: a\n")
            (bc / "projects/p1/cards/c.md").write_text("---\nid: X\nstate: needs-you\n---\n# card\n## Needs you\n1. a\nRecommendation: a\n")
            (ms / "projects/msi-1/focus/F-002.md").write_text("---\nstate: needs-you\n---\n# F-002: b\nUpdated: 2026-11-08\n## Needs you\n1. a\n")
            (ms / "projects/msi-1/focus/F-003.md").write_text("# no state declared\n")
            items = collect([bc, ms])
            self.assertEqual([i["id"] for i in items], ["c", "F-002", "F-001"])
            self.assertTrue(items[0]["needs_you"]["valid"])
            self.assertFalse(items[1]["needs_you"]["valid"])
            self.assertEqual(items[1]["updated"], "2026-11-08")
            out = Path(tmp, "status.json")
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]))
            subprocess.run([sys.executable, "-m", "dashboard.app.needs_you", str(bc), str(ms), "--write", str(out)],
                           check=True, env=env, cwd=tmp)
            payload = json.loads(out.read_text())
            self.assertEqual([i["id"] for i in payload["needs_you"]], ["c", "F-002"])


if __name__ == "__main__":
    unittest.main()
