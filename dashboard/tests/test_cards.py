import concurrent.futures
import hashlib
import re
from unittest import mock

from fixtures import RepoTest, SAMPLE
from dashboard.app import cards
from dashboard.app.projects import discover, list_projects
from dashboard.app.safety import Error


class CardTests(RepoTest):
    def read(self):
        return cards.read_card(self.settings, "alpha", "question.md")

    def edit(self, **kwargs):
        return cards.edit_card(self.settings, "alpha", "question.md", self.read()["revision"], **kwargs)

    def test_track_is_optional(self):
        import re
        self.card.write_bytes(re.sub(rb"^track: .*\n", b"", SAMPLE, flags=re.M))
        record = cards.read_card(self.settings, "alpha", "question.md")
        self.assertFalse(record["read_only"], record.get("reason"))
        self.assertNotIn("track", record["metadata"])

    def test_frontmatter_rejections_are_read_only_and_unchanged(self):
        variants = [SAMPLE[4:], SAMPLE.replace(b"\n---\n\n", b"\n\n", 1)]
        bad_lines = [b" title: Bad", b"nocolon", b"# comment", b"", b"title: Duplicate", b"Bad: value",
                     b"extra: value # comment", b"extra: a: b", b"extra: 'unclosed", b'extra: "unclosed',
                     b"extra: 'a'b'", b'extra: "a"b"', b"extra: 'a\\b'", b"extra: " + b"a" * 201]
        bad_lines += [b"extra: " + value + b"thing" for value in (b"-", b"[", b"{", b"&", b"*", b"|", b">", b"!", b"?", b"%", b"@", b"`")]
        variants += [SAMPLE.replace(b"id: ALPHA-QUESTION", b"id: ALPHA-QUESTION\n" + line) for line in bad_lines]
        # `track` is optional (projects without tracks omit it), but never empty when present.
        variants += [re.sub(rb"^" + key + rb": .*\n", b"", SAMPLE, flags=re.M) for key in (b"id", b"title", b"project", b"stage", b"created", b"updated")]
        variants += [re.sub(rb"^" + key + rb": .*\n", key + b": " + empty + b"\n", SAMPLE, flags=re.M)
                     for key in (b"id", b"title", b"project", b"track", b"stage", b"created", b"updated")
                     for empty in (b"", b"   ", b"''", b'""', b"'   '")]
        variants += [SAMPLE.replace(b"stage: idea", b"stage: invalid"), SAMPLE.replace(b"project: alpha", b"project: beta"), b"\xff" + SAMPLE]
        for data in variants:
            with self.subTest(data=data[:100]):
                self.card.write_bytes(data)
                value = self.read()
                self.assertTrue(value["read_only"])
                self.assertTrue(value["reason"])
                for edit in ({"stage": "parked"}, {"text": "A note"}):
                    self.error(422, "unsupported_card", self.edit, **edit)
                    self.assertEqual(self.card.read_bytes(), data)

    def test_stage_preserves_body_bytes_and_quoting(self):
        data = SAMPLE.replace(b"stage: idea", b"stage: 'idea'").replace(b"updated: 2020-01-01", b'updated: "2020-01-01"').replace(b"\n", b"\r\n")
        self.card.write_bytes(data)
        self.edit(stage="probing")
        result = self.card.read_bytes()
        self.assertEqual(result.split(b"---", 2)[2], data.split(b"---", 2)[2])
        self.assertIn(b"stage: 'probing'\r\n", result)
        self.assertRegex(result, rb'updated: "\d{4}-\d{2}-\d{2}"\r\n')
        self.assertEqual(re.sub(rb"^(stage|updated): .*\r\n", b"", result, flags=re.M), re.sub(rb"^(stage|updated): .*\r\n", b"", data, flags=re.M))

    def test_discussion_position_validation_and_eof(self):
        self.edit(text="-- ## observation\nnext line")
        result = self.card.read_text()
        self.assertRegex(result, r"- second\n- \d{4}-\d{2}-\d{2} — rdash: observation next line\n\n## Next")
        for text in ("x" * 2001, "bad\x00", "bad\t", "bad\x7f", "bad\x85", "###", 10):
            before = self.card.read_bytes()
            self.error(400, "invalid_text", self.edit, text=text)
            self.assertEqual(before, self.card.read_bytes())
        for data, code in [(SAMPLE.replace(b"## Ideas and discussion", b"## Other"), "missing_section"), (SAMPLE + b"## Ideas and discussion\n", "ambiguous_section")]:
            self.card.write_bytes(data)
            self.error(422, code, self.edit, text="note")
            self.assertEqual(data, self.card.read_bytes())
        self.card.write_bytes(SAMPLE.split(b"## Ideas and discussion")[0] + b"## Ideas and discussion")
        self.edit(text="note")
        self.assertTrue(self.card.read_text().endswith("rdash: note\n"))

    def test_wrapped_bullet_is_not_split_by_a_new_note(self):
        """A wrapped bullet's continuation lines must stay attached to it."""
        from dashboard.app import cards
        body = ("---\nid: W-1\ntitle: Wrapped\nproject: alpha\ntrack: model\n"
                "stage: idea\ncreated: 2026-01-01\nupdated: 2026-01-01\n---\n\n"
                "## Ideas and discussion\n\n"
                "- 2026-01-01 - first line of a bullet that wraps\n"
                "  onto a continuation line that must not be orphaned.\n\n"
                "## Next decision\n\nDecide.\n")
        card = self.repo / "projects/alpha/cards/wrapped.md"
        card.write_bytes(body.encode())
        revision = cards.read_card(self.settings, "alpha", "wrapped.md")["revision"]
        cards.edit_card(self.settings, "alpha", "wrapped.md", revision, text="appended")
        lines = card.read_text().splitlines()
        first = lines.index("- 2026-01-01 - first line of a bullet that wraps")
        self.assertEqual(lines[first + 1],
                         "  onto a continuation line that must not be orphaned.",
                         "new note was spliced into the middle of a wrapped bullet")
        self.assertTrue(lines[first + 2].endswith("rdash: appended"))
        self.assertIn("## Next decision", lines)

    def test_idea_body_is_captured_and_replaces_the_placeholder(self):
        """The captured idea lands in the card; without one the template stands."""
        from dashboard.app import cards
        made = cards.create_idea(self.settings, "alpha", "Thin neurite recall",
                                 "model", idea="Try multiscale inference before more data.")
        text = (self.repo / "projects/alpha/cards" / made["card"]).read_text()
        self.assertIn("rdash: Try multiscale inference before more data.", text)
        self.assertNotIn("- YYYY-MM-DD", text)
        self.assertIn("## Ideas and discussion", text)
        self.assertIn("## Next decision", text)
        self.assertFalse(made["read_only"], made.get("reason"))
        self.assertEqual(made["metadata"]["stage"], "idea")

        plain = cards.create_idea(self.settings, "alpha", "No body supplied", "model")
        self.assertIn("- YYYY-MM-DD", (self.repo / "projects/alpha/cards" / plain["card"]).read_text())

        self.error(400, "invalid_idea", cards.create_idea, self.settings, "alpha",
                   "Empty idea", "model", "   ")
        self.error(400, "invalid_idea", cards.create_idea, self.settings, "alpha",
                   "Long idea", "model", "x" * 2001)

    def test_stale_revision_and_backup_collisions(self):
        old = self.read()["revision"]
        self.edit(stage="probing")
        after = self.card.read_bytes()
        exc = self.error(409, "stale_revision", cards.edit_card, self.settings, "alpha", "question.md", old, stage="parked")
        self.assertEqual(exc.payload["revision"], hashlib.sha256(after).hexdigest())
        self.assertEqual(self.card.read_bytes(), after)
        from dashboard.app import safety
        with mock.patch.object(safety, "datetime") as clock:
            clock.now.return_value.strftime.return_value = "20200101T000000Z"
            first = safety.backup(self.settings, "alpha", self.card)
            second = safety.backup(self.settings, "alpha", self.card)
        self.assertTrue(second.name.endswith("-1.md"))
        self.assertEqual(first.read_bytes(), after)
        self.assertIn(SAMPLE, [p.read_bytes() for p in self.cache.rglob("*.md")])

    def test_ideas_roundtrip_template_and_title_types(self):
        body = (self.repo / "dashboard/TEMPLATE.md").read_bytes().split(b"---", 2)[2]
        for title in ("A new idea", "héllo 世界", "\"Quotes\" and 'apostrophes'", "ratio: value # hash", "x" * 201, "(A title)"):
            result = cards.create_idea(self.settings, "beta", title)
            self.assertFalse(result["read_only"])
            self.assertEqual(result["metadata"]["track"], "model")
            self.assertLessEqual(len(result["metadata"]["title"]), 120)
            self.assertEqual((self.repo / "projects/beta/cards" / result["card"]).read_bytes().split(b"---", 2)[2], body)
        self.assertEqual(discover(self.settings, "alpha")[0], ["question.md"])
        for title in ("世界", "\nTitle", "bad\x00", "bad\x85", None, []):
            self.error(400, "invalid_title", cards.create_idea, self.settings, "alpha", title)
        for track in ("Bad", "x_y", "x" * 33, None, []):
            self.error(400, "invalid_track", cards.create_idea, self.settings, "alpha", "Title", track)

    def test_filename_and_project_wide_id_collisions(self):
        first = cards.create_idea(self.settings, "alpha", "New.idea_name")
        second = cards.create_idea(self.settings, "alpha", "New idea name")
        self.assertEqual(first["card"], "inbox/new-idea-name.md")
        self.assertEqual(second["card"], "inbox/new-idea-name-2.md")
        self.card.write_bytes(SAMPLE.replace(b"ALPHA-QUESTION", b"ALPHA-COLLISION") + b"invalid")
        result = cards.create_idea(self.settings, "alpha", "Collision")
        self.assertEqual(result["card"], "inbox/collision-2.md")
        self.card.write_bytes(b"---\nid: ALPHA-UNPARSEABLE\nunsupported\n---\n")
        self.assertEqual(cards.create_idea(self.settings, "alpha", "Unparseable")["card"], "inbox/unparseable-2.md")
        for i in range(1, 51):
            path = self.card.parent / ("occupied" + str(i) + ".md")
            path.write_text("---\nid: ALPHA-FULL" + ("-" + str(i) if i > 1 else "") + "\n---\n")
        self.error(409, "slug_exhausted", cards.create_idea, self.settings, "alpha", "Full")

    def test_link_failure_and_racing_filename(self):
        with mock.patch("dashboard.app.safety.os.link", side_effect=OSError("injected before publication")):
            with self.assertRaises(OSError):
                cards.create_idea(self.settings, "alpha", "Atomic")
        self.assertEqual(discover(self.settings, "alpha")[0], ["question.md"])
        self.assertEqual(list(self.card.parent.rglob(".rdash-*.tmp")), [])
        (self.card.parent / ".rdash-interrupted.tmp").write_text("partial")
        self.assertEqual(discover(self.settings, "alpha")[0], ["question.md"])
        original = cards.publish_link
        calls = []
        def race(path, data):
            calls.append(path)
            if len(calls) == 1:
                raise FileExistsError()
            return original(path, data)
        with mock.patch.object(cards, "publish_link", side_effect=race):
            self.assertEqual(cards.create_idea(self.settings, "alpha", "Race")["card"], "inbox/race-2.md")

    def test_eight_concurrent_revision_updates(self):
        revision = self.read()["revision"]
        def update(_):
            try:
                cards.edit_card(self.settings, "alpha", "question.md", revision, stage="probing")
                return 200
            except Error as exc:
                return exc.status
        with concurrent.futures.ThreadPoolExecutor(8) as pool:
            outcomes = list(pool.map(update, range(8)))
        self.assertEqual(outcomes.count(200), 1)
        self.assertTrue(all(status in (200, 409, 503) for status in outcomes))
        self.assertEqual(len(list(self.cache.rglob("*.md"))), 1)

    def test_discovery_registration_and_paths(self):
        (self.card.parent / "topic").mkdir()
        (self.card.parent / "topic/question.md").write_bytes(SAMPLE)
        (self.card.parent / "README.md").write_text("skip")
        (self.card.parent / ".hidden.md").write_text("skip")
        (self.card.parent / "data.json").write_text("ignored")
        (self.card.parent / "symlink.md").symlink_to(self.card)
        (self.repo / "projects/link").symlink_to(self.repo / "projects/alpha", target_is_directory=True)
        (self.repo / "projects/escape").symlink_to(self.root, target_is_directory=True)
        self.assertEqual(discover(self.settings, "alpha"), (["question.md"], 3))
        self.assertEqual([p["id"] for p in list_projects(self.settings)], ["alpha", "beta"])
        for ref in ("..", "/question.md", "inbox/../..", "topic/question.md", "symlink.md"):
            with self.assertRaises(Error):
                cards.read_card(self.settings, "alpha", ref)
        self.error(404, "unknown_project", cards.list_cards, self.settings, "unknown")


