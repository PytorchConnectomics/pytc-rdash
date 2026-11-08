"""CLI boundary checks, plus explicitly configured real-evaluator integration."""

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ADAPTER = Path(__file__).resolve().parents[1] / "examples" / "nisb" / "nerl_adapter.py"


class AdapterBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.code = self.root / "pytc"
        source = self.code / "connectomics" / "metrics" / "nerl.py"
        source.parent.mkdir(parents=True)
        # An import tripwire, never a replacement/mock scorer.
        source.write_text("raise RuntimeError('inspection imported the evaluator')\n")

    def tearDown(self):
        self.temp.cleanup()

    def call(self, *args, no_site=True, adapter=ADAPTER):
        command = [sys.executable] + (["-S"] if no_site else [])
        result = subprocess.run(
            command + [str(adapter), "--code-repo", str(self.code), *map(str, args)],
            text=True, capture_output=True, check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=30,
        )
        return result, json.loads(result.stdout)

    def test_inspection_does_not_import_or_write(self):
        backend = self.root / "backend" / "em_erl"
        backend.mkdir(parents=True)
        (backend / "__init__.py").write_text("raise RuntimeError('backend imported')\n")
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        process, receipt = self.call("--backend-repo", backend.parent)
        after = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(receipt["execution"]["status"], "not_run")
        self.assertEqual(receipt["checks"], [])
        self.assertEqual(receipt["scientific_verdict"], "not_evaluated")
        self.assertEqual(before, after)

    def test_unavailable_backend_is_error_not_a_pass(self):
        process, receipt = self.call("--run")
        self.assertEqual(process.returncode, 2)
        self.assertIn("em_erl", receipt["readiness"]["missing"])
        self.assertEqual(receipt["execution"]["status"], "error")
        self.assertEqual(receipt["validity"]["status"], "unknown")
        self.assertFalse(receipt["baseline_reproduced"])

    def test_existing_receipt_is_refused_before_execution(self):
        target = self.root / "receipt.json"
        target.write_text("keep this exact original")
        process, receipt = self.call("--run", "--receipt", target)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(receipt["error"]["type"], "FileExistsError")
        self.assertEqual(target.read_text(), "keep this exact original")

    def test_malformed_receipt_has_structured_error(self):
        target = self.root / "bad.json"
        target.write_text("[]")
        process, receipt = self.call("--verify-receipt", target)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(receipt["validity"]["status"], "unknown")

    def test_empty_fixture_cannot_pass_run_or_verification(self):
        adapter = self.root / "nerl_adapter.py"
        adapter.write_bytes(ADAPTER.read_bytes())
        (self.root / "fixtures.json").write_text('{"checks": []}')
        receipt_path = self.root / "receipt.json"
        receipt_path.write_text("{}")
        for mode in [("--run",), ("--verify-receipt", receipt_path)]:
            with self.subTest(mode=mode):
                process, receipt = self.call(*mode, adapter=adapter)
                self.assertEqual(process.returncode, 2)
                self.assertEqual(receipt["execution"]["status"], "error")
                self.assertIn("nonempty checks", receipt["error"]["message"])


@unittest.skipUnless(os.environ.get("NERL_TEST_CODE_REPO") and os.environ.get("NERL_TEST_BACKEND_REPO"),
                     "Set both NERL_TEST_* source paths to opt in to real CPU scoring")
class RealEvaluatorIntegration(unittest.TestCase):
    def test_actual_scores_receipt_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "receipt.json"
            command = [sys.executable, str(ADAPTER), "--code-repo", os.environ["NERL_TEST_CODE_REPO"],
                       "--backend-repo", os.environ["NERL_TEST_BACKEND_REPO"]]
            env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            run = subprocess.run(command + ["--run", "--receipt", str(target)],
                                 text=True, capture_output=True, env=env, timeout=60)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            receipt = json.loads(target.read_text())
            self.assertEqual(len(receipt["checks"]), 5)
            self.assertTrue(all(check["pass"] for check in receipt["checks"]))
            self.assertTrue(receipt["sources_stable"])
            check = subprocess.run(command + ["--verify-receipt", str(target)],
                                   text=True, capture_output=True, env=env, timeout=30)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            receipt["checks"][0]["observed"]["nerl"] = 0.25
            target.write_text(json.dumps(receipt))
            changed = subprocess.run(command + ["--verify-receipt", str(target)],
                                     text=True, capture_output=True, env=env, timeout=30)
            self.assertEqual(changed.returncode, 1)
            self.assertFalse(json.loads(changed.stdout)["receipt_integrity"])
            # Even re-checksumming a changed result must not preserve a bogus pass.
            receipt.pop("receipt_sha256")
            blob = json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            receipt["receipt_sha256"] = hashlib.sha256(blob).hexdigest()
            target.write_text(json.dumps(receipt))
            inconsistent = subprocess.run(command + ["--verify-receipt", str(target)],
                                          text=True, capture_output=True, env=env, timeout=30)
            report = json.loads(inconsistent.stdout)
            self.assertEqual(inconsistent.returncode, 1)
            self.assertTrue(report["receipt_integrity"])
            self.assertFalse(report["check_results_consistent"])


if __name__ == "__main__":
    unittest.main()
