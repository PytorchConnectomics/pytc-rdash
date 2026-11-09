# Research dashboard cards

Research cards were merged from `dw-os/kb/research/` into this workspace on
2026-09-15. Each project keeps cards alongside its scientific memory:

```text
projects/<project>/
  spec.md / state.yaml  # Existing scientific definition and state
  cards/*.md            # Hypotheses, ideas, linked probes and sessions
  cards/inbox/*.md      # Human ideas captured through rdash
  research_plan/        # Existing plans/preregistrations where used
  lessons/              # Existing conclusions and their supporting evidence
  logs/                 # Observations and handoffs
```

## Start here

- [NISB cards](../projects/nisb-base-26/cards/README.md)
- [Card template](TEMPLATE.md)
- [Research workspace](../README.md)

The new [goal supervisor](supervisor/README.md) provides an explicitly activated,
governed SLURM execution backend and goal routes. Its observed in-flight work
feeds the existing `agent` owner tier through augmented sessions; authored
session declarations are preserved. The goal detail panel shows budgets,
decisions and available evidence. See the supervisor's current scope and
limitations for execution and live verification.

Copy the template into a project's `cards/` directory. Required frontmatter:
`id`, `title`, `project`, `track`, `stage`, `created`, `updated`. The `project`
value must match its project directory. Keep IDs stable across renames.
Optional `task:` groups several cards under one piece of the project's work;
the conventional values are `data`, `model`, `deployment` and `evaluation`, and
any other plain value is allowed. `track` names the planned approach(es) the card
serves, comma separated (`track: clahe, 8-bit`); `shared` marks a prerequisite of every
track in its task. Optional `cube:` (comma separated) names the target volume(s); omitted
means every cube. A project declares its tracks and runs (one track per task, on one cube)
in an `rdash-tracks` JSON fence under `## TRACKS` in `spec.md` (format and segmentation
skeleton: `projects/TEMPLATE/spec.md`); the **Milestones** view shows each track's cards in
its milestone's row, derived from the cards (`dashboard/app/tracks.py`). An optional
top-level `tasks` list in the fence fixes the project's task columns and their order.
Stages are `idea`, `formulating`, `probing`, `reviewing`, and `parked`.
Card stage is distinct from job status, measurement validity, and scientific verdict.

Optional `state:` is the one signal an agent thread declares (`working`, `needs-you`,
`paused`, `done`; `dashboard/app/needs_you.py`). `needs-you` is the bell: it is read
before any inferred owner, and it is valid only with a `## Needs you` section of one to
three numbered options and a `Recommendation:` line (template). Focus notebooks
(`projects/<p>/focus/F-*.md`) carry the same field. Across checkouts,
`python3 -m rdash.dashboard.app.needs_you <workbench roots...> [--write status.json]`
lists what needs a person without a second board; keep the written file git-ignored.

Cards are entry points for ideas and evidence, not duplicate experiment ledgers.
Link accepted plans, results, and lessons in their existing canonical locations.
Preserve original predictions and append human guidance and proposed revisions.
Keep source dates and uncertainties; old lessons retain their original scope.
Do not infer a current scientific verdict from a historical file's location.

## Local dashboard

The board is implemented in this repository using Python 3.9+ and plain static
HTML/CSS/JavaScript. No packages or external network requests are required.

The dropdown remembers one project. Projects appear from existing project directories with a `spec.md` or `cards/`, including empty boards;
only `projects/*/cards/*.md` and `projects/*/cards/inbox/*.md` are scanned.
README and hidden files are skipped; other unsupported entries are counted in
the board's ignored-paths note.
New ideas are saved under that project's `cards/inbox/`. Refresh reads current
files. Stage changes and appended notes use revision checks and pre-edit backups.
The board observes jobs on configured hosts; generic session launching and
harvesting remain unimplemented. Switching project changes only the view. Keep
local mount paths and execution caches outside tracked cards.

## Run it from this repo

```sh
dashboard/app/research_dash.sh start
dashboard/app/research_dash.sh status
dashboard/app/research_dash.sh stop
# Also supported: restart
```

Open the printed URL manually (default `http://127.0.0.1:8766`).
`RESEARCH_DASH_PORT` overrides the port; the launcher rejects port 0.
`RDASH_REPO_ROOT` selects a repository containing `projects/` and
`dashboard/TEMPLATE.md`. `RESEARCH_DASH_CACHE` overrides local runtime storage:
`~/Library/Caches/dw-research-dashboard` on macOS, otherwise
`${XDG_CACHE_HOME:-~/.cache}/dw-research-dashboard`. It holds logs, pidfile and
pre-edit backups. Startup and stop are serialized by a cache-local lock.
## Run it on the hub, view it locally

