#!/usr/bin/env bash
# Remove orphaned kimimaro shared-memory segments from /dev/shm.
# A segment is orphaned when no process holds it open or mapped. Killed kimimaro
# runs (scancel, timeout, OOM) leave these behind; they pin RAM and end up in swap.
#
#   shm_clean.sh [--dry-run] [--min-age MIN] [--pattern GLOB]
#
# Only files owned by the caller are touched. Files younger than --min-age
# (default 10 min) are skipped so a run that has just created a segment is safe.
set -euo pipefail

DRY=0; MIN_AGE=10; PATTERN='kimimaro-shm-*'
while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run) DRY=1 ;;
    --min-age) MIN_AGE=$2; shift ;;
    --pattern) PATTERN=$2; shift ;;
    -h|--help) sed -n 2,9p "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

freed=0; n=0; kept=0
while IFS= read -r -d '' f; do
  if fuser -s "$f" 2>/dev/null; then kept=$((kept+1)); continue; fi
  kb=$(du -k "$f" | cut -f1)
  if [[ $DRY == 1 ]]; then echo "would remove $f (${kb} KB)"; else rm -f "$f"; fi
  freed=$((freed+kb)); n=$((n+1))
done < <(find /dev/shm -maxdepth 1 -type f -user "$USER" -name "$PATTERN" -mmin +"$MIN_AGE" -print0)

verb=$([[ $DRY == 1 ]] && echo "would free" || echo "freed")
echo "$(hostname -s): $verb $((freed/1024)) MB in $n files; $kept in use, kept"
