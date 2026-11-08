import json
from dataclasses import replace
from unittest import mock

from dashboard.app import inspection, receipts
from dashboard.tests.fixtures import RepoTest, SAMPLE

ROOT = "/data/runs"


def receipt(**extra):
    row = dict(schema=receipts.SCHEMA, job=4242, host="gpu1", via="rsub", project="alpha", card="question.md")
    row.update(extra)
    return row


class ValidateTests(RepoTest):
    def test_normalizes_and_drops_unknown_keys(self):
        out = receipts.validate(receipt(job="4242", extra="x", step="info"))
        self.assertEqual(out["job"], 4242)
        self.assertNotIn("extra", out)
        self.assertEqual(out["step"], "info")

    def test_rejects_malformed_fields(self):
        for bad in (dict(schema="other"), dict(job=0), dict(job=True), dict(host="a b"), dict(via="sbatch"),
                    dict(card="../x.md"), dict(project="a/b"), dict(step="Bad"), dict(focus="F-1"),
                    dict(snapshot="relative"), dict(argv="x"), dict(code=dict(path="/x", commit="abc")),
                    dict(project=None)):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    receipts.validate(receipt(**bad))

    def test_store_is_write_once_and_load_checks_the_name(self):
        self.assertTrue(receipts.store(self.settings, receipts.validate(receipt())))
        self.assertFalse(receipts.store(self.settings, receipts.validate(receipt(note="again"))))
        runs = self.repo / "projects/alpha/runs"
        self.assertEqual([p.name for p in runs.iterdir()], ["gpu1-4242.json"])
        # A file whose content names another job is ignored, not trusted.
        (runs / "gpu1-7.json").write_text(json.dumps(receipt()))
        (runs / "notes.txt").write_text("x")
        self.assertEqual([r["job"] for r in receipts.load(self.settings, "alpha")], [4242])

    def test_annotate_joins_by_card(self):
        receipts.store(self.settings, receipts.validate(receipt()))
        receipts.store(self.settings, receipts.validate(receipt(job=5, card=None)))
        records = [dict(card="question.md"), dict(card="other.md")]
        receipts.annotate(records, self.settings, "alpha")
        self.assertEqual([r["job"] for r in records[0]["receipts"]], [4242])
        self.assertEqual(records[1]["receipts"], [])


class BoardJoinTests(RepoTest):
    def test_card_jobs_union_fence_and_receipts_observed_per_host(self):
        self.card.write_bytes(SAMPLE + b'\n```probe-status\n{"host": "gpu1", "jobs": [7]}\n```\n')
        settings = replace(self.settings, ssh_hosts=("gpu1", "gpu2"))
        receipts.store(settings, receipts.validate(receipt(job=7)))            # duplicate of the fence
        receipts.store(settings, receipts.validate(receipt(job=8, host="gpu2")))
        seen = {}

        def cached(host, channel, items, roots=(), timeout=30):
            seen.setdefault(channel, {})[host] = list(items)
            return {i: dict(reduced="COMPLETED" if host == "gpu1" else "RUNNING", tasks={}) for i in items}
        from dashboard.app import cards
        records = receipts.annotate(cards.list_cards(settings, "alpha"), settings, "alpha")
        with mock.patch.object(inspection, "cached", cached):
            inspection.annotate_status(records, settings, "alpha")
        jobs = {(j.get("host", "gpu1"), j["id"]): j["state"] for j in records[0]["jobs"]}
        self.assertEqual(jobs, {("gpu1", 7): "COMPLETED", ("gpu2", 8): "RUNNING"})
        self.assertEqual(seen["jobs"], {"gpu1": [7], "gpu2": [8]})
        self.assertNotIn("_group", records[0]["jobs"][0])


class CollectTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.settings = replace(self.settings, ssh_hosts=("gpu1",))
        (self.repo / "projects/gamma/focus").mkdir(parents=True)
        (self.repo / "projects/gamma/focus/F-003.md").write_text("# F-003\n")

    def run_collect(self, listing, files):
        def lines(host, channel, items, timeout=60, max_output=None):
            self.assertEqual((host, channel, items), ("gpu1", "receipts", [ROOT]))
            return listing

        def channel(host, name, paths, roots=(), timeout=30):
            self.assertEqual(name, "content")
            return [dict(state="present", data=files[p]) if p in files else dict(state="absent") for p in paths], "ok"
        with mock.patch.object(receipts, "launch_roots", lambda s: {"gpu1": [ROOT]}), \
                mock.patch.object(inspection, "json_lines", lines), \
                mock.patch.object(inspection, "_channel", channel):
            return receipts.collect(self.settings)

    def test_new_receipts_are_stored_bad_ones_skipped_and_nothing_twice(self):
        listing = [dict(i=0, dir="alpha", name="4242.json", size=100, mtime=1.0),
                   dict(i=0, dir="alpha", name="9.json", size=100, mtime=1.0),
                   dict(i=0, dir="beta", name="10.json", size=100, mtime=1.0),
                   dict(i=0, dir="focus", name="11.json", size=100, mtime=1.0)]
        files = {ROOT + "/alpha/receipts/4242.json": json.dumps(receipt()).encode(),
                 ROOT + "/alpha/receipts/9.json": json.dumps(receipt(job=99)).encode(),     # names another job
                 ROOT + "/beta/receipts/10.json": json.dumps(receipt(job=10)).encode(),     # project != directory
                 ROOT + "/focus/receipts/11.json": json.dumps(receipt(job=11, via="fsubmit", project=None,
                                                                      card=None, focus="F-003")).encode()}
        summary = self.run_collect(listing, files)
        self.assertEqual(sorted(summary["stored"]), ["alpha/runs/gpu1-4242.json", "gamma/runs/gpu1-11.json"])
        self.assertEqual(len(summary["skipped"]), 2)
        stored = json.loads((self.repo / "projects/gamma/runs/gpu1-11.json").read_text())
        self.assertEqual((stored["project"], stored["focus"]), ("gamma", "F-003"))
        self.assertIn("collected_at", stored)
        again = self.run_collect(listing, files)
        self.assertEqual((again["stored"], again["skipped"]), ([], []))

    def test_unreachable_host_is_reported_not_fatal(self):
        with mock.patch.object(receipts, "launch_roots", lambda s: {"gpu1": [ROOT]}), \
                mock.patch.object(inspection, "json_lines", lambda *a, **k: None):
            self.assertEqual(receipts.collect(self.settings)["hosts"], {"gpu1": "unreachable"})


class UnrecordedTests(RepoTest):
    def setUp(self):
        super().setUp()
        receipts._unrecorded_cache.clear()
        self.settings = replace(self.settings, ssh_hosts=("gpu1",))
        self.card.write_bytes(SAMPLE + b'\n```probe-status\n{"host": "gpu1", "jobs": [7]}\n```\n')
        receipts.store(self.settings, receipts.validate(receipt(job=8)))

    def test_jobs_no_receipt_or_fence_names_are_listed_by_allocation(self):
        rows = [dict(job="7", state="COMPLETED", submit="2026-10-23T01:00:00", workdir="/x", name="a"),
                dict(job="8_0", state="COMPLETED", submit="2026-10-23T01:00:00", workdir="/x", name="b"),
                dict(job="9_0", state="COMPLETED", submit="2026-10-23T02:00:00", workdir=ROOT + "/alpha/stage/t", name="c"),
                dict(job="9_1", state="FAILED", submit="2026-10-23T02:00:00", workdir=ROOT + "/alpha/stage/t", name="c"),
                dict(job="10", state="RUNNING", submit="2026-10-23T03:00:00", workdir="/home/u/x", name="proto")]
        with mock.patch.object(receipts, "launch_roots", lambda s: {"gpu1": [ROOT]}), \
                mock.patch.object(inspection, "json_lines", lambda host, ch, items, **k: rows):
            result = receipts.unrecorded(self.settings, "2026-10-23")
        self.assertEqual(result["hosts"], {"gpu1": "ok"})
        self.assertEqual([j["job"] for j in result["jobs"]], [10, 9])
        nine = result["jobs"][1]
        self.assertEqual((nine["tasks"], nine["states"], nine["project"]), (2, {"COMPLETED": 1, "FAILED": 1}, "alpha"))
        self.assertIsNone(result["jobs"][0]["project"])

    def test_attach_records_after_the_fact(self):
        observed = ({10: dict(tasks={"10": dict(state="RUNNING", name="proto", start="2026-10-23T03:00:00",
                                                elapsed="", reason="")}, reduced="RUNNING")}, "ok")
        with mock.patch.object(inspection, "probe_jobs", lambda host, ids: observed):
            out = receipts.attach(self.settings, "gpu1", 10, "alpha", "cards/question.md", note="became the baseline")
        self.assertEqual((out["via"], out["card"], out["job_name"]), ("attach", "question.md", "proto"))
        self.assertTrue((self.repo / "projects/alpha/runs/gpu1-10.json").is_file())
        with mock.patch.object(inspection, "probe_jobs", lambda host, ids: observed):
            self.error(409, "already_recorded", receipts.attach, self.settings, "gpu1", 10, "alpha")
            self.error(403, "host_not_permitted", receipts.attach, self.settings, "gpu9", 10, "alpha")
            self.error(404, "unknown_card", receipts.attach, self.settings, "gpu1", 11, "alpha", "cards/nope.md")
        with mock.patch.object(inspection, "probe_jobs", lambda host, ids: ({}, "ok")):
            self.error(404, "unknown_job", receipts.attach, self.settings, "gpu1", 12, "alpha")
