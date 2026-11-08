#!/usr/bin/env bash
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/rdash_env.sh"
# One entry point for the rdash command center, run from any checkout.
#
#   hub.sh status                                   board, sync, tunnel, revisions, queue
#   hub.sh deploy                                   pull hub + GPU checkouts, restart board
#   hub.sh launch <project> <cards/file.md> [--step S] [--test-only]
#   hub.sh runs [project]                           recent jobs no receipt or card names
#   hub.sh attach <host> <job> <project> [cards/file.md] [--note TEXT]
#   hub.sh sync                                     run the hub's one-minute sync now
#   hub.sh batch new|status|tick <project> ...      batch cards for agents (JSON out)
#   hub.sh jobs [gpu-host]                          your queued/running Slurm jobs
#
# Topology (dashboard/RECEIPTS.md): cards live in git and are written anywhere. The
# board runs on the team's hub in a service-only checkout of the team repository
# (with rdash/ as its submodule) that follows origin/main every minute and commits
# what the board writes. A launch submits from the machine that holds the code
# (rsub) and leaves a receipt beside the run; the hub collects receipts and never
# edits a card to record a job. This machine only opens the tunnel (`rdash`);
# cluster keys stay on the hub.
#
# rdash ships no hosts or paths: each team sets them in ~/.config/rdash/env
# (rdash_env.sh) or its systemd units (dashboard/app/systemd/).
#   RDASH_HOST         hub ssh alias                           (required)
#   RDASH_REMOTE_ROOT  the team repository's checkout on the hub (required)
#   RDASH_SSH_HOSTS    GPU hosts, comma list                   (default: none)
#   RDASH_GPU_ROOT     the team repository's checkout on GPU hosts that have one
#   RDASH_CHECKOUT_HOSTS  GPU hosts with that checkout, where launches run;
#                      any other GPU host is staged from the hub over SSH
set -eu

HUB=${RDASH_HOST-}
HUB_ROOT=${RDASH_REMOTE_ROOT-}
GPUS=${RDASH_SSH_HOSTS-}
GPU_ROOT=${RDASH_GPU_ROOT-}
CHECKOUTS=${RDASH_CHECKOUT_HOSTS-}
[ -n "$HUB" ] && [ -n "$HUB_ROOT" ] || { echo "hub.sh: set RDASH_HOST and RDASH_REMOTE_ROOT (~/.config/rdash/env)" >&2; exit 1; }
case "$HUB_ROOT$GPU_ROOT" in *[!A-Za-z0-9._/-]*) echo "hub.sh: invalid checkout path" >&2; exit 1 ;; esac
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# From the team repository, the tooling is rdash/; python modules import as dashboard.*
TOOL=rdash
ENV="RDASH_SSH_HOSTS=$GPUS RDASH_HOST_ALIAS=$HUB"
for key in RDASH_CONFIG_DIR RESEARCH_DASH_PORT; do
    if declare -p "$key" >/dev/null 2>&1; then
        [[ ${!key} =~ ^[A-Za-z0-9._,/-]*$ ]] || { echo "hub.sh: invalid $key" >&2; exit 1; }
        ENV="$ENV $key=${!key}"
    fi
done

for value in "$HUB" $(echo "$GPUS" | tr ',' ' '); do
    case "$value" in ''|-*|*[!A-Za-z0-9._-]*) echo "hub.sh: invalid host '$value'" >&2; exit 1 ;; esac
done

# On the hub itself (an agent session there), run hub commands locally.
LOCAL=$(hostname -s 2>/dev/null || hostname)
on() {
    host=$1; shift
    if [ "$host" = "$LOCAL" ]; then sh -c "$*" 2>&1 || true
    else ssh -o BatchMode=yes "$host" "$@" 2>&1 | grep -v '^Pseudo-terminal' || true; fi
}
# Same, but keeps the command's exit status and stderr apart: launch and batch
# print JSON for agents, who need a failure to fail.
on_strict() {
    host=$1; shift
    if [ "$host" = "$LOCAL" ]; then bash -c "$*"
    else ssh -o BatchMode=yes "$host" "$@"; fi
}
# GPU authentication belongs to the hub; clients do not need cluster keys.
on_gpu() {
    local target=$1 command
    shift
    if [ "$HUB" = "$LOCAL" ]; then on "$target" "$@"
    else
        printf -v command '%q' "$*"
        on "$HUB" "ssh -o BatchMode=yes $target $command"
    fi
}
# Strict variant for launches: exit status and stderr pass through.
on_gpu_strict() {
    local target=$1 command
    shift
    if [ "$target" = "$LOCAL" ]; then bash -c "$*"
    elif [ "$HUB" = "$LOCAL" ]; then ssh -o BatchMode=yes "$target" "$@"
    else
        printf -v command '%q' "$*"
        ssh -o BatchMode=yes "$HUB" "ssh -o BatchMode=yes $target $command"
    fi
}
tunnel() { [ "$HUB" != "$LOCAL" ] && [ -x "$HERE/rdash_remote.sh" ]; }