This is the intended deployment. The hub (g02 since 2026-10-19; hebb before) is
always on and runs the board in a service-only checkout that follows origin/main
(`dwos-rdash-sync.timer`, every minute: collect run receipts, commit what the
board wrote, rebase, push; see [RECEIPTS.md](RECEIPTS.md)). Receipts from the GPU
hosts are collected every 15 minutes (`RDASH_SLOW_HOSTS`, default `bc:900,cajal:900`), and a
polled host that does not answer turns the sync state to `warn` ("bc unreachable
since …") on the Runs view and in `hub.sh status` until it does. Cards are written in
git anywhere; launches leave receipts beside the run instead of editing cards.
GPU hosts (cajal, bc) are only inspected over SSH from g02, and only an SSH
tunnel crosses the network to the viewer:

```sh
dashboard/app/rdash_remote.sh start    # start on the hub, forward, print the URL
dashboard/app/rdash_remote.sh status
dashboard/app/rdash_remote.sh stop
```

Day to day, `dashboard/app/hub.sh status | deploy | launch | runs | attach | sync | jobs`
wraps these steps, the job launch and the receipts; see
[skills/rdash](../skills/rdash/SKILL.md). On g02 the board and the sync are user
services: `dwos-rdash.service` and `dwos-rdash-sync.timer` (unit files in `app/`).

`RDASH_HOST` (default `g02`), `RDASH_REMOTE_ROOT` (default
`/home/hanson/rdash/research`) and `RESEARCH_DASH_PORT` select the target.
`RDASH_SSH_HOSTS`, when set, is passed to the hub as the GPU hosts it may
inspect; `hub.sh` passes `cajal,bc`. Aliases:

```sh
alias rdash='/absolute/path/to/dw-research/dashboard/app/rdash_remote.sh start'
alias rdashstop='/absolute/path/to/dw-research/dashboard/app/rdash_remote.sh stop'
```

Why the board runs beside the cards rather than over a mounted filesystem: the
single-writer mechanism is a POSIX `flock` on `<repo>/.rdash.lock`, which does
not span an sshfs mount, so a locally-mounted board and cluster-side agents
would lock in unrelated domains and lose writes silently. The read path is also
metadata-heavy -- listing a project costs `(cards+1) x (projects+1)` directory
scans -- which is cheap on a local disk and slow across a WAN mount.

**The port must match on both ends.** `server.py` validates the `Host` header
against its own bound port, so `-L 9000:127.0.0.1:8766` returns 403. Forwarding
by hand:

```sh
ssh g02 RDASH_SSH_HOSTS=cajal,bc /home/hanson/rdash/research/dashboard/app/research_dash.sh start
ssh -f -N -L 8766:127.0.0.1:8766 g02
```

`rdash_remote.sh` owns its tunnel through a dedicated ControlMaster socket
rather than by matching process names: `ssh -f` rewrites its argv to just
`ssh <host>`, which is indistinguishable from other sessions to the same host,
including an interactive session or an agent driving the same host.

`start` also leaves a watcher (pid file beside the socket) that reopens the
tunnel within about 10 s of it dying, and replaces it after a detected sleep,
so a Mac sleep or network change heals without rerunning `rdash`. `stop`
kills the watcher; `status` reports it. The script's one-shot `ssh` calls
bypass a shared `ControlMaster auto` socket, which after a sleep can be dead
but still accept, hanging the call until keepalive gives up.

Capabilities: project selection, card reads, idea capture, discussion append,
stage changes, revision checks, and pre-edit backups. Unsupported frontmatter
is visible but read-only. Titles are sanitized on creation; the stored title is
displayed after saving. A declared session is displayed and linked out to, but
starting, attaching, observing or harvesting one is **not implemented**, and
neither are Start/Open/Harvest, handoffs, agent launching, or synthesis.
Evaluation writes are also deferred.

### Inspect evidence and return feedback

Open a card and use **Inspect evidence** to select up to two declared artifacts.
The panel displays bounded UTF-8 reports (`txt`, `log`, `md`, `json`, `csv`,
`tsv`) or PNG/JPEG images, with the host, path, observation time and content
digest. Each file is limited to 1 MiB. Comparison is visual; matching datasets,
samples, evaluators and budgets must still be established through the contract.

Artifacts must be declared in the card's existing `probe-status.artifacts`
mapping and lie under the configured host/root allowlists. No directory browser
or arbitrary-path endpoint is exposed. HTML, SVG, PDF and executable files are
not rendered. An inaccessible, changing, oversized or unsupported artifact
shows an explicit error rather than an empty successful preview.

After the preview loads, **Save evidence feedback** appends a note to the card's
existing **Ideas and discussion** section. The note includes a feedback ID,
artifact digest, card revision, host, path and observation time. Both revisions
are checked again at save time. If either changed, refresh and inspect the new
content before saving. Feedback does not change acceptance, launch an agent or
establish a scientific result. The next authorized agent session responds to
that feedback ID in the same discussion with its finding and evidence.

The routes are:

- `GET /api/evidence?project=...&card=...&revision=...&label=...` returns a text
  preview or a digest-bound image URL.
- `GET /api/evidence/content` accepts the same fields plus `artifact_revision`
  and serves only the matching PNG/JPEG bytes.
- `POST /api/evidence/feedback` accepts those identity fields plus `text`, uses
  the ordinary card writer and returns the updated card.

**Agent can investigate** routes routine evidence reading and reference repair
away from the human decision queue. It does not mean a worker was started.
**Coordinator in flight** uses the supervisor's observed signal. Scientific
verdicts, budget changes and uncertain execution authority still require a
person; a declared session alone never establishes liveness.

Mutual exclusion holds only between cooperating rdash writers, via POSIX
`flock` on the repository's gitignored `.rdash.lock`. The lock file remains in
place; kernel ownership ends when its descriptor closes or its process dies.
Revision checks and the `.agent-lock` courtesy check narrow but do not eliminate
races with editors or agents. An editor writing between rdash's locked re-read
and atomic replacement can lose its change; pre-edit backups are the recovery
aid, and may not include such an intervening edit. Fresh or unreadable agent
locks refuse mutations; locks older than six hours are allowed by this board's
contract, without claiming that an old agent or job has stopped.

Only loopback is supported. There is no authentication; do not expose the server
publicly or through a proxy. Host, Origin and custom mutation-header guards
protect browser requests; static serving is restricted to three bundled assets.

## Project views

Each project is a view containing many cards. `nisb-base` maps to
`projects/nisb-base-26/`; `nisb-liconn` maps to
`projects/nisb-liconn-26/`. They have independent cards and idea inboxes.
The selector uses readable labels while retaining stable directory IDs. Existing
NISB-base cards stay with base; they are not copied to LICoNN. Empty projects
can receive their first card through Add idea.

## Frontend design

See the [research-card-first frontend design](../.agent/frontend/design.md) for
the Start / Open / Harvest workflow and implementation plan.

## Engineering inspection board

**Milestones** (milestone × task matrix of questions and tracks) and **Tasks**, toggled in
the header and remembered per browser. In a project with `questions/` files, **Tasks** has one
column per question, headed by its tile, with the cards serving it below in id order (cards
serving none get a last column). Otherwise **Tasks** has one column per `task:` value (`data`, `model`,
`deployment`, `evaluation`, then other values, then `unassigned`), with that
task's cards below it, coloured by progress: green *done* (a recorded verdict:
`met`, `failed` or `inconclusive`), yellow *in progress* (a job queued or
running, jobs launched and no verdict yet, or stage `formulating`, `probing` or
`reviewing`), red *todo* (anything else). Finished jobs alone never turn a card
green. The Task filter applies to both views.