class JobFenceTests(RepoTest):
    """Job IDs reach a subprocess argv, so parsing must be strict."""

    def setUp(self):
        super().setUp()
        from unittest import mock
        from dashboard.app import inspection
        def channel(host, channel, items, **kwargs):
            self.assertEqual(channel, 'jobs')
            rows = inspection.scheduler(items)
            return [rows.get(str(i), dict(tasks={}, reduced='unknown')) for i in items], 'ok'
        patcher = mock.patch.object(inspection, '_channel', side_effect=channel)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_declared_jobs_accepts_only_plain_positive_integers(self):
        from dashboard.app.jobs import declared_jobs
        fence = '```probe-status\n{"schema_version": 1, "jobs": %s}\n```\n'
        self.assertEqual(declared_jobs(fence % '[3013750, "3013760"]'), [3013750, 3013760])
        # Shell metacharacters, negatives, booleans and floats are all dropped.
        self.assertEqual(declared_jobs(fence % '["1;rm -rf /", -5, true, 1.5, "0"]'), [])
        self.assertEqual(declared_jobs(fence % '[7, 7, 7]'), [7])
        self.assertEqual(declared_jobs(fence % '["999999999999999"]'), [])
        self.assertEqual(declared_jobs('```probe-status\nnot json\n```\n'), [])
        self.assertEqual(declared_jobs('no fence at all'), [])
        self.assertEqual(declared_jobs(''), [])

    def test_declared_sessions_reads_an_attachment_not_a_live_process(self):
        from dashboard.app.jobs import declared_sessions
        fence = '```probe-status\n{"schema_version": 1, "sessions": %s}\n```\n'
        read = declared_sessions(fence % '[{"provider": "claude", "label": "Sweep mt per model", "host": "bc"}]')
        self.assertEqual(read["declared"], True)
        self.assertEqual(read["items"], [dict(label="Sweep mt per model", provider="claude", host="bc")])
        # A declaration never carries liveness: the reader must not invent one.
        self.assertNotIn("process_state", read["items"][0])
        self.assertNotIn("running", read)
        # The label is the whole point of the column, so an entry without one is dropped.
        self.assertEqual(declared_sessions(fence % '[{"provider": "claude"}, {"label": 12}, "claude"]')["items"], [])
        self.assertEqual(declared_sessions(fence % '[{"label": "x", "host": "bc; rm -rf /"}]')["items"],
                         [dict(label="x")])
        self.assertEqual(declared_sessions(fence % '{"label": "not a list"}')["declared"], False)
        self.assertEqual(declared_sessions('```probe-status\nnot json\n```\n')["declared"], False)
        self.assertEqual(declared_sessions('')["items"], [])

    def test_method_steps_read_the_card_and_never_invent_a_status(self):
        from dashboard.app.contract import method_reference, method_tasks
        card = "card.md"
        body = ('```probe-contract\n{"references": {"method": "cards/card.md#decision-procedure"}}\n```\n'
                "## Decision procedure\n\n"
                "### 1. With GT — decide it on `ExPID82_1` val\n\nprose\n\n"
                "### 2. Without GT — [inference](../spec.md#tasks) only\n\n"
                "#### 3. a numbered note nested inside step 2\n\n"
                "### Traps that silently produce garbage\n\nprose\n\n"
                "## Acceptance\n\n### 9. not under the method section\n")
        reference, anchor = method_reference(body, card)
        self.assertEqual(reference, "cards/card.md#decision-procedure")
        self.assertEqual(anchor, "decision-procedure")
        steps = method_tasks(body, anchor)
        # Backticked identifiers survive; unnumbered subsections are prose, not work;
        # a deeper numbered heading is detail inside a step, not a step beside it;
        # the section ends at the next same-level heading.
        self.assertEqual(steps, ["With GT — decide it on ExPID82_1 val",
                                 "Without GT — inference only"])
        # Nothing here claims a step is done, current or blocked.
        self.assertTrue(all(isinstance(step, str) for step in steps))

    def test_method_kept_outside_the_card_is_referenced_not_restated(self):
        from dashboard.app.contract import method_reference, method_tasks
        fence = '```probe-contract\n{"references": {"method": %s}}\n```\n## Decision procedure\n\n### 1. Step\n'
        reference, anchor = method_reference(fence % '"../../probe/protocol/PROBE_PROTOCOL.md#loop"', "card.md")
        self.assertEqual(reference, "../../probe/protocol/PROBE_PROTOCOL.md#loop")
        self.assertIsNone(anchor)
        self.assertEqual(method_tasks(fence, anchor), [])
        # A reference with no anchor points at a file, not a section: nothing to read.
        self.assertEqual(method_reference(fence % '"cards/card.md"', "card.md"), ("cards/card.md", None))
        self.assertEqual(method_reference(fence % "12", "card.md"), (None, None))
        self.assertEqual(method_reference('```probe-contract\nnot json\n```\n', "card.md"), (None, None))
        self.assertEqual(method_reference("no fence", "card.md"), (None, None))

    def test_method_steps_fall_back_to_an_ordered_list_and_skip_fenced_text(self):
        from dashboard.app.contract import method_tasks
        body = ("## Decision procedure\n\n"
                "1. Decode both models\n"
                "2. Score at each model's own threshold\n\n"
                "```sh\n3. this is a code sample, not a step\n```\n")
        self.assertEqual(method_tasks(body, "decision-procedure"),
                         ["Decode both models", "Score at each model's own threshold"])
        self.assertEqual(method_tasks(body, None), [])
        self.assertEqual(method_tasks("## Other\n\n1. x\n", "decision-procedure"), [])

    def test_missing_scheduler_reports_unknown_never_a_guess(self):
        from dashboard.app import inspection as jobs
        jobs._cache.clear()
        original = jobs._run
        jobs._run = lambda command: None          # scheduler absent or failing
        try:
            self.assertEqual(jobs.states_for([11, 12]), {11: "unknown", 12: "unknown"})
            records = [{"card": "a.md", "job_ids": [11]}, {"card": "b.md", "job_ids": []}]
            annotated = jobs.annotate(records)
        finally:
            jobs._run = original
            jobs._cache.clear()
        self.assertEqual(annotated[0]["jobs"], [{"id": 11, "state": "unknown"}])
        self.assertEqual(annotated[1]["jobs"], [])
        self.assertNotIn("job_ids", annotated[0])

    def test_real_sacct_output_does_not_hide_a_failure(self):
        """Verbatim SLURM 23.11.10 output: .extern reports COMPLETED for a FAILED job."""
        from dashboard.app import inspection as jobs
        jobs._cache.clear()
        real = ("3013750|FAILED\n3013750.batch|FAILED\n3013750.extern|COMPLETED\n"
                "3013760_0|COMPLETED\n3013760_0.batch|COMPLETED\n3013760_0.extern|COMPLETED\n"
                "3013760_1|COMPLETED\n3013760_1.batch|COMPLETED\n3013760_1.extern|COMPLETED\n"
                "3013899|RUNNING\n3013899.batch|RUNNING\n3013899.extern|RUNNING\n")
        original = jobs._run
        jobs._run = lambda c: real if c[0] == "sacct" else "3013899 RUNNING\n"
        try:
            got = jobs.states_for([3013750, 3013760, 3013899])
        finally:
            jobs._run = original
            jobs._cache.clear()
        self.assertEqual(got[3013750], "FAILED", "the .extern step hid a real failure")
        self.assertEqual(got[3013760], "COMPLETED")
        self.assertEqual(got[3013899], "RUNNING")

    def test_array_with_one_live_task_is_not_reported_completed(self):
        from dashboard.app import inspection as jobs
        jobs._cache.clear()
        original = jobs._run
        jobs._run = lambda c: ("500_0|COMPLETED\n500_1|RUNNING\n501_0|COMPLETED\n501_1|FAILED\n"
                               if c[0] == "sacct" else "")
        try:
            got = jobs.states_for([500, 501])
        finally:
            jobs._run = original
            jobs._cache.clear()
        self.assertEqual(got[500], "RUNNING")
        self.assertEqual(got[501], "FAILED")

    def test_job_name_is_read_from_either_source_without_shifting_columns(self):
        from dashboard.app import inspection as jobs
        jobs._cache.clear()
        original = jobs._run
        def fake(command):
            if command[0] == "sacct":
                return "500|COMPLETED|00:14:31|2026-09-29T10:00:00|2026-09-29T10:14:31|decode_eb8\n"
            # squeue puts reason before the name, and a name may contain the
            # separator: the tail belongs to the name, not to a later column.
            return "501|RUNNING|0:11|2026-09-29T10:20:00|c154|sweep|mt\n"
        jobs._run = fake
        try:
            got = jobs.scheduler([500, 501])
        finally:
            jobs._run = original
            jobs._cache.clear()
        self.assertEqual(got["500"]["tasks"]["500"],
                         dict(state="COMPLETED", elapsed="00:14:31", reason="", start="2026-09-29T10:00:00",
                              end="2026-09-29T10:14:31", name="decode_eb8"))
        self.assertEqual(got["501"]["tasks"]["501"],
                         dict(state="RUNNING", elapsed="0:11", reason="c154", start="2026-09-29T10:20:00",
                              end="", name="sweep|mt"))

    def test_absent_job_name_is_empty_never_the_literal_null(self):
        from dashboard.app import inspection as jobs
        self.assertEqual(jobs.clean_name("(null)"), "")
        self.assertEqual(jobs.clean_name("  run\x00_a  "), "run_a")
        self.assertEqual(len(jobs.clean_name("x" * 200)), jobs.NAME_LIMIT)

    def test_sacct_steps_collapse_to_the_parent_job(self):
        from dashboard.app import inspection as jobs
        jobs._cache.clear()
        original = jobs._run
        def fake(command):
            if command[0] == "sacct":
                return "3013750|COMPLETED\n3013750.batch|COMPLETED\n3013760|FAILED\n"
            return "3013899 RUNNING\n"
        jobs._run = fake
        try:
            got = jobs.states_for([3013750, 3013760, 3013899, 4000000])
        finally:
            jobs._run = original
            jobs._cache.clear()
        self.assertEqual(got, {3013750: "COMPLETED", 3013760: "FAILED",
                               3013899: "RUNNING", 4000000: "unknown"})
