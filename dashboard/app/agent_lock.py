"""Take, release and list agent locks: one per card, plus one optional project-wide lock.

    python3 -m dashboard.app.agent_lock take    --project P --card cards-ref.md --task "what"
    python3 -m dashboard.app.agent_lock release --project P --card cards-ref.md
    python3 -m dashboard.app.agent_lock status  --project P

Omit --card for the project lock (`<project>/.agent-lock`): project-wide work such as
spec, state or a new card. A card lock (`<project>/.locks/cards/<ref>.lock`) covers one
card, so several sessions can work on different cards of one project. The session is
$RDASH_SESSION_ID unless --session is given; the board and launcher pass a holder's own
locks when that variable matches. Locks are advisory and gitignored; see safety.py.
"""
import argparse
import json
import sys
import time

from .config import Settings
from .safety import (Error, LOCK_FRESH_SECONDS, PROJECT_LOCK, _session, card_locks, project_id, read_lock,
                     release_lock, resolve_within, take_lock, writer_lock)


def _with_writer(settings, fn):
    for attempt in range(20):
        try:
            with writer_lock(settings):
                return fn()
        except Error as exc:
            if exc.payload["error"] != "busy" or attempt == 19:
                raise
            time.sleep(0.25)


def status(project_dir):
    rows = []
    entries = [(None, project_dir / PROJECT_LOCK)] + card_locks(project_dir)
    for card, path in entries:
        try:
            state = read_lock(path)
        except Error:
            rows.append(dict(card=card, path=str(path), unreadable=True))
            continue
        if state:
            lock, age = state
            rows.append(dict(card=card, session_id=lock.get("session_id"), task=lock.get("task"),
                             started=lock.get("started"), age_h=round(age / 3600, 2),
                             fresh=age < LOCK_FRESH_SECONDS))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=("take", "release", "status"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--card", help="card ref under cards/, e.g. 2026-11-25_x.md or inbox/y.md; omit for the project lock")
    parser.add_argument("--task", help="take: what the session is doing")
    parser.add_argument("--session", help="default: $RDASH_SESSION_ID")
    parser.add_argument("--stale", action="store_true", help="release: also a foreign lock over 6 h old")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
        project_dir = resolve_within(settings.repo_root, "projects", project_id(args.project))
        if not project_dir.is_dir():
            raise Error(404, "unknown_project", "No such project " + args.project)
        session = _session(args.session)
        if args.action == "status":
            out = status(project_dir)
        elif args.action == "take":
            path = _with_writer(settings, lambda: take_lock(project_dir, session, args.task or "", args.card))
            out = dict(taken=str(path), session_id=session)
        else:
            path = _with_writer(settings, lambda: release_lock(project_dir, session, args.card, args.stale))
            out = dict(released=str(path) if path else None)
    except Error as exc:
        print(json.dumps(exc.payload), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(json.dumps(dict(error="config", message=str(exc))), file=sys.stderr)
        return 1
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
