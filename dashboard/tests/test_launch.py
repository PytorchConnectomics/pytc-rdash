import json
import subprocess
from dataclasses import replace
from unittest import mock

from dashboard.app import cards, launch
from dashboard.app.jobs import declared_status
from dashboard.tests.fixtures import RepoTest, SAMPLE

SCRIPT = "scripts/slurm/job.sbatch"
ROOT = "/srv/stage"
TREE = "a" * 40


def fence(**launch_block):
    body = {"schema_version": 1, "host": "gpu1", "launch": launch_block or {"script": SCRIPT}, "jobs": []}
    return "\n```probe-status\n" + json.dumps(body) + "\n```\n"


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class LaunchTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.settings = replace(self.settings, ssh_hosts=("gpu1",))

    def write(self, text):
        self.card.write_bytes(SAMPLE + text.encode())

    def run_launch(self, replies, owner="gpu1", **kwargs):
        calls = []

        def exchange(argv, payload, timeout=None, max_output=None):
            calls.append((argv[-1], payload))
            return replies.pop(0)
        with mock.patch.object(launch.inspection, "_exchange", exchange), \
                mock.patch.object(launch.inspection, "resolve_roots",
                                  lambda host, paths, timeout=30: tuple(paths)), \
                mock.patch.object(launch, "load_roots", lambda *a, **k: ((owner, ROOT),)), \
                mock.patch.object(launch, "committed_scripts",
                                  lambda repo, project, script, ref=None: ("0123456789ab", TREE, b"TAR")):
            return launch.launch(self.settings, "alpha", "question.md", **kwargs), calls

    def snapshot(self):
        return ("%s/alpha/stage/%s\n" % (ROOT, TREE)).encode()

    def test_validation_rejects_unsafe_declarations(self):
        for block in ({"script": "/abs/job.sbatch"}, {"script": "job.sbatch"}, {"script": "scripts/../x"},
                      {"script": "scripts//x"}, {"script": "scripts/a b"},
                      {"script": SCRIPT, "args": ["; rm -rf /"]}, {"script": SCRIPT, "args": "x"},
                      {"script": SCRIPT, "cwd": "~/x"}):
            with self.subTest(block=block):
                with self.assertRaises(launch.Error) as caught:
                    launch.declared_launch(fence(**block))
                self.assertEqual(caught.exception.status, 422)
        self.assertEqual(launch.declared_launch(fence(script=SCRIPT, args=["--x=1"]))["args"], ["--x=1"])

    def test_host_must_be_permitted(self):
        self.write(fence())
        self.settings = replace(self.settings, ssh_hosts=())
        self.error(403, "host_not_permitted", launch.launch, self.settings, "alpha", "question.md")

    def test_submit_stages_then_writes_receipt_not_card(self):
        self.write(fence())
        before = self.card.read_bytes()
        result, calls = self.run_launch([(b"", "ok"), (self.snapshot(), "ok"), (b"4242\n", "ok"), (b"stored\n", "ok")])
        stage_command, payload = calls[1]
        self.assertEqual(payload, b"TAR")
        self.assertIn("%s/alpha/stage/%s" % (ROOT, TREE), stage_command)
        self.assertIn("%s/alpha/results" % ROOT, stage_command)
        sbatch = calls[2][0]
        self.assertIn("umask 002", sbatch)
        self.assertIn("sbatch --parsable", sbatch)
        self.assertIn("RDASH_SNAPSHOT=%s/alpha/stage/%s" % (ROOT, TREE), sbatch)
        self.assertIn("RDASH_RESULTS=%s/alpha/results" % ROOT, sbatch)
        self.assertIn("--output=%s/alpha/results/slurm/%%x_%%j.out" % ROOT, sbatch)
        self.assertIn("%s/alpha/stage/%s/slurm/job.sbatch" % (ROOT, TREE), sbatch)
        self.assertIn("--comment=rdash:0123456789ab:" + TREE[:12], sbatch)
        self.assertEqual(result["job_id"], "4242")
        self.assertEqual(self.card.read_bytes(), before)
        put_command, payload = calls[3]
        self.assertIn("%s/alpha/receipts" % ROOT, put_command)
        self.assertIn("4242.json", put_command)
        receipt = json.loads(payload)
        self.assertEqual((receipt["job"], receipt["host"], receipt["via"]), (4242, "gpu1", "rsub"))
        self.assertEqual((receipt["project"], receipt["card"]), ("alpha", "question.md"))
        self.assertEqual(receipt["research"], {"ref": "HEAD", "revision": "0123456789ab", "scripts_tree": TREE})
        self.assertEqual(receipt["results"], "%s/alpha/results" % ROOT)
        self.assertEqual(result["receipt"], "%s/alpha/receipts/4242.json" % ROOT)

    def test_receipt_failure_still_reports_the_job(self):
        self.write(fence())
        with self.assertRaises(launch.Error) as caught:
            self.run_launch([(b"", "ok"), (self.snapshot(), "ok"), (b"4242\n", "ok"), (b"exists\n", "failed")])
        self.assertEqual(caught.exception.payload["error"], "unrecorded_job")
        self.assertEqual(caught.exception.payload["job_id"], "4242")
        self.assertIn("hub.sh attach gpu1 4242 alpha cards/question.md", caught.exception.payload["message"])

    def test_dirty_code_is_saved_as_a_patch_beside_the_receipt(self):
        self.write(fence(script=SCRIPT, cwd="/src/pytc"))
        state = json.dumps({"repo": True, "top": "/src/pytc", "commit": "b" * 40, "remote": "git@x:y.git",
                            "dirty": True, "patch_bytes": 9}).encode() + b"\n" + b"diff --x\n"
        result, calls = self.run_launch([(b"", "ok"), (self.snapshot(), "ok"), (state, "ok"), (b"4242\n", "ok"),
                                         (b"stored\n", "ok"), (b"stored\n", "ok")])
        self.assertIn("4242.patch", calls[4][0])
        self.assertEqual(calls[4][1], b"diff --x\n")
        receipt = json.loads(calls[5][1])
        self.assertEqual(receipt["code"]["commit"], "b" * 40)
        self.assertTrue(receipt["code"]["dirty"])
        self.assertEqual(receipt["code"]["patch"], "4242.patch")
        self.assertEqual(len(receipt["code"]["patch_sha256"]), 64)

    def test_on_its_own_host_the_launch_runs_without_ssh(self):
        self.write(fence())
        self.settings = replace(self.settings, ssh_hosts=(), host_alias="gpu1")
        result, calls = self.run_launch([(b"", "ok"), (self.snapshot(), "ok"), (b"4242\n", "ok"), (b"stored\n", "ok")],
                                        owner="local")
        self.assertTrue(result["local"])
        self.assertEqual(calls[0][0], "%i")          # argv itself, not an ssh command string
        self.assertNotIn("ssh", " ".join(str(c[0]) for c in calls))

    def test_card_can_be_read_from_a_git_ref(self):
        self.write(fence())
        with mock.patch.object(launch, "_git", lambda repo, *args, **kw: fence().replace("gpu1", "gpu9")):
            self.assertEqual(launch.declared_launch(launch.card_text(self.settings, "alpha", "question.md", "origin/main"))["host"], "gpu9")
        self.error(400, "invalid_ref", launch.card_text, self.settings, "alpha", "question.md", "-x;rm")

    def test_live_job_with_same_name_blocks_before_staging(self):
        self.write(fence())
        with self.assertRaises(launch.Error) as caught:
            self.run_launch([(b"4242\n", "ok")])
        self.assertEqual(caught.exception.payload["error"], "already_queued")

    def test_test_only_stages_but_records_nothing(self):
        self.write(fence())
        before = self.card.read_bytes()
        result, calls = self.run_launch([(b"", "ok"), (self.snapshot(), "ok"), (b"", "ok")], test_only=True)
        self.assertEqual(len(calls), 3)
        self.assertTrue(result["test_only"])
        self.assertIn("--test-only", calls[2][0])
        self.assertEqual(self.card.read_bytes(), before)

    def test_staging_failure_submits_nothing(self):
        self.write(fence())
        with self.assertRaises(launch.Error) as caught:
            self.run_launch([(b"", "ok"), (b"", "failed")])
        self.assertEqual(caught.exception.payload["error"], "staging_failed")
        self.assertEqual(declared_status(self.card.read_text())["jobs"], [])

    def test_ambiguous_sbatch_output_is_an_error_and_records_nothing(self):
        self.write(fence())
        with self.assertRaises(launch.Error) as caught:
            self.run_launch([(b"", "ok"), (self.snapshot(), "ok"), (b"Submitted batch job 7\n", "ok")])
        self.assertEqual(caught.exception.payload["error"], "ambiguous_submission")
        self.assertEqual(declared_status(self.card.read_text())["jobs"], [])



