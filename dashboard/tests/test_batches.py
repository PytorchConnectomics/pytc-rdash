import json
from dataclasses import replace
from unittest import mock

from dashboard.app import cards, launch, receipts
from dashboard.app.jobs import declared_status, declared_steps
from dashboard.tests.fixtures import RepoTest, SAMPLE
from dashboard.tests.test_launch import ROOT, TREE

STEPS = {"info": {"script": "scripts/pipeline/info.sbatch", "jobs": []},
         "align": {"script": "scripts/pipeline/align.sbatch", "jobs": [7]}}
BATCH = {"name": "brain3", "input": "/data/in/Brain3.czi", "fold_z": "120"}


def fence(**extra):
    body = {"schema_version": 1, "host": "gpu1", "batch": BATCH, "steps": STEPS, "jobs": [7]}
    body.update(extra)
    return "\n```probe-status\n" + json.dumps(body) + "\n```\n"


BODY = """
## Summary

Brain3 arrived 2026-10-07.
Aligned; no fold.

Later paragraph.

## Steps

- [x] **info** — header read
- [ ] **align** — waiting
  on the queue
- [ ] no key here
- [ ] **Bad Key** — kept as text
"""


class BatchParseTests(RepoTest):
    def test_steps_summary_and_step_jobs(self):
        self.card.write_bytes(SAMPLE.replace(b"track: model", b"track: model\ntask: batch") + BODY.encode() + fence().encode())
        record = cards.read_card(self.settings, "alpha", "question.md")
        self.assertFalse(record["read_only"], record.get("reason"))
        steps = record["steps"]
        self.assertEqual([(s["key"], s["checked"]) for s in steps],
                         [("info", True), ("align", False), (None, False), (None, False)])
        self.assertEqual(steps[0]["text"], "header read")
        self.assertEqual(steps[1]["text"], "waiting on the queue")
        self.assertEqual(steps[3]["text"], "**Bad Key** — kept as text")
        self.assertEqual(record["summary"], "Brain3 arrived 2026-10-07. Aligned; no fold.")
        self.assertEqual(record["step_jobs"], {"info": [], "align": [7]})

    def test_non_batch_cards_carry_no_steps(self):
        self.card.write_bytes(SAMPLE + BODY.encode())
        self.assertNotIn("steps", cards.read_card(self.settings, "alpha", "question.md"))

    def test_declared_steps_ignores_malformed_entries(self):
        text = fence(steps={"ok": {"jobs": [1, "2", True, -3]}, "Bad": {"jobs": [4]}, "x": "nope"})
        self.assertEqual(declared_steps(text), {"ok": [1]})
        self.assertEqual(declared_steps("no fence"), {})


class StepLaunchTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.settings = replace(self.settings, ssh_hosts=("gpu1",))

    def run_launch(self, replies, **kwargs):
        calls = []

        def exchange(argv, payload, timeout=None, max_output=None):
            calls.append((argv[-1], payload))
            return replies.pop(0)
        with mock.patch.object(launch.inspection, "_exchange", exchange), \
                mock.patch.object(launch.inspection, "resolve_roots", lambda host, paths, timeout=30: tuple(paths)), \
                mock.patch.object(launch, "load_roots", lambda *a, **k: (("gpu1", ROOT),)), \
                mock.patch.object(launch, "committed_scripts",
                                  lambda repo, project, script, ref=None: ("0123456789ab", TREE, b"TAR")):
            return launch.launch(self.settings, "alpha", "question.md", **kwargs), calls

    def test_step_launch_exports_batch_and_records_under_step(self):
        self.card.write_bytes(SAMPLE + fence().encode())
        snapshot = ("%s/alpha/stage/%s\n" % (ROOT, TREE)).encode()
        result, calls = self.run_launch([(b"", "ok"), (snapshot, "ok"), (b"4242\n", "ok"), (b"stored\n", "ok")], step="info")
        squeue, sbatch = calls[0][0], calls[2][0]
        self.assertIn("rdash-question-info", squeue)
        self.assertIn("--job-name=rdash-question-info", sbatch)
        self.assertIn("RDASH_STEP=info,RDASH_BATCH_FOLD_Z=120,RDASH_BATCH_INPUT=/data/in/Brain3.czi,RDASH_BATCH_NAME=brain3", sbatch)
        self.assertIn("/stage/%s/pipeline/info.sbatch" % TREE, sbatch)
        self.assertEqual(result["step"], "info")
        receipt = json.loads(calls[3][1])
        self.assertEqual((receipt["job"], receipt["step"]), (4242, "info"))
        # The board joins the receipt to the card's step; the card is not edited.
        receipts.store(self.settings, dict(receipt, collected_at="t"))
        record = dict(card="question.md", step_jobs=declared_steps(self.card.read_text()))
        receipts.annotate([record], self.settings, "alpha")
        self.assertEqual(record["step_jobs"], {"info": [4242], "align": [7]})
        self.assertEqual(declared_status(self.card.read_text())["jobs"], [7])

    def test_step_validation(self):
        for step, extra, code in (("Info", {}, "invalid_step"), ("missing", {}, "no_step"),
                                  ("info", {"batch": {"name": "a,b"}}, "invalid_batch"),
                                  ("info", {"batch": {"name": "a=b"}}, "invalid_batch"),
                                  ("info", {"batch": {"Bad": "x"}}, "invalid_batch"),
                                  ("info", {"batch": ["x"]}, "invalid_batch"),
                                  ("info", {"steps": {"info": {"script": "/abs.sbatch"}}}, "invalid_script")):
            with self.subTest(step=step, extra=extra):
                with self.assertRaises(launch.Error) as caught:
                    launch.declared_launch(fence(**extra), step)
                self.assertEqual(caught.exception.payload["error"], code)

    def test_plain_launch_unchanged_when_no_step(self):
        with self.assertRaises(launch.Error) as caught:
            launch.declared_launch(fence())
        self.assertEqual(caught.exception.payload["error"], "no_launch")
        self.assertEqual(launch.job_name("cards/x.md"), "rdash-x")
        self.assertEqual(launch.job_name("cards/x.md", "align"), "rdash-x-align")



PIPE = {"batch": {"required": ["name", "input"], "optional": ["fold_z"]},
        "steps": [{"name": "info", "script": "scripts/pipeline/info.sbatch", "needs": [], "check": "header read"},
                  {"name": "align", "script": "scripts/pipeline/align.sbatch", "needs": ["info"], "check": "<= 1 px"},
                  {"name": "feedback", "script": None, "needs": ["align"], "check": "sent"}]}