The card list shows the title and the owning session; task, track, id, authored stage
and updated date are the row's tooltip, since each is already a filter or the
sort key rather than something to read per row. Live job badges sit in Jobs.
The detail view shows a job/status strip, Result vs. contract, authored contract,
live artifacts, and discussion. The generated `radd-status` block remains in
card bytes but is collapsed below live artifacts, labelled with generation age
(or unknown age). Refresh reads observations without running `--write`.
The raw toggle still shows the complete original card body.

The board's Contract column lists the card's own method steps: the numbered
subheadings under the heading its `probe-contract` `method` reference names,
read only when that reference points into the same card. A method held in
another file is named, not restated, and an unnumbered subsection beside the
steps (traps, sizing) is prose rather than work. No step carries `DONE`,
`CURRENT`, `TODO` or `BLOCKED` unless a card records one, and the board does not
derive one. Contract structure comes from `probe/scripts/check_readiness.py` and
appears in the detail view rather than the column: it reads the same on every
passing card, and it certifies neither authority nor evidence. Authored
acceptance and verdict remain visible and read-only. Health, staleness sorting,
and log tails are not implemented. Completed jobs do not establish correctness.

The session sits under the card title, not in a column of its own: it names who
owns the card, and a column of `not declared` spent a sixth of the width saying
nothing. It answers where a session is, not whether it is running. Each declared
session shows its `host` and `cwd` beneath its label -- the machine and working
directory to reattach at -- and shows nothing when the card gives neither, since
the label above already says a session owns the card. A session is rendered as a
link when the card gives its `id`: a
`claude` provider opens at `claude://claude.ai/epitaxy/<id>`, handled by the
Claude desktop app on whichever machine displays the board. The card carries the
session's identity; the board builds the client URL.

