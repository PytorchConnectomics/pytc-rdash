"""Shared verifier for failure-replay tasks: compare answer.json with expected.json."""
import json
import sys

answer_path, expected_path = sys.argv[1], sys.argv[2]
try:
    answer = json.load(open(answer_path))
except (OSError, json.JSONDecodeError) as e:
    print(f"FAIL: cannot read answer: {e}")
    sys.exit(1)
expected = json.load(open(expected_path))

failures = []
for key in ("cause", "action"):
    if answer.get(key) not in expected[key]:
        failures.append(f"{key}={answer.get(key)!r}, expected one of {expected[key]}")
if "notify" in expected and bool(answer.get("notify")) != expected["notify"]:
    failures.append(f"notify={answer.get('notify')!r}, expected {expected['notify']}")

if failures:
    print("FAIL: " + "; ".join(failures))
    sys.exit(1)
print("PASS")
