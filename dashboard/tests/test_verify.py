"""Reject invalid evidence even when execution appears to have succeeded."""
import copy
import json
import os
from unittest import mock

from supervisor_fixtures import SupervisorTest
from dashboard.supervisor import verify, observe


class VerificationTests(SupervisorTest):
    def setUp(self):
        super().setUp()
        self.assignments["a"].update(step="tissue", source_shape=[16, 20, 24], downsample=4,
                                      acceptance=list(verify.CHECKS))
        self.update_snapshot()
        self.output = self.root / "tissue.h5"
        self.output.write_bytes(b"fixture output")
        self.row = self.reserve(outputs=[dict(name="tissue_ds", path=str(self.output), min_size=1)])
        self.store.confirm_submittable(self.row["request_id"])
        observe.adopt(self.store, self.row["request_id"], "123")
        self.row = self.store.dispatch(self.row["request_id"])
        self.receipt = dict(schema=1, request_id=self.row["request_id"], attempt=self.row["attempt"],
                            goal=self.goal, assignment="a", job_name=self.row["job_name"], slurm_job_id="123",
                            command=self.row["command"], inputs={}, parameters={}, outputs=[verify.digest(self.output)],
                            exit_code=0, summary=dict(dataset="main", rank=3, dtype="uint8", shape=[4, 5, 6]))
        self.path = self.root / "receipt.json"

    def observer(self, host, paths):
        return {p: dict(state="present", kind="file", size=os.stat(p).st_size, mtime=os.stat(p).st_mtime) for p in paths}, "ok"

    def check(self, receipt=None):
        return verify.check_receipt(self.row, self.assignments["a"], receipt or self.receipt, self.observer)

    def test_valid_and_identity_mismatches(self):
        self.assertTrue(all(self.check().values()))
        for field in ("request_id", "job_name", "command", "attempt", "slurm_job_id", "goal"):
            changed = copy.deepcopy(self.receipt)
            changed[field] = "wrong"
            self.assertFalse(self.check(changed)["receipt_identity"], field)
        changed = copy.deepcopy(self.receipt)
        changed["outputs"][0]["path"] += "-wrong"
        self.assertFalse(self.check(changed)["receipt_identity"])

    def test_freshness_input_parameters_and_structure(self):
        os.utime(self.output, (999, 999))
        self.receipt["outputs"] = [verify.digest(self.output)]
        self.assertFalse(self.check()["outputs_present"])
        self.receipt["inputs"] = {"wrong": {}}
        self.assertFalse(self.check()["inputs_match"])
        self.receipt["parameters"] = dict(pct=98)
        self.assertFalse(self.check()["params_authorized"])
        for update in (dict(rank=2), dict(dtype="float32"), dict(shape=[4, 5, 7])):
            changed = copy.deepcopy(self.receipt)
            changed["summary"].update(update)
            self.assertFalse(self.check(changed)["structure"])

    def test_calibration_key_set_and_nonfinite_cut(self):
        self.assignments["a"].update(step="calibrate", volume="fixture")
        self.row["parameters"] = dict(pct=99.0)
        self.receipt["parameters"] = dict(pct=99.0)
        self.row["outputs_declared"][0]["name"] = "calib"
        value = {k: 1 for k in verify.CALIB_KEYS}
        value.update(vol="fixture", shape=[16, 20, 24], pct=99.0, cut=.05)
        for cut, expected in ((.05, True), (float("nan"), False), (float("inf"), False), (0, False), (1, False)):
            value["cut"] = cut
            self.output.write_text(json.dumps(value))
            self.receipt["outputs"] = [verify.digest(self.output)]
            self.assertEqual(self.check()["structure"], expected)
        del value["sigmas"]
        value["cut"] = .05
        self.output.write_text(json.dumps(value))
        self.receipt["outputs"] = [verify.digest(self.output)]
        self.assertFalse(self.check()["structure"])

    def test_once_only_import_conflict_and_complete_gate(self):
        self.path.write_text(json.dumps(self.receipt))
        for _ in range(2):
            self.assertEqual(verify.import_receipt(self.store, self.row, self.assignments["a"], self.path, self.observer), "verified")
        self.assertEqual(len(self.store.rows("SELECT * FROM receipts")), 1)
        self.error(409, "already_verified", self.reserve)
        self.receipt["exit_code"] = 1
        self.path.write_text(json.dumps(self.receipt))
        self.assertEqual(verify.import_receipt(self.store, self.row, self.assignments["a"], self.path, self.observer), "conflict")
        self.assertEqual(self.store.rows("SELECT verdict FROM receipts")[0]["verdict"], "conflict")

    def test_complete_without_evidence_raises_decision(self):
        self.error(409, "outstanding_dispatches", verify.complete, self.store, self.goal, self.generation, self.revision)
        self.assertEqual(self.store.balance(self.goal)["phase"], "decision_required")
        self.assertEqual(len(self.store.rows("SELECT * FROM decisions")), 1)

    def test_worker_publishes_failure_receipt_without_running_science(self):
        from dashboard.supervisor import receipt
        manifest = dict(self.row, output_dir=str(self.root / "out"), receipt_path=str(self.path),
                        step="tissue", assignment_record=self.assignments["a"])
        path = self.root / "dispatch.json"
        path.write_text(json.dumps(manifest))
        with mock.patch.object(receipt.subprocess, "run", return_value=mock.Mock(returncode=2)) as run:
            result = receipt.run(path, lambda record: {})
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(self.path.read_text())["exit_code"], 2)
        self.assertEqual(run.call_count, 1)

    def test_bad_json_is_rejected_evidence_not_a_success_or_unhandled_error(self):
        self.path.write_bytes(b"{broken")
        self.assertEqual(verify.import_receipt(self.store, self.row, self.assignments["a"], self.path, self.observer), "rejected")
