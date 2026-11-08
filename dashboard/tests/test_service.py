"""Test restart safety and dependent continuation with synthetic receipts only."""
import json
from unittest import mock

from supervisor_fixtures import SupervisorTest
from dashboard.supervisor import goals, service, verify
from dashboard.supervisor.store import Error, encode


class ServiceTests(SupervisorTest):
    def make_service(self, provider=None, scheduler=None):
        instance = service.Service(self.settings, provider or mock.Mock(), scheduler or mock.Mock(), self.store,
                                   probe=lambda host, ids: ({i: dict(reduced="COMPLETED") for i in ids}, "ok"))
        self.addCleanup(instance.close)
        return instance

    def test_missing_and_corrupt_store_refuse_outstanding_projection(self):
        row = self.reserve()
        goals.publish(self.settings, self.store, "alpha", "demo", self.generation)
        self.store.path.unlink()
        instance = self.make_service()
        self.error(503, "runtime_store_lost", instance.start)
        self.assertFalse(self.store.path.exists())
        self.assertEqual(json.loads((self.root_goal / "state.json").read_text())["waiting_reason"], "runtime_store_lost")
        instance.provider.probe.assert_not_called()
        instance.close()
        self.store.path.write_bytes(b"corrupt")
        self.error(503, "runtime_store_lost", instance.start)
        self.assertEqual(self.store.path.read_bytes(), b"corrupt")

    def test_probe_failure_prevents_running_loop(self):
        provider = mock.Mock()
        provider.probe.side_effect = Error("sentinel_probe_failed", status=503)
        instance = self.make_service(provider)
        self.error(503, "sentinel_probe_failed", instance.pass_once)
        provider.invoke.assert_not_called()

    def test_project_lock_refresh_and_foreign_lock_survives(self):
        lock = service.ProjectLock(self.settings, "alpha", "owner")
        lock.acquire()
        original = json.loads(lock.path.read_text())
        lock.refresh()
        self.assertEqual(json.loads(lock.path.read_text())["session_id"], "owner")
        foreign = service.ProjectLock(self.settings, "alpha", "foreign")
        self.error(423, "project_locked", foreign.acquire)
        foreign.release()
        self.assertTrue(lock.path.exists())
        lock.release()
        self.assertFalse(lock.path.exists())

    def test_waiting_does_not_invoke_coordinator_and_pause_publishes(self):
        self.now += 301
        with self.store.transaction() as db:
            db.execute("UPDATE goal_state SET phase='waiting'")
        instance = self.make_service()
        instance.pass_once()
        instance.provider.invoke.assert_not_called()
        self.store.enqueue(self.goal, "pause", {}, "human", self.revision)
        instance.pass_once()
        self.assertEqual(json.loads((self.root_goal / "state.json").read_text())["phase"], "paused")
        self.assertFalse((self.repo / "projects/alpha/.agent-lock").exists())

    def test_known_dead_owner_is_reconciled_but_age_is_not_takeover_authority(self):
        old = service.ProjectLock(self.settings, "alpha", "test", self.store)
        old.acquire()
        replacement = service.ProjectLock(self.settings, "alpha", "replacement", self.store)
        with mock.patch.object(service.os, "kill", side_effect=ProcessLookupError):
            replacement.acquire()
        self.assertEqual(json.loads(old.path.read_text())["session_id"], "replacement")
        old.release()
        self.assertTrue(replacement.path.exists())
        self.assertGreater(self.store.acquire_lease(self.goal, "replacement"), self.generation)
        replacement.release()

    def test_two_steps_continue_automatically_with_no_intervening_commands(self):
        source = self.root / "source.h5"
        source.write_bytes(b"fixture source")
        for aid in ("a", "b"):
            self.assignments[aid].update(step="tissue", volume="fixture", source_shape=[16, 20, 24], downsample=4,
                                         python="python", memory="32G", partition="short", inputs={"source": {"path": str(source)}},
                                         outputs=[dict(name="tissue_ds", filename="tissue.h5", min_size=1)], acceptance=list(verify.CHECKS))
        self.assignments["b"]["dependencies"] = ["a"]
        self.assignments["b"]["inputs"]["tissue"] = {"from": {"assignment": "a", "output": "tissue_ds"}, "filename": "previous.h5"}
        self.payload["acceptance"] = [dict(assignment=aid, criterion=c) for aid in ("a", "b") for c in verify.CHECKS]
        self.update_snapshot()
        self.now += 301
        actions = iter([dict(kind="dispatch_assignment", assignment="a"), dict(kind="dispatch_assignment", assignment="b"), dict(kind="complete")])
        def invoke(packet, run_id):
            value = json.loads(packet)
            return "```rdash-decision\n" + encode(dict(goal=value["goal"], snapshot_revision=value["snapshot_revision"],
                generation=value["generation"], rationale="Advance on verified evidence", action=next(actions))) + "\n```"
        provider = mock.Mock()
        provider.invoke.side_effect = invoke
        scheduler = mock.Mock()
        scheduler.lookup_by_name.return_value = []
        job_ids = iter(["101", "102"])
        def submit(row, wrapper, manifest, cwd, memory, partition):
            job_id = next(job_ids)
            for output in row["outputs_declared"]:
                from pathlib import Path
                path = Path(output["path"])
                path.parent.mkdir(parents=True)
                path.write_bytes(b"synthetic tissue")
            receipt = dict(schema=1, attempt=row["attempt"], request_id=row["request_id"], goal=row["goal"],
                           assignment=row["assignment"], job_name=row["job_name"], slurm_job_id=job_id,
                           command=row["command"], exit_code=0, parameters=row["parameters"], inputs=row["inputs_digest"],
                           outputs=[verify.digest(out["path"]) for out in row["outputs_declared"]],
                           summary=dict(dataset="main", rank=3, dtype="uint8", shape=[4, 5, 6]))
            (manifest.parent / "receipt.json").write_text(encode(receipt))
            return job_id
        scheduler.submit.side_effect = submit
        scheduler.settle.return_value = dict(state="COMPLETED", cpu_hours=.1, alloc_cpus=4)
        instance = self.make_service(provider, scheduler)
        for _ in range(3):
            instance.pass_once()
            self.now += 31
        self.assertEqual(self.store.balance(self.goal)["phase"], "achieved", self.store.rows("SELECT * FROM decisions"))
        self.assertEqual(scheduler.submit.call_count, 2)
        self.assertEqual(self.store.balance(self.goal)["consumed_jobs"], 2)
        self.assertEqual(self.store.balance(self.goal)["held_jobs"], 0)
        self.assertEqual(self.store.balance(self.goal)["coordinator_runs_used"], 3)

    def test_recoverable_failure_retries_once_then_requires_a_person(self):
        self.now += 301
        provider = mock.Mock()
        def invoke(packet, run):
            value = json.loads(packet)
            return "```rdash-decision\n" + encode(dict(goal=value["goal"], snapshot_revision=value["snapshot_revision"],
                generation=value["generation"], rationale="Retry within limits", action=dict(kind="dispatch_assignment", assignment="a"))) + "\n```"
        provider.invoke.side_effect = invoke
        scheduler = mock.Mock()
        scheduler.lookup_by_name.return_value = []
        scheduler.submit.side_effect = ["101", "102"]
        scheduler.settle.return_value = dict(state="TIMEOUT", cpu_hours=.1, alloc_cpus=4)
        instance = self.make_service(provider, scheduler)
        for _ in range(3):
            instance.pass_once()
            self.now += 31
        self.assertEqual(scheduler.submit.call_count, 2)
        self.assertEqual(provider.invoke.call_count, 2)
        self.assertEqual(self.store.balance(self.goal)["phase"], "decision_required")
        self.assertEqual(self.store.balance(self.goal)["consumed_jobs"], 2)