# Fast-forward only, and only over a clean tracked tree: a hub or GPU checkout
# with local edits is someone's work in progress, never something to merge over.
# A root `git submodule update` detaches the checkout at the root's pinned (often
# old) commit; reattach to main only when that commit is already in origin/main.
pull() {
    on "$1" "cd $2 2>/dev/null || { echo '$1: no research checkout; skipped'; exit 0; }; if [ -n \"\$(git status --porcelain --untracked-files=no)\" ]; then
        echo '$1: tracked changes present, not pulling:'; git status --short --untracked-files=no | head;
    else git fetch -q origin &&
        if ! git symbolic-ref -q HEAD >/dev/null; then
            if git merge-base --is-ancestor HEAD origin/main && git merge-base --is-ancestor main origin/main; then
                echo \"$1: was detached at \$(git log --oneline -1 | cut -c1-60); reattaching to main\"; git checkout -q main;
            else echo '$1: detached with commits not on origin/main; not touching it'; exit 0; fi
        fi && git merge -q --ff-only origin/main && echo \"$1: \$(git log --oneline -1)\"; fi"
}

case "${1:-}" in
status)
    printf 'local: %s  %s\n' "$(git -C "$HERE" log --oneline -1)" "$(git -C "$HERE" status -sb | head -1)"
    on "$HUB" "cd $HUB_ROOT && echo \"$HUB: \$(git log --oneline -1)\" && { b=\$(git symbolic-ref -q --short HEAD) || b=; [ \"\$b\" = main ] || echo \"  WARNING: board checkout is on '\${b:-detached HEAD}', not main: it serves that, and the sync is blocked\"; } && git status --short | head -5 && $ENV $TOOL/dashboard/app/research_dash.sh status && { cat \${RESEARCH_DASH_CACHE:-\${XDG_CACHE_HOME:-\$HOME/.cache}/rdash-\$(basename $HUB_ROOT)}/sync.json 2>/dev/null | sed 's/^/sync: /' || echo 'sync: never ran (enable the rdash sync timer)'; echo; }"
    for g in $(echo "$GPUS" | tr ',' ' '); do
        on_gpu "$g" "{ [ -n '$GPU_ROOT' ] && cd $GPU_ROOT 2>/dev/null && echo \"$g: \$(git log --oneline -1)\"; } || echo \"$g: no team checkout (launch does not need one)\"; squeue --me -h -o '  %i %j %T %M' | head -20"
    done
    if tunnel; then
        if "$HERE/rdash_remote.sh" status 2>/dev/null | grep -q 'tunnel: up'; then echo "tunnel: up"
        else echo "tunnel: down (run: rdash)"; fi
    fi
    ;;
deploy)
    if git -C "$HERE" status -sb | head -1 | grep -q 'ahead'; then
        echo "hub.sh: local commits are not pushed; push first" >&2; exit 1
    fi
    pull "$HUB" "$HUB_ROOT"
    [ -z "$GPU_ROOT" ] || for g in $(echo "$CHECKOUTS" | tr ',' ' '); do pull "$g" "$GPU_ROOT"; done
    on "$HUB" "cd $HUB_ROOT && $ENV $TOOL/dashboard/app/research_dash.sh stop >/dev/null; $ENV $TOOL/dashboard/app/research_dash.sh start"
    if tunnel; then "$HERE/rdash_remote.sh" start >/dev/null && echo "tunnel: up"; fi
    ;;
