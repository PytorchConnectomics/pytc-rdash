"""Offline authored goals and isolated runtime stores for supervisor tests."""
import copy
import json
import uuid

from fixtures import RepoTest
from dashboard.supervisor import goals
from dashboard.supervisor.store import Store


class SupervisorTest(RepoTest):
    def setUp(self):
        super().setUp()
        self.now = 1000.0
        self.store = Store(self.cache / "supervisor/runtime.db", clock=lambda: self.now)
        self.store.initialize()
        self.goal = "alpha/demo"
        self.root_goal = goals.directory(self.settings, "alpha", "demo")
        (self.root_goal / "assignments").mkdir(parents=True)
        self.payload = dict(schema=1, id="demo", project="alpha", card="question.md", outcome="Verify two steps",
                            authority=dict(allowed_actions=["dispatch_assignment", "request_decision", "complete", "stop"]),
                            budget=dict(jobs=4, cpu_hours=12.0, coordinator_runs=12), concurrency=1,
                            acceptance=[dict(assignment="a", criterion="exit_zero")])
        self.assignments = {name: dict(id=name, cpus=4, time_limit_s=2700, parameters={},
                                      dependencies=[], acceptance=["exit_zero"], step="harness_sleep",
                                      python="python", volume="fixture", memory="32G", partition="short", inputs={},
                                      outputs=[dict(name="done", filename="done.json", min_size=1)])
                            for name in ("a", "b")}
        self.write_records()
        self.revision = goals.import_snapshot(self.settings, self.store, "alpha", "demo")
        self.generation = self.store.acquire_lease(self.goal, "test")
        self.store.enqueue(self.goal, "resume", {}, "test", self.revision)
        self.store.apply_commands(self.goal)

    def write_records(self):
        (self.root_goal / "goal.json").write_text(json.dumps(self.payload))
        for aid, value in self.assignments.items():
            (self.root_goal / "assignments" / (aid + ".json")).write_text(json.dumps(value))

    def update_snapshot(self):
        self.write_records()
        self.revision = goals.import_snapshot(self.settings, self.store, "alpha", "demo")

    def reserve(self, aid="a", **changes):
        request = str(uuid.uuid4())
        kwargs = dict(goal=self.goal, aid=aid, generation=self.generation, request_id=request,
                      job_name="rdash-" + request[:12], attempt=request, inputs={}, outputs=[],
                      command=["python", "worker.py"], revision=self.revision)
        kwargs.update(changes)
        return self.store.reserve(**kwargs)

    def decision(self, aid="a", parameter="pct"):
        identifier = str(uuid.uuid4())
        with self.store.transaction() as db:
            db.execute("INSERT INTO decisions(id,goal,assignment,parameter,question,alternatives,evidence,expected_cost,"
                       "snapshot_revision,created,state) VALUES(?,?,?,?,'Choose','[]','[]','{}',?,?,'open')",
                       (identifier, self.goal, aid, parameter, self.revision, self.now))
        return identifier

    def snapshot_copy(self):
        return copy.deepcopy(self.store.snapshot(self.goal)[1])