class StageScriptTests(RepoTest):
    """The STAGE shell script itself, against a real directory."""

    def stage(self, files):
        import io
        import tarfile
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w") as tar:
            for name, text in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(text)
                tar.addfile(info, io.BytesIO(text))
        target = self.root / "runs/p/stage/t"
        return subprocess.run(["sh", "-c", launch.STAGE, "rdash-stage", str(target), "rev1", str(self.root / "runs/p/results")],
                              input=data.getvalue(), capture_output=True), target

    def test_fresh_snapshot_is_marked_and_reused(self):
        result, target = self.stage({"job.sbatch": b"echo 1\n"})
        self.assertEqual(result.returncode, 0)
        self.assertEqual((target / ".rdash-complete").read_text(), "rev1\n")
        self.assertEqual(self.stage({"job.sbatch": b"echo changed\n"})[0].returncode, 0)   # never rewritten
        self.assertEqual((target / "job.sbatch").read_bytes(), b"echo 1\n")

    def test_unmarked_directory_is_reused_only_when_identical(self):
        target = self.root / "runs/p/stage/t"
        target.mkdir(parents=True)
        (target / "job.sbatch").write_bytes(b"echo 1\n")
        result, _ = self.stage({"job.sbatch": b"echo 1\n"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((target / ".rdash-complete").is_file())

    def test_unmarked_directory_that_differs_fails(self):
        target = self.root / "runs/p/stage/t"
        target.mkdir(parents=True)
        (target / "job.sbatch").write_bytes(b"echo other\n")
        (target / "out.log").write_bytes(b"x")
        result, _ = self.stage({"job.sbatch": b"echo 1\n"})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((target / ".rdash-complete").exists())
        self.assertEqual(sorted(p.name for p in target.parent.iterdir()), ["t"])   # no temp left behind


class CommittedScriptsTests(RepoTest):
    """Policy (b), against a real git repository."""

    def setUp(self):
        super().setUp()
        self.scripts = self.repo / "projects/alpha/scripts/slurm"
        self.scripts.mkdir(parents=True)
        (self.scripts / "job.sbatch").write_text("#!/bin/bash\necho hi\n")
        git(self.repo, "init", "-q")
        git(self.repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
        git(self.repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")

    def test_clean_tree_returns_its_hash_and_archive(self):
        revision, tree, archive = launch.committed_scripts(self.repo, "alpha", SCRIPT)
        self.assertRegex(tree, r"^[0-9a-f]{40}$")
        self.assertEqual(len(revision), 12)
        self.assertIn(b"slurm/job.sbatch", archive)

    def test_modified_or_untracked_scripts_are_refused(self):
        (self.scripts / "job.sbatch").write_text("#!/bin/bash\necho changed\n")
        self.error(409, "uncommitted_scripts", launch.committed_scripts, self.repo, "alpha", SCRIPT)
        git(self.repo, "checkout", "--", ".")
        (self.scripts / "helper.py").write_text("print(1)\n")
        self.error(409, "uncommitted_scripts", launch.committed_scripts, self.repo, "alpha", SCRIPT)

    def test_ref_reads_the_committed_tree_and_ignores_the_work_tree(self):
        (self.scripts / "job.sbatch").write_text("#!/bin/bash\necho uncommitted\n")
        revision, tree, archive = launch.committed_scripts(self.repo, "alpha", SCRIPT, "HEAD")
        self.assertRegex(tree, r"^[0-9a-f]{40}$")
        self.assertNotIn(b"uncommitted", archive)

    def test_script_missing_from_committed_tree_is_refused(self):
        self.error(422, "script_not_committed", launch.committed_scripts, self.repo, "alpha",
                   "scripts/slurm/other.sbatch")
