"""Expose explicit operator commands for the governed supervisor."""
import argparse
import getpass
import json
import sys

from dashboard.app.config import Settings
from dashboard.app import safety
from dashboard.adapters.claude_cli import Claude
from dashboard.adapters.slurm import Slurm
from . import goals
from .service import Service
from .store import Error, Store, encode


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("create", "activate", "pause", "resume", "resolve", "status", "run-once", "serve"))
    parser.add_argument("--project")
    parser.add_argument("--goal")
    parser.add_argument("--revision")
    parser.add_argument("--decision")
    parser.add_argument("--value", help="JSON decision value")
    parser.add_argument("--record", help="JSON bundle with authored goal and assignments")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
        store = Store(settings.supervisor_db)
        if args.action in ("serve", "run-once"):
            service = Service(settings, Claude(settings), Slurm(getpass.getuser()), store)
            try:
                service.run() if args.action == "serve" else service.pass_once()
            finally:
                service.close()
            return 0
        goal = goals.key(args.project, args.goal)
        if args.action == "create":
            with open(args.record, "rb") as stream:
                record = json.load(stream)
            goals.validate(record, args.project, args.goal)
            root = goals.directory(settings, args.project, args.goal)
            with safety.writer_lock(settings):
                safety.agent_lock_state(root.parents[1])
                root.mkdir(parents=True, exist_ok=False)
                assignments = root / "assignments"
                assignments.mkdir()
                for aid, assignment in record["assignments"].items():
                    safety.publish_replace(assignments / (aid + ".json"), (encode(assignment) + "\n").encode())
                authored = {k: v for k, v in record.items() if k != "assignments"}
                safety.publish_replace(root / "goal.json", (encode(authored) + "\n").encode())
            print("created paused goal", goal)
            return 0
        if not store.path.exists():
            raise Error("supervisor_not_started", status=503)
        if args.action == "status":
            print(json.dumps(goals.projection(store, goal), indent=2))
            return 0
        revision = goals.import_snapshot(settings, store, args.project, args.goal)
        if args.action == "activate":
            expected = args.revision or revision
        else:
            expected = args.revision
        payload = dict(decision_id=args.decision, value=json.loads(args.value)) if args.action == "resolve" else {}
        kind = {"activate": "resume", "resolve": "resolve_decision"}.get(args.action, args.action)
        print(store.enqueue(goal, kind, payload, getpass.getuser(), expected))
        return 0
    except (Error, safety.Error, OSError, ValueError, TypeError) as exc:
        print("rdash supervisor: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