Session liveness is deliberately not tracked. A desktop session leaves no
transcript the board could stat, and a cluster session's `bridge-pointer.json`
records a pid without the login node it belongs to, so a pid check would answer
confidently and wrongly. Nothing here claims a session is up, and the Next
column has no rule that fires on one.

`dashboard/app/inspect.py` is shared by the board and `radd_status.py`. Metadata,
scheduler and content use independent subprocess channels on both local and
SSH hosts. Metadata and scheduler stdout are capped at 256 KiB; content stdout
at 4 MiB per call, with complete records retained after a truncated tail. Calls
are chunked at 250 items / 256 KiB input. The default exchange deadline is 30 s;
cleanup can add at most 2 s, with unreaped children polled on later calls.
Cache entries expire after 10 s, independently by host, channel, item and root
policy; a host lock covers collection through publication.

Artifact probing is disabled by default. `RDASH_STAT_LOCAL=1` enables local
metadata/content inspection; `RDASH_HOST_ALIAS` also enables local inspection
and maps that declared alias to this machine. `rdash_remote.sh` supplies its
alias. `RDASH_SSH_HOSTS` lists permitted remote SSH aliases, comma-separated.
SSH requires Python 3 and a previously trusted host key; keys are never enrolled.
Paths travel in JSON stdin, never in transport argv. An unreachable host yields
unknown. Only ENOENT/ENOTDIR metadata errors establish absence.
`RDASH_STAT_ROOTS` optionally restricts metadata paths lexically; metadata is
not a content read and can traverse intermediate symlinks.

### Results and content roots

Declare measurements in the existing JSON `probe-status` fence:

```json
{"results": [{"name": "val NERL", "path": "results/metric.json", "key": "nerl",
  "baseline": 0.604428, "direction": "higher", "source": "contract baseline reference"}]}
```

The author copies the baseline from the contract. The board never infers it or
writes a verdict. With no baseline it shows a measurement, without delta.
Only finite JSON numbers qualify (booleans and strings do not). JSON files are
limited to 1 MiB, read in 64 KiB chunks. Missing files show absent; malformed
JSON, missing keys, excessive nesting or nonnumeric values show unreadable,
never zero. CSV is unsupported. Keys use at most eight dot-separated segments
matching `[A-Za-z0-9_-]+`; numeric segments index lists or select object keys.
Literal dots in an object key cannot be selected. JSON nesting is capped at 32.
Direction only colors the delta. The source is displayed alongside the value.

Default local content roots are `projects/<project>/results/` and `logs/`.
Relative result paths are project-relative on the board host; remote results
require absolute host paths. External roots require an operator
file at `projects/config/rdash-roots.yaml`. This implementation **does not create
that file**. It accepts only this restricted YAML shape (unquoted absolute paths;
full-line comments and blank lines allowed):

```yaml
local:
  - /resolved/absolute/results
bc:
  - /resolved/absolute/remote/results
```

`local` and the configured host alias refer to this board's host. Other keys
must be permitted SSH aliases. Root symlinks resolve once at configuration load,
on the owning host; restart after changing policy. Configuration-time remote
resolution adds a bounded transport call, separate from observation refreshes.
An unavailable remote root policy yields `root_unavailable` for content rows.
Defaults are captured for projects present at startup; restart after adding a
project. A vanished root also reports `root_unavailable`.

Reads walk directory descriptors from the resolved root, refusing symlinks in
any subsequent component (stricter than merely refusing symlink escapes).
The final object's type is checked before opening: FIFO, device, socket and
directory results are refused. The opened regular file must match the checked
inode/device; size limits are enforced during reading. Anything outside roots
shows `outside declared roots`; metadata remains independently available.

CLI output retains its existing shape, local-time mtime formatting and array
text. It now reports non-missing filesystem failures as unknown and discards
SLURM step records such as `.extern`. The board reduces array tasks with active,
then failed, then completed precedence; the CLI retains per-task descriptions.
Live SSH/BC scheduler integration must be verified on BC; local fixtures do not
establish that integration.
