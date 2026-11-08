#!/usr/bin/env bash
# rdash_sync.sh — the hub's one-minute loop (dwos-rdash-sync.timer on g02).
#
#   1. collect new run receipts from the launch hosts (receipts.py collect);
#   2. commit what rdash itself wrote -- projects/*/cards (board edits, ideas,
#      batch ticks) and projects/*/runs (receipts) -- under the board's writer lock;
#   3. rebase onto origin/main and push, so every checkout sees the change and the
#      board serves what was pushed from anywhere within a minute.
#
# The board checkout is service-only. It must be on main, and any other tracked
# change blocks the sync rather than being committed or stashed: it is someone's
# work in a checkout nobody should develop in. State: <cache>/sync.json, shown by
# `hub.sh status` and the board's Runs view.
#
# Hosts in RDASH_SLOW_HOSTS (host:seconds,..., default bc:900,cajal:900) are polled
# at most that often; board edits still sync every minute. BC's login node is shared and caps weidf at 400 tasks; polling it every
# minute added to the 2026-10-23 lockout (pm/clusters/bc.md). A polled host that does
# not answer -- or silently drops out of the launch roots, as bc did at 05:14 that
# day -- turns the state to warn ("bc unreachable since ...") until it answers again.
set -uo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$here/rdash_env.sh"
root=$(cd -- "$here/../.." && pwd)
cd "$root" || exit 1
export RDASH_REPO_ROOT=$root RDASH_HOST_ALIAS=${RDASH_HOST_ALIAS:-$(hostname -s)} RDASH_SSH_HOSTS=${RDASH_SSH_HOSTS-cajal,bc}
cache=${RESEARCH_DASH_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/dw-research-dashboard}
mkdir -p "$cache"
report() {
    python3 - "$cache/sync.json" "$1" "$2" "$(git rev-parse --short HEAD 2>/dev/null)" <<'PY'
import json, os, sys, time
path, state, message, head = sys.argv[1:]
tmp = path + ".tmp"
with open(tmp, "w") as out:
    json.dump(dict(state=state, message=message, head=head, at=time.strftime("%Y-%m-%dT%H:%M:%S%z")), out)
os.replace(tmp, path)
PY
    echo "rdash-sync: $1: $2"
}
# Pathspec wildcards match across '/', so these cover cards/inbox/ too.
OWNED=('projects/*/cards/*' 'projects/*/runs/*')

branch=$(git symbolic-ref -q --short HEAD) || branch=
if [ "$branch" != main ]; then
    report blocked "board checkout is on '${branch:-detached HEAD}', not main; nothing collected or synced"; exit 0
fi
now=$(date +%s) due=() slows=${RDASH_SLOW_HOSTS-bc:900,cajal:900}
IFS=, read -ra hosts <<< "$RDASH_SSH_HOSTS"
for host in "${hosts[@]}"; do
    [ -n "$host" ] || continue
    every=0 last=0
    for slow in ${slows//,/ }; do [ "${slow%%:*}" = "$host" ] && every=${slow#*:}; done
    [ -f "$cache/polled-$host" ] && read -r last < "$cache/polled-$host"
    if [ $((now - ${last:-0})) -ge "$every" ]; then due+=("$host"); echo "$now" > "$cache/polled-$host"; fi
done
polled=$(IFS=,; echo "${due[*]}")
collected=$(RDASH_SSH_HOSTS=$polled python3 -B -m dashboard.app.receipts collect 2>"$cache/collect.err") \
    || { report warn "receipt collection failed: $(tail -1 "$cache/collect.err")"; collected=; }
printf '%s\n' "$collected" > "$cache/collect.json"
# Hosts down since when (<cache>/hosts.json): only hosts polled this run change, and a
# host taken out of RDASH_SSH_HOSTS is forgotten.
down=$(python3 - "$cache/hosts.json" "$RDASH_SSH_HOSTS" "$polled" "$collected" <<'PY'
import json, os, sys, time
path, configured, polled, collected = sys.argv[1:]
try:
    down = json.load(open(path))
except (OSError, ValueError):
    down = {}
down = {host: since for host, since in down.items() if host in configured.split(",")}
try:
    answered = json.loads(collected).get("hosts", {})
except ValueError:
    answered = None     # collection itself failed, reported above
for host in polled.split(",") if polled and answered is not None else []:
    if answered.get(host) == "ok":
        if host in down:
            print("rdash-sync: %s reachable again (down since %s)" % (host, down.pop(host)), file=sys.stderr)
    else:
        down.setdefault(host, time.strftime("%Y-%m-%d %H:%M"))
with open(path + ".tmp", "w") as out:
    json.dump(down, out)
os.replace(path + ".tmp", path)
print("; ".join("%s unreachable since %s" % kv for kv in sorted(down.items())))
PY
)
git fetch -q origin main || { report warn "git fetch failed; will retry"; exit 0; }

exec 9>>"$root/.rdash.lock"
flock -w 30 9 || { report busy "board writer lock held for 30 s; will retry"; exit 0; }
other=$( { git diff --name-only; git diff --cached --name-only; } | grep -vE '^projects/[^/]+/(cards|runs)/' | sort -u | head -5)
if [ -n "$other" ]; then
    report blocked "tracked changes outside cards/ and runs/ in the board checkout: $(echo $other)"; exit 0
fi
changed=$(git ls-files -z --modified --deleted --others --exclude-standard -- "${OWNED[@]}" | tr '\0' '\n' | sort -u)
if [ -n "$changed" ]; then
    printf '%s\n' "$changed" | git add -A --pathspec-from-file=- \
        && git commit -q -m "rdash: board edits and run receipts (g02 sync)" \
        || { report warn "commit failed"; exit 1; }
fi
if ! git rebase -q origin/main >/dev/null 2>&1; then
    git rebase --abort >/dev/null 2>&1
    report conflict "local rdash commit does not rebase onto origin/main; kept locally, not pushed"; exit 1
fi
flock -u 9
if [ -n "$(git rev-list origin/main..HEAD)" ]; then
    git push -q origin HEAD:main 2>"$cache/push.err" || { report warn "push failed; will retry: $(tail -1 "$cache/push.err")"; exit 0; }
fi
stored=$(printf '%s' "$collected" | python3 -c 'import json,sys
try: d = json.load(sys.stdin)
except ValueError: d = {}
print(len(d.get("stored", [])), "new receipt(s);", ", ".join("%s %s" % kv for kv in d.get("hosts", {}).items()) or "no hosts")')
if [ -n "$down" ]; then
    report warn "at origin/main $(git rev-parse --short origin/main); $stored; $down"
else
    report ok "at origin/main $(git rev-parse --short origin/main); $stored"
fi
