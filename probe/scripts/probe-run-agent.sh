#!/usr/bin/env bash
# Run a delegated step (implement, or a second-opinion review) through a
# non-interactive agent CLI. The coordinator builds <prompt> from the
# preregistration, with engineering acceptance separate from the scientific
# decision criteria and the project gate as an early check. The agent's final
# message is written to <output-file>.
#
# Usage: probe-run-agent.sh <claude|codex> <prompt-file-or-"-"> <output-file>
#   prompt is read from the file, or from stdin when the 2nd arg is "-".
set -euo pipefail

AGENT=${1:?usage: probe-run-agent.sh <claude|codex> <prompt-file|-> <output-file>}
PROMPT_SRC=${2:?missing prompt}
OUT=${3:?missing output file}

if [ "$PROMPT_SRC" = "-" ]; then PROMPT=$(cat); else PROMPT=$(cat "$PROMPT_SRC"); fi
mkdir -p "$(dirname "$OUT")"

case "$AGENT" in
  claude)
    command -v claude >/dev/null || { echo "probe-run-agent: 'claude' not found" >&2; exit 127; }
    # Implement/analysis pass with tools enabled; no session persistence.
    printf '%s\n' "$PROMPT" \
      | claude --print --output-format text --no-session-persistence \
      | tee "$OUT"
    ;;
  codex)
    command -v codex >/dev/null || { echo "probe-run-agent: 'codex' not found" >&2; exit 127; }
    codex exec --sandbox workspace-write --output-last-message "$OUT" "$PROMPT"
    ;;
  *)
    echo "probe-run-agent: unknown agent '$AGENT' (use claude|codex)" >&2
    exit 2
    ;;
esac

echo "probe-run-agent: $AGENT wrote $OUT" >&2