launch)
    # Submit from where the code lives: on a host with a research checkout, run
    # rsub there against origin/main; otherwise (bc) the hub stages it over SSH.
    # Either way the record is a receipt beside the run, collected by the hub.
    usage="usage: hub.sh launch <project> <cards/file.md> [--step <step>] [--test-only]"
    [ $# -ge 3 ] || { echo "$usage" >&2; exit 1; }
    project=$2 card=$3 extra= step=; shift 3
    case "$project$card" in *[!A-Za-z0-9._/-]*) echo "hub.sh: invalid project or card" >&2; exit 1 ;; esac
    while [ $# -gt 0 ]; do
        case "$1" in
        --test-only) extra="$extra --test-only" ;;
        --step) [ $# -ge 2 ] || { echo "$usage" >&2; exit 1; }
                case "$2" in [a-z]*) ;; *) echo "hub.sh: invalid step" >&2; exit 1 ;; esac
                case "$2" in *[!a-z0-9-]*) echo "hub.sh: invalid step" >&2; exit 1 ;; esac
                step=" --step $2"; shift ;;
        *) echo "hub.sh: unknown option $1" >&2; exit 1 ;;
        esac
        shift
    done
    tool=$(cd "$HERE/../.." && pwd); repo=$tool
    [ -d "$repo/projects" ] || repo=$(cd "$repo/.." && pwd)   # rdash as a submodule: the team repo is one level up
    git -C "$repo" fetch -q origin main || { echo "hub.sh: could not fetch origin/main" >&2; exit 1; }
    host=$(cd "$repo" && PYTHONPATH=$tool RDASH_SSH_HOSTS= python3 -B -m dashboard.app.launch --project "$project" --card "$card" --ref origin/main$step --print-host) || exit 1
    run="git fetch -q origin main && $TOOL/dashboard/bin/rsub $project $card --ref origin/main$step$extra"
    case ",$CHECKOUTS," in
    *",$host,"*) [ -n "$GPU_ROOT" ] || { echo "hub.sh: RDASH_GPU_ROOT is unset for checkout host $host" >&2; exit 1; }
                 on_gpu_strict "$host" "cd $GPU_ROOT && $run" ;;
    *) on_strict "$HUB" "cd $HUB_ROOT && $run" ;;
    esac
    ;;
runs)
    [ -z "${2:-}" ] || case "$2" in *[!A-Za-z0-9._-]*) echo "hub.sh: invalid project" >&2; exit 1 ;; esac
    on_strict "$HUB" "cd $HUB_ROOT && $ENV PYTHONPATH=$TOOL python3 -B -m dashboard.app.receipts unrecorded${2:+ --project $2}"
    ;;
attach)
    usage="usage: hub.sh attach <host> <job> <project> [cards/file.md] [--note TEXT]"
    [ $# -ge 4 ] || { echo "$usage" >&2; exit 1; }
    shift
    args=(--host "$1" --job "$2" --project "$3"); shift 3
    if [ $# -gt 0 ] && [ "$1" != --note ]; then args+=(--card "$1"); shift; fi
    if [ $# -gt 0 ]; then [ "$1" = --note ] && [ $# -eq 2 ] || { echo "$usage" >&2; exit 1; }; args+=(--note "$2"); fi
    on_strict "$HUB" "cd $HUB_ROOT && $ENV PYTHONPATH=$TOOL python3 -B -m dashboard.app.receipts attach$(printf ' %q' "${args[@]}")"
    ;;
sync)
    on_strict "$HUB" "cd $HUB_ROOT && $ENV $TOOL/dashboard/app/rdash_sync.sh"
    ;;
batch)
    # hub.sh batch new <project> --name N --date D --set k=v ...
    # hub.sh batch status <project> <cards/batch-...md>
    # hub.sh batch tick <project> <cards/batch-...md> --step S --result "..." [--skip]
    usage="usage: hub.sh batch new|status|tick <project> [<cards/batch-...md>] [options]"
    [ $# -ge 3 ] || { echo "$usage" >&2; exit 1; }
    cmd=$2 project=$3; shift 3
    case "$cmd" in new|status|tick) ;; *) echo "$usage" >&2; exit 1 ;; esac
    case "$project" in *[!A-Za-z0-9._-]*) echo "hub.sh: invalid project" >&2; exit 1 ;; esac
    if [ "$cmd" != new ]; then
        [ $# -ge 1 ] || { echo "$usage" >&2; exit 1; }
        case "$1" in *[!A-Za-z0-9._/-]*) echo "hub.sh: invalid card" >&2; exit 1 ;; esac
        set -- --card "$@"
    fi
    on_strict "$HUB" "cd $HUB_ROOT && $ENV PYTHONPATH=$TOOL python3 -B -m dashboard.app.batch $cmd --project $project$(printf ' %q' "$@")"
    ;;
jobs)
    for g in $(echo "${2:-$GPUS}" | tr ',' ' '); do
        on_gpu "$g" "echo '== $g'; squeue --me -o '%.8i %.40j %.10T %.10M %.20S %R'; sacct -X -n -S now-1days -o JobID%8,JobName%40,State%12,Start,End | tail -10"
    done
    ;;
*)
    sed -n '3,12p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
