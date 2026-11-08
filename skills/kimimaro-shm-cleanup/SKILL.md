---
name: kimimaro-shm-cleanup
description: Find and remove orphaned kimimaro shared-memory segments in /dev/shm, and make kimimaro Slurm jobs clean up after themselves. Use when swap or /dev/shm is near full on a cluster node (cajal), after cancelling or timing out kimimaro skeletonization jobs, or when writing an sbatch script that runs kimimaro with parallel > 1.
---
# kimimaro-shm-cleanup — free RAM pinned by killed kimimaro runs

With `parallel > 1`, kimimaro shares the labels and distance field through
`/dev/shm/kimimaro-shm-cc-labels-<uuid>` and `/dev/shm/kimimaro-shm-dbf-<uuid>`.
A normal exit deletes them. A killed run (`scancel`, time limit, OOM) leaves them
behind. `/dev/shm` is RAM-backed tmpfs, so leaked segments pin memory until reboot,
and under pressure the kernel can only push them to swap.

On cajal, 2026-10-15: 39 GB of leaked segments from Oct 8–14 runs had filled the
8 GB swap. No process owned the swap and si/so were 0, so nothing was slowed yet,
but the next large job would have had no swap headroom.

## Diagnose

```bash
free -h; df -h /dev/shm
vmstat 1 5                     # si/so > 0 sustained = swap is actually hurting
awk '/^VmSwap/{s+=$2}END{print s/1024" MB swapped by processes"}' /proc/[0-9]*/status
```

Full swap, near-zero process swap and a large `/dev/shm` mean leaked shared memory.

## Clean up

```bash
S=~/dw-os/research/skills/kimimaro-shm-cleanup
$S/shm_clean.sh --dry-run      # list what would go
$S/shm_clean.sh                # remove it
```

The script removes only `kimimaro-shm-*` files that the caller owns, that no process
has open or mapped (`fuser`), and that are older than `--min-age` minutes
(default 10). Live runs are never touched. Use `--pattern` for other leakers
(for example `'sem.mp-*'`; those are tiny).

Swap drains as pages are touched or freed. It does not drop to zero at once, and
that is harmless.

## Prevent: sbatch template

Bash runs a trap only when it is not blocked on a foreground child, so run the work
in the background and `wait`. `--signal=B:TERM@120` makes Slurm signal the batch
shell 2 minutes before the time limit; `scancel` sends SIGTERM first by default.

```bash
#SBATCH --signal=B:TERM@120
S=~/dw-os/research/skills/kimimaro-shm-cleanup
cleanup() { kill "$PID" 2>/dev/null; wait "$PID" 2>/dev/null; $S/shm_clean.sh --min-age 0; }
trap cleanup EXIT TERM INT
python skeletonize.py ... &    # kimimaro with parallel > 1
PID=$!
wait "$PID"
```

`--min-age 0` is safe here because the in-use check still protects segments that
other running jobs hold open. A plain SIGKILL (OOM killer, `scancel -s KILL`)
cannot be trapped; run `shm_clean.sh` by hand or at the start of the next job.

## Related: swap size

cajal has an 8 GB `/swap.img`. Enlarging it or lowering `vm.swappiness` needs sudo.
Fix leaks first; a bigger swap only delays the problem.
