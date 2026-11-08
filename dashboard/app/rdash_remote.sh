#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/rdash_env.sh"
# Drive the rdash board on a remote host and forward it to this machine.
#
#   rdash_remote.sh start | stop | status
#
# The board runs where the cards are, so agent writes, the .rdash.lock flock and
# the .agent-lock check all stay in one filesystem domain. Only an SSH tunnel
# crosses the network.
#
#   RDASH_HOST          ssh host: the team's hub (required; ~/.config/rdash/env)
#   RDASH_REMOTE_ROOT   the team repository's checkout on that host (required)
#   RDASH_SSH_HOSTS     GPU hosts the board may inspect, comma-separated
#                       (default: the remote launcher's own default)
#   RESEARCH_DASH_PORT  port, used on BOTH ends (default: 8766)
#
# The port must match on both ends: server.py validates the Host header against
# its own bound port, so `-L 9000:127.0.0.1:8766` returns 403.
#
# The tunnel is owned through a dedicated ControlMaster socket, never by matching
# process names. `ssh -f` rewrites its argv to just `ssh <host>`, which is
# indistinguishable from other sessions to the same host -- including the one
# codex.app uses to drive BC. Only the socket identifies our own tunnel.
#
# `start` also leaves a watcher that reopens the tunnel when it dies, so a Mac
# sleep or network change heals itself. Every call bypasses the shared
# `ControlMaster auto` socket: after a sleep that master is dead but still
# answers, and a command routed through it hangs until keepalive gives up.
set -eu

HOST=${RDASH_HOST:-}
ROOT=${RDASH_REMOTE_ROOT:-}
[ -n "$HOST" ] && [ -n "$ROOT" ] || { echo "rdash_remote.sh: set RDASH_HOST and RDASH_REMOTE_ROOT (~/.config/rdash/env)" >&2; exit 1; }
PORT=${RESEARCH_DASH_PORT:-8766}
FORWARD="${PORT}:127.0.0.1:${PORT}"
URL="http://127.0.0.1:${PORT}"
REMOTE="$ROOT/rdash/dashboard/app/research_dash.sh"
CTL="${TMPDIR:-/tmp}/rdash-tunnel-${HOST}-${PORT}.sock"
WATCH="${TMPDIR:-/tmp}/rdash-watch-${HOST}-${PORT}.pid"
ONESHOT="-o ControlPath=none -o ConnectTimeout=10"
SSH_HOSTS=""
if [ -n "${RDASH_SSH_HOSTS+x}" ]; then
    case "$RDASH_SSH_HOSTS" in
        *[!A-Za-z0-9._,-]*) echo "Invalid RDASH_SSH_HOSTS" >&2; exit 1 ;;
    esac
    SSH_HOSTS="RDASH_SSH_HOSTS=$RDASH_SSH_HOSTS "
fi

tunnel_up() { ssh -S "$CTL" -O check "$HOST" >/dev/null 2>&1; }
tunnel_close() { ssh -S "$CTL" -O exit "$HOST" >/dev/null 2>&1 || true; rm -f "$CTL"; }
# Redirect the forked master's stdio: with -f it inherits the caller's stdout,
# so a command substitution or pipe around this script would block until the
# tunnel exits. ExitOnForwardFailure: a stale tunnel still holding the port
# must fail this attempt, not yield a master that forwards nothing.
tunnel_open() {
    rm -f "$CTL"
    ssh -M -S "$CTL" -f -N -L "$FORWARD" -o ExitOnForwardFailure=yes \
        -o ConnectTimeout=10 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 \
        "$HOST" </dev/null >/dev/null 2>&1
}
watch_up() { [ -f "$WATCH" ] && kill -0 "$(cat "$WATCH")" 2>/dev/null; }

case "${1:-}" in
start)
    case "$HOST" in
        ''|*[!A-Za-z0-9._-]*|-*) echo "Invalid RDASH_HOST" >&2; exit 1 ;;
    esac
    ssh $ONESHOT "$HOST" "${SSH_HOSTS}RDASH_HOST_ALIAS=$HOST RESEARCH_DASH_PORT=$PORT $REMOTE start" >/dev/null
    tunnel_up || tunnel_open
    if ! watch_up; then
        nohup "$0" _watch >/dev/null 2>&1 &
        echo $! > "$WATCH"
    fi
    printf '%s\n' "$URL"
    ;;
_watch)
    # Reopen a dead tunnel. A wall-clock jump means the machine slept: the
    # master may still pass `-O check` with a dead connection, so replace it.
    while :; do
        before=$(date +%s)
        sleep 10
        if [ $(( $(date +%s) - before )) -gt 30 ]; then tunnel_close; fi
        tunnel_up || tunnel_open || true
    done
    ;;
stop)
    # Closes only our own tunnel and watcher; other ssh sessions are untouched.
    if watch_up; then kill "$(cat "$WATCH")" 2>/dev/null || true; fi
    rm -f "$WATCH"
    tunnel_close
    ssh $ONESHOT "$HOST" "RESEARCH_DASH_PORT=$PORT $REMOTE stop"
    ;;
status)
    ssh $ONESHOT "$HOST" "RESEARCH_DASH_PORT=$PORT $REMOTE status"
    if tunnel_up; then printf 'tunnel: up %s\n' "$URL"; else printf 'tunnel: down\n'; fi
    if watch_up; then printf 'watcher: up\n'; else printf 'watcher: down (run start)\n'; fi
    ;;
*)
    echo "Usage: rdash_remote.sh start|stop|status" >&2
    exit 1
    ;;
esac