class BatchCommandTests(RepoTest):
    def setUp(self):
        super().setUp()
        from dashboard.app import batch
        self.batch = batch
        self.card.unlink()
        (self.repo / "projects/alpha/spec.md").write_text(
            "# Alpha\n\n## PIPELINE\n\n```rdash-pipeline\n" + json.dumps(PIPE) + "\n```\n")
        self.states = {}
        patcher = mock.patch.object(batch.inspection, "annotate_status", self.annotate)
        patcher.start(); self.addCleanup(patcher.stop)

    def annotate(self, records, settings, project=None):
        for record in records:
            ids = declared_status(record["body"])["jobs"] + [r["job"] for r in record.get("receipts", [])]
            record["jobs"] = [dict(id=i, state=self.states.get(i, "unknown")) for i in ids]

    def new(self, **values):
        return self.batch.create(self.settings, "alpha", "brain3", "2026-10-07", dict({"input": "/d/b3.czi"}, **values))

    def add_job(self, ref, step, job):
        receipts.store(self.settings, receipts.validate(dict(
            schema=receipts.SCHEMA, job=job, host="cajal", via="rsub", project="alpha", card=ref, step=step)))

    def test_new_card_parses_and_reports_first_step_ready(self):
        report = self.new()
        self.assertEqual(report["card"], "cards/batch-2026-10-07_brain3.md")
        self.assertEqual(report["id"], "ALPHA-BATCH-001")
        self.assertEqual(report["batch"], {"input": "/d/b3.czi", "name": "brain3"})
        self.assertEqual([(r["step"], r["state"]) for r in report["steps"]],
                         [("info", "ready"), ("align", "blocked"), ("feedback", "blocked")])
        self.assertEqual(report["next"], "info")
        self.assertIn("hub.sh launch alpha cards/batch-2026-10-07_brain3.md --step info", report["steps"][0]["launch"])
        record = cards.read_card(self.settings, "alpha", "batch-2026-10-07_brain3.md")
        self.assertFalse(record["read_only"], record.get("reason"))

    def test_new_validates_batch_values_and_duplicates(self):
        for values, code in (({"input": "a,b"}, "invalid_batch"), ({"other": "x"}, "invalid_batch")):
            with self.subTest(values=values):
                with self.assertRaises(self.batch.Error) as caught:
                    self.batch.create(self.settings, "alpha", "brain3", "2026-10-07", values)
                self.assertEqual(caught.exception.payload["error"], code)
        with self.assertRaises(self.batch.Error) as caught:
            self.batch.create(self.settings, "alpha", "brain3", "2026-10-07", {})
        self.assertEqual(caught.exception.payload["error"], "invalid_batch")
        self.new()
        with self.assertRaises(self.batch.Error) as caught:
            self.new()
        self.assertEqual(caught.exception.payload["error"], "batch_exists")

    def test_tick_requires_completed_job_and_order(self):
        ref = "batch-2026-10-07_brain3.md"
        self.new()
        def err(**kw):
            with self.assertRaises(self.batch.Error) as caught:
                self.batch.tick(self.settings, "alpha", ref, **kw)
            return caught.exception.payload["error"]
        self.assertEqual(err(step="info", result="ok"), "job_not_completed")
        self.assertEqual(err(step="align", result="ok"), "needs_unmet")
        self.add_job(ref, "info", 11)
        self.states[11] = "RUNNING"
        self.assertEqual(self.batch.status(self.settings, "alpha", ref)["steps"][0]["state"], "running")
        self.states[11] = "COMPLETED"
        row = self.batch.status(self.settings, "alpha", ref)["steps"][0]
        self.assertEqual(row["state"], "check")
        self.assertIn("tick", row)
        report = self.batch.tick(self.settings, "alpha", ref, "info", "Z326, jumps at z 155")
        self.assertEqual([r["state"] for r in report["steps"]], ["done", "ready", "blocked"])
        self.assertIn("- [x] **info** — Z326, jumps at z 155\n", (self.repo / "projects/alpha/cards" / ref).read_text())
        self.assertEqual(err(step="info", result="again"), "already_ticked")
        self.add_job(ref, "align", 12)
        self.states[12] = "FAILED"
        self.assertEqual(self.batch.status(self.settings, "alpha", ref)["steps"][1]["state"], "failed")
        report = self.batch.tick(self.settings, "alpha", ref, "align", "no drift in this volume", skip=True)
        self.assertEqual(report["steps"][1]["text"], "skipped — no drift in this volume")
        self.assertEqual(report["next"], "feedback")
        self.assertIn("tick", report["steps"][2])
        self.assertTrue(self.batch.tick(self.settings, "alpha", ref, "feedback", "emailed Shulin")["complete"])

    def test_launch_refuses_unmet_needs(self):
        self.new()
        text = (self.repo / "projects/alpha/cards/batch-2026-10-07_brain3.md").read_text()
        with self.assertRaises(launch.Error) as caught:
            launch.declared_launch(text, "align")
        self.assertEqual(caught.exception.payload["error"], "needs_unmet")
        with self.assertRaises(launch.Error) as caught:
            launch.declared_launch(text, "feedback")
        self.assertEqual(caught.exception.payload["error"], "no_step")
        self.assertEqual(launch.declared_launch(text, "info")["batch"]["name"], "brain3")

    def test_pipeline_validation(self):
        bad = dict(PIPE, steps=[{"name": "a", "script": None, "needs": ["later"]}])
        (self.repo / "projects/alpha/spec.md").write_text("```rdash-pipeline\n" + json.dumps(bad) + "\n```\n")
        with self.assertRaises(self.batch.Error) as caught:
            self.batch.pipeline(self.settings, "alpha")
        self.assertEqual(caught.exception.payload["error"], "invalid_pipeline")
