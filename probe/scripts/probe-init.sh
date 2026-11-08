#!/usr/bin/env bash
# Scaffold a probe research workspace. Idempotent: never overwrites an existing
# state.yaml / loop.md / lessons.md. Usage: probe-init.sh <workspace-dir>
set -euo pipefail

WS=${1:?usage: probe-init.sh <workspace-dir>}
HERE=$(cd "$(dirname "$0")/.." && pwd)   # the probe skill root
TPL="$HERE/templates"

mkdir -p "$WS/lessons" "$WS/error_analysis" "$WS/research_plan" "$WS/runs"

copy_if_absent() {  # <src> <dst>
  if [ -e "$2" ]; then
    echo "probe-init: kept existing $2"
  else
    cp "$1" "$2"
    echo "probe-init: wrote $2"
  fi
}

copy_if_absent "$TPL/state.yaml" "$WS/state.yaml"
copy_if_absent "$TPL/loop.md"    "$WS/loop.md"

if [ ! -e "$WS/lessons/lessons.md" ]; then
  cat >"$WS/lessons/lessons.md" <<'EOF'
# Lessons index

Master index of experiments in this workspace. One row per experiment run; the verdict
and the preregistration live in `lesson_<run_id>.md`. Objective and current findings:
[`../state.yaml`](../state.yaml). Methodology: [`../loop.md`](../loop.md).

| # | run / lever | one-line verdict | outcome | detail |
|---|---|---|---|---|
EOF
  echo "probe-init: wrote $WS/lessons/lessons.md"
else
  echo "probe-init: kept existing $WS/lessons/lessons.md"
fi

echo "probe-init: scaffold written at $WS (contents and execution readiness not validated)"
echo "next: fill state.yaml + loop.md (method revision, objective, evaluation, project gates) via 'probe bootstrap'"
