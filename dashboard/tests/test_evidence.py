import hashlib
import json
import struct
from dataclasses import replace
from datetime import datetime, timezone
from unittest import mock
import zlib

from fixtures import RepoTest
from dashboard.app import cards, evidence, inspection


def png(width=1, height=1):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


class EvidenceTests(RepoTest):
    def setUp(self):
        super().setUp()
        self.settings = replace(self.settings, stat_local=True)
        self.directory = self.repo / "projects/alpha/results"
        self.directory.mkdir()
        self.artifact = self.directory / "qc.txt"
        self.artifact.write_text("Inspect the merge near the boundary.\n")
        self.declare()

    def declare(self, path=None, host=None):
        value = dict(artifacts={"QC": str(path or self.artifact)})
        if host is not None:
            value["host"] = host
        self.card.write_text(self.card.read_text().split("```probe-status")[0] +
                             "```probe-status\n" + json.dumps(value) + "\n```\n")
        self.revision = cards.read_card(self.settings, "alpha", "question.md")["revision"]

    def preview(self, **changes):
        request = dict(project="alpha", card="question.md", revision=self.revision, label="QC")
        request.update(changes)
        return evidence.preview(self.settings, **request)

    def feedback(self, receipt=None, **changes):
        receipt = receipt or self.preview()
        request = dict(project="alpha", card="question.md", revision=self.revision, label="QC",
                       artifact_revision=receipt["artifact_revision"], text="Check the highlighted merge.")
        request.update(changes)
        return evidence.feedback(self.settings, request)

    def test_text_preview_reads_exact_bytes_without_changing_card(self):
        original = self.card.read_bytes()
        result = self.preview()
        self.assertEqual(result["text"], self.artifact.read_text())
        self.assertEqual(result["artifact_revision"], hashlib.sha256(self.artifact.read_bytes()).hexdigest())
        self.assertEqual((result["kind"], result["mime"], result["host"]), ("text", "text/plain", "local"))
        self.assertIsInstance(result["observed_at"], float)
        self.assertEqual(self.card.read_bytes(), original)

    def test_images_use_same_origin_digest_bound_content_url(self):
        image = self.directory / "qc.png"
        image.write_bytes(png())
        self.declare(image)
        result = self.preview()
        self.assertEqual((result["kind"], result["mime"]), ("image", "image/png"))
        self.assertIn("artifact_revision=" + result["artifact_revision"], result["content_url"])
        self.assertTrue(result["content_url"].startswith("/api/evidence/content?"))
        self.assertEqual(evidence.content(self.settings, "alpha", "question.md", self.revision, "QC", result["artifact_revision"]),
                         (image.read_bytes(), "image/png"))
        image.write_bytes(png(2, 1))
        self.error(409, "stale_artifact", evidence.content, self.settings, "alpha", "question.md", self.revision, "QC", result["artifact_revision"])

    def test_unsupported_formats_are_not_read_or_executed(self):
        for suffix in ("html", "svg", "pdf", "py", "sh"):
            path = self.directory / ("qc." + suffix)
            path.write_text("<script>alert('not rendered')</script>")
            self.declare(path)
            with mock.patch.object(inspection, "read_files") as reader:
                self.error(415, "unsupported_format", self.preview)
                reader.assert_not_called()

    def test_invalid_images_and_excessive_dimensions(self):
        for suffix, content in (("png", b"not an image"), ("jpg", b"\xff\xd8bad\xff\xd9"), ("png", png()[:-1])):
            path = self.directory / ("qc." + suffix)
            path.write_bytes(content)
            self.declare(path)
            self.error(422, "invalid_image", self.preview)
        path.write_bytes(png(65535, 65535))
        self.error(422, "image_dimensions", self.preview)

    def test_invalid_utf8_binary_text_and_json(self):
        for content in (b"\xff", b"nul\x00byte"):
            self.artifact.write_bytes(content)
            self.error(422, "invalid_text", self.preview)
        path = self.directory / "qc.json"
        self.declare(path)
        for content in ("not json", '{"score":NaN}', "[" * 2000 + "]" * 2000):
            path.write_text(content)
            self.error(422, "invalid_text", self.preview)
        path.write_text('{"score": 0.75}')
        self.assertEqual(self.preview()["text"], path.read_text())

    def test_missing_oversized_and_nonregular_artifacts(self):
        self.artifact.unlink()
        self.error(404, "evidence_unavailable", self.preview)
        self.artifact.write_bytes(b"x" * (inspection.MAX_CONTENT_FILE + 1))
        error = self.error(413, "evidence_unavailable", self.preview)
        self.assertEqual(error.payload["reason"], "too_large")
        self.artifact.unlink()
        self.artifact.mkdir()
        self.error(403, "evidence_unavailable", self.preview)

    def test_paths_must_be_declared_and_within_project_roots(self):
        self.error(404, "unknown_artifact", self.preview, label=str(self.artifact))
        outside = self.root / "secret.txt"
        outside.write_text("outside project")
        self.declare(outside)
        error = self.error(403, "evidence_unavailable", self.preview)
        self.assertEqual(error.payload["reason"], "outside declared roots")
        self.declare(self.repo / "projects/beta/results/other.txt")
        self.error(403, "evidence_unavailable", self.preview)
        self.declare(self.directory / "../cards/question.md")
        self.error(403, "evidence_unavailable", self.preview)

    def test_symlink_file_and_intermediate_directory_are_refused(self):
        alias = self.directory / "alias.txt"
        alias.symlink_to(self.artifact)
        self.declare(alias)
        self.error(403, "evidence_unavailable", self.preview)
        folder = self.directory / "linked"
        folder.symlink_to(self.directory, target_is_directory=True)
        self.declare(folder / "qc.txt")
        self.error(403, "evidence_unavailable", self.preview)

    def test_host_and_stat_root_permissions_fail_before_remote_read(self):
        self.declare(host="not-approved")
        with mock.patch.object(inspection, "read_files") as reader:
            self.error(403, "host_not_permitted", self.preview)
            reader.assert_not_called()
        self.declare(host="bad;touch marker")
        self.error(403, "invalid_host", self.preview)
        self.declare()
        self.settings = replace(self.settings, stat_local=False)
        self.error(403, "local_stat_disabled", self.preview)
        self.settings = replace(self.settings, stat_local=True, stat_roots=(str(self.root / "elsewhere"),))
        self.error(403, "path_not_permitted", self.preview)

    def test_remote_reads_use_configured_roots_and_no_cached_bytes(self):
        self.settings = replace(self.settings, ssh_hosts=("gpu",), result_roots=(("gpu", "/runs"),))
        self.declare("/runs/qc.txt", host="gpu")
        raw = b"remote evidence"
        observation = {"/runs/qc.txt": dict(state="present", data=raw, size=len(raw), mtime=1)}
        with mock.patch.object(inspection, "read_files", return_value=(observation, "ok")) as reader:
            result = self.preview()
            reader.assert_called_once_with("gpu", ["/runs/qc.txt"], ("/runs",))
        self.assertEqual(result["text"], raw.decode())
        self.assertEqual(result["host"], "gpu")
        with mock.patch.object(inspection, "read_files", return_value=({"/runs/qc.txt": dict(state="unknown", reason="host_unreachable")}, "unreachable")):
            self.error(503, "evidence_unavailable", self.preview)

    def test_stale_card_before_and_during_read_is_rejected(self):
        self.card.write_text(self.card.read_text() + "\nchanged\n")
        self.error(409, "stale_revision", self.preview)
        self.declare()
        original = inspection.read_files
        def read_and_edit(*args, **kwargs):
            value = original(*args, **kwargs)
            self.card.write_text(self.card.read_text() + "\nchanged during read\n")
            return value
        with mock.patch.object(inspection, "read_files", side_effect=read_and_edit):
            self.error(409, "stale_revision", self.preview)

    def test_feedback_records_provenance_without_acceptance_or_verdict_changes(self):
        self.card.write_text(self.card.read_text().replace("stage: idea", "stage: idea\nverdict: open") +
                             "\n## Acceptance\n- [ ] Check boundary\n")
        self.declare()
        # Preserve the authored acceptance section when redeclaring the status fence.
        self.card.write_text(self.card.read_text() + "\n## Acceptance\n- [ ] Check boundary\n")
        self.revision = cards.read_card(self.settings, "alpha", "question.md")["revision"]
        receipt = self.preview()
        before = cards.read_card(self.settings, "alpha", "question.md")
        result = self.feedback(receipt, text="Check the merge.\n## Acceptance\n- [x] injected")
        self.assertEqual(result["acceptance"], before["acceptance"])
        self.assertEqual(result["verdict"], "open")
        self.assertEqual(result["metadata"]["stage"], "idea")
        self.assertIn("Evidence feedback ", result["body"])
        self.assertIn("(needs follow-up)", result["body"])
        self.assertIn(receipt["artifact_revision"], result["body"])
        self.assertIn(self.revision, result["body"])
        self.assertIn(str(self.artifact), result["body"])
        self.assertIn('"host": "local"', result["body"])

    def test_feedback_rejects_changed_artifact_even_with_same_size_and_mtime(self):
        receipt = self.preview()
        original = self.card.read_bytes()
        st = self.artifact.stat()
        self.artifact.write_text("X" * st.st_size)
        import os
        os.utime(self.artifact, ns=(st.st_atime_ns, st.st_mtime_ns))
        self.error(409, "stale_artifact", self.feedback, receipt)
        self.assertEqual(self.card.read_bytes(), original)

    def test_feedback_rejects_stale_card_and_invalid_payloads(self):
        receipt = self.preview()
        self.card.write_text(self.card.read_text() + "\nchanged\n")
        self.error(409, "stale_revision", self.feedback, receipt)
        for value in (None, "", "x" * 1001, "bad\x00note"):
            self.error(400, "invalid_text", self.feedback, receipt, text=value)
        self.error(400, "invalid_artifact_revision", self.feedback, receipt, artifact_revision="forged")

    def test_feedback_cannot_change_card_after_a_concurrent_edit(self):
        receipt = self.preview()
        original = cards.edit_card
        def concurrent(*args, **kwargs):
            self.card.write_text(self.card.read_text() + "\nconcurrent note\n")
            return original(*args, **kwargs)
        with mock.patch.object(cards, "edit_card", side_effect=concurrent):
            self.error(409, "stale_revision", self.feedback, receipt)
        self.assertNotIn("Evidence feedback", self.card.read_text())

    def test_feedback_respects_existing_project_lock(self):
        receipt = self.preview()
        lock = self.card.parent.parent / ".agent-lock"
        lock.write_text(json.dumps(dict(session_id="another-session", started=datetime.now(timezone.utc).isoformat())))
        self.error(423, "project_locked", self.feedback, receipt)
