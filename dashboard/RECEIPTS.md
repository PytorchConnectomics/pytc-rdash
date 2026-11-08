# rdash: cards in git, receipts beside the run, g02 as the index

DW, 2026-10-23. Replaces "the hub is the only writer of job IDs" (2026-10-19).

## Why

A card used to hold three kinds of data that change in different ways:

| Data | Example | Written by | Changes |
|---|---|---|---|
| Intent and conclusions | question, design, verdict, discussion | DW and agents, on any machine | slowly; prose; needs history |
| Run receipts | job ID, host, code commit, command, output folder | whatever submitted the job | once per run, never edited |
| Live state | queued, running, failed | Slurm | constantly; never stored |

Live state was already right (the board reads it and stores nothing). Writing
receipts *into* the card is what forced the rest: only the hub could launch, only
the hub could write a job ID, scripts were staged from the hub's copy, and
`rdash-launch` round-tripped through git so the hub could commit the ID. Keeping
receipts out of the card removes those rules.

## The design

1. **Cards are plain git files.** Write and edit them on any machine; commit and
   push as usual. The board on g02 serves a service-only clone
   (`/home/hanson/rdash/research`, branch `main`) that the sync keeps equal to
   origin/main, so a pushed card shows within about a minute. It is not g02's
   dw-os submodule (`~/dw-os/research`), where agent sessions do their work.
2. **Receipts live with the run.** A submission writes one receipt on the host
   that runs the job, next to its results, and never edits the card:
   - `dashboard/bin/rsub <project> cards/<card>.md [--step S] [--test-only] [--ref R]`
     writes `<runs root>/<project>/receipts/<job>.json` (`dashboard/app/launch.py`);
   - `fsubmit` (focus questions on cajal) writes `/data/runs/focus/receipts/<job>.json`
     naming its F-id (`rloop/focus/bin/fsubmit`).

   A receipt records the research revision and scripts tree, the staged snapshot,
   the results folder, the sbatch argv, who submitted it, and the code commit of
   the launch's `code` path (or its `cwd`, when that is a git work tree).
   Uncommitted code does not block a launch: the diff is saved as `<job>.patch`
   beside the receipt and the receipt says `dirty`. Credentials in a remote URL
   are stripped.
3. **g02 only reads.** `dwos-rdash-sync.timer` runs `dashboard/app/rdash_sync.sh`
   every minute: it collects new receipts over SSH into
   `projects/<project>/runs/<host>-<job>.json` (focus receipts go to the project
   whose `focus/<F-id>.md` exists), commits what rdash wrote (`projects/*/cards`,
   `projects/*/runs`) under the board's writer lock, rebases onto origin/main and
   pushes. Nothing connects *to* g02, and while g02 is down jobs still run and
   leave receipts; the next sync picks them up.
4. **Unrecorded runs are listed, not blocked.** The board's **Runs** view (and
   `hub.sh runs [project]`) lists this user's jobs since 2026-10-23 (at most the
   last 7 days) on each host that no receipt and no card fence names, grouped by
   allocation, with the project guessed from the working directory. Prototype
   freely; when a run turns out to matter, `hub.sh attach <host> <job> <project>
   [cards/<card>.md] [--note TEXT]` records it after the fact (`via: attach`).
5. **Results and review are unchanged.** Jobs write their outputs under the run's
   `results/`; the evidence panel reads declared artifacts; the verdict is
   written in the card, in git.

## Where things run

| Machine | Role |
|---|---|
| cajal | code, GPUs, `rsub` and `fsubmit`, receipts under `/data/runs` |
| bc | GPUs; no research checkout, so `hub.sh launch` stages bc cards from g02 over SSH (same receipt) |
| g02 | the index: board, receipt collection, one-minute sync, cluster keys for clients |
| hebb | focus workers, which submit through `fsubmit` on cajal |
| Mac / phone | view through the tunnel (`rdash`) or voice; launches go through `hub.sh launch` |

`hub.sh launch <project> <card>` from any machine fetches origin/main, reads the
card's host, and runs `rsub --ref origin/main` on that host when it has a research
checkout (`RDASH_CHECKOUT_HOSTS`, default `cajal`); otherwise on g02, which stages
over SSH. A session on cajal can run `dashboard/bin/rsub` directly from its own
checkout once card and scripts are committed.

## Rules

- **The board checkout is service-only.** Never develop or switch branches in
  g02's `~/rdash/research`; work in `~/dw-os/research`, a worktree, or another
  machine. (Until 2026-10-23 the board served `~/dw-os/research`, and agent
  sessions kept switching its branch under the board.) The sync refuses
  to run when it is off `main` or has tracked changes outside `cards/` and
  `runs/`, and says so in `hub.sh status` and on the Runs view.
- **A receipt is written once.** Neither side rewrites one; a correction is a
  note in the card's discussion.
- **Card fences stay readable.** Job IDs recorded in `probe-status` fences before
  2026-10-23 are still observed; new launches add none.
- **One GPU host per project** and BC's GPU-selection rules are unchanged
  (`skills/rdash/SKILL.md`).

## Failure modes

| Symptom | Meaning | Fix |
|---|---|---|
| `sync: blocked … not main` | someone switched the board checkout | put the work on a branch elsewhere, `git -C ~/rdash/research checkout main` on g02 |
| `sync: blocked … tracked changes` | uncommitted non-card edits on g02 | move them out; the sync never commits or stashes them |
| `sync: conflict` | a board edit and a pushed edit touched the same card lines | resolve in g02's checkout (`git rebase origin/main`), then `hub.sh sync` |
| `unrecorded_job` from rsub | job submitted, receipt not written | the message gives the `hub.sh attach` command |
| `staging_failed … File exists` | a snapshot directory without `.rdash-complete` (not made by `launch.py`) | inspect and remove that directory by hand; launch.py never overwrites one |
| receipt skipped in collect output | malformed, wrong host/job, or unknown project | read `<cache>/collect.json` on g02 |

## Verification (2026-10-23)

- Test suite: receipts, sync (against real git repos), launch and batch tests.
- `rsub --test-only` from g02 to cajal (SSH staging) and locally on cajal.
- One real launch of a project's `cards/<date>_rdash-launch-smoke.md`
  from a scratch clone on cajal: job 2704, receipt written by `rsub`, collected
  on g02, joined to the card by the board. The job itself FAILED in its own
  script: the smoke card's cube path
  (a large OME-Zarr input on the execution host)
  no longer exists. That is the smoke script's input, not the launch path.
