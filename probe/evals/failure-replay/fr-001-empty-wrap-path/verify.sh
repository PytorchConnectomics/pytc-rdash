#!/usr/bin/env bash
# Usage: verify.sh <answer.json>
here="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$here/../../verify_failure_replay.py" "${1:?answer.json}" "$here/expected.json"
