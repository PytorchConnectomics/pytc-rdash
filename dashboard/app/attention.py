"""Route the next action. An agent owner is a suggestion, not dispatch authority."""

# Mirrors JOB_BUCKET in static/app.js: the badge and this derivation must
# read the same scheduler state the same way.
BUCKETS = {
    "RUNNING": "run", "COMPLETING": "run", "CONFIGURING": "run",
    "PENDING": "wait", "REQUEUED": "wait", "SUSPENDED": "wait",
    "COMPLETED": "done", "FAILED": "bad", "CANCELLED": "bad", "TIMEOUT": "bad",
    "NODE_FAIL": "bad", "OUT_OF_MEMORY": "bad", "BOOT_FAIL": "bad",
    "DEADLINE": "bad", "PREEMPTED": "bad",
}


def owner_and_next(record):
    contract = record.get("contract", {})
    acceptance = record.get("acceptance", {})
    sessions = record.get("sessions", {})
    buckets = [BUCKETS.get(str(j.get("state")).upper(), "unknown") for j in record.get("jobs", [])]
    live = any(b in ("run", "wait") for b in buckets)
    unknown = "unknown" in buckets or any(a.get("state") == "unknown" for a in record.get("artifacts", []))
    unresolved = unknown or live
    terminal = record.get("verdict") in ("met", "failed", "inconclusive")
    total, settled = acceptance.get("total", 0), acceptance.get("settled", 0)
    full = acceptance.get("declared", False) and settled == total and total > 0
    rules = [
        (record.get("read_only"), "fix_frontmatter", "agent", "Inspect unsupported frontmatter before proposing a repair"),
        (contract.get("declared") and contract.get("structure") == "fail", "fix_contract", "agent", "Investigate unresolved contract references; preserve scientific criteria"),
        (contract.get("declared") and contract.get("structure") == "unknown", "contract_unknown", "agent", "Inspect why contract structure is unknown"),
        ((record.get("goal") or {}).get("phase") == "unknown", "unknown", "you", "Goal projection is unreadable or invalid; reconcile authority before continuing"),
        ((record.get("goal") or {}).get("phase") == "decision_required", "resolve_decision", "you", "An open decision blocks authorized work"),
        ((record.get("goal") or {}).get("phase") == "paused", "resume_or_redirect", "you", "Dispatch is paused; running jobs continue"),
        ((record.get("goal") or {}).get("phase") == "exhausted", "raise_budget_or_close", "you", "Budget or coordinator runs are spent"),
        (terminal and unresolved, "verdict_recorded_state_unresolved", "you", "Authored verdict; execution state remains unresolved"),
        (terminal, "closed", "none", "Authored terminal verdict; no unresolved execution state"),
        (full and not unresolved, "record_verdict", "you", "Acceptance settled; a human verdict is still needed"),
        (contract.get("missing_facts", 0) > 0 and not sessions.get("running") and not live, "supply_facts", "agent", "Collect missing evidence facts without changing acceptance criteria"),
        (unknown, "unknown", "you", "Job or artifact observation is unknown"),
        (live, "wait", "scheduler", "Jobs are running or queued"),
        (sessions.get("running"), "in_session", "agent", "The goal supervisor reports a coordinator in flight"),
        (any(b in ("done", "bad") for b in buckets) and not full, "read_evidence", "agent", "Inspect finished-job evidence; completion does not establish acceptance"),
        (not acceptance.get("declared"), "make_acceptance_checkable", "you", "No acceptance task list"),
        (settled < total, "read_evidence", "agent", "Check evidence for unsettled acceptance items"),
        (True, "plan_next_probe", "you", "No other rule applies"),
    ]
    for condition, next_action, owner, reason in rules:
        if condition:
            return dict(owner=owner, next=next_action, reason=reason)
