> **Historical record — relocated 2026-09-09.** Source: `research/meta/claude_code_workflow.md`. Historical review from the June 26 NISB session. Proposed mechanisms and “built/not yet wired” statuses below are dated evidence, not the current probe protocol. The original body below is preserved byte-for-byte, including historical paths, statuses, and quotations.

**Current crosslink map** (use these links instead of interpreting old relative links from the new location):

- `research_process.md` → [Historical NISB process analysis](../../projects/nisb-base-26/retrospectives/2026-06-26/research_process.md)
- Related session → [Historical NISB review](../../projects/nisb-base-26/retrospectives/2026-06-26/README.md)
- Current method → [Probe protocol](../protocol/PROBE_PROTOCOL.md)

Historical runtime and transcript paths in the body remain evidence of the original context; this relocation does not verify or remap those external files.

**Original source revision:** [b3e39c0](https://github.com/donglaiw/dw-research/blob/b3e39c09d4a1ff43fbdd097465ac6af1bd8bb6f8/meta/claude_code_workflow.md); body SHA-256 `2ab9e4c2f3bfbc38523f66d3a4d96fcdf3a15265dbeac1c8c03c4e0f01c3ccf6`.

<!-- ORIGINAL HISTORICAL BODY — preserved byte-for-byte below -->

# Using Claude Code effectively for research coding

You're an advanced user (`loop.md`, prereg headers, node-LUT cheap gates, CCC, the
`probe` skill, the memory index). So this isn't "prompt better" — it's closing the
gap between the discipline you've *written down* and what the agent actually
*enforces*. The meta-pattern: your process lives in docs you follow by hand, and
the agent's natural bias (toward analysis and plans) amplifies exactly the
diagnosis-drift in [`research_process.md`](research_process.md).

Each principle below is paired with a concrete mechanism and its current status.

### 1. Move invariants from a doc you read into a gate the agent enforces
Your `loop.md` §4 invariants are prose you have to remember to apply; seven lessons
re-deriving "needs object-context" is the proof they weren't binding.
- **Mechanism.** Put I1–I5 and "no GPU run without a prereg header" where the agent
  reads them every session, plus a hook that refuses expensive launches.
- **Status.** Built: `projects/nisb-base-26/CLAUDE.md` (auto-loads under `projects/nisb-base-26/`),
  `dev/nisb/scripts/prereg_gate.sh` (PreToolUse hook). **You still need to** wire
  the hook into `.claude/settings.json` (or `~/.claude/settings.json` for fleet
  worktree roots).

### 2. Make "research/plan" requests end in one runnable experiment, not a survey
The Jun 20–21 deep-research burst is the tell — the agent will produce elaborate
plans all day because they're low-risk deliverables, and that displaces the run.
- **Mechanism.** End planning asks with "produce exactly one preregistered
  cheap-gate experiment I can run today; no survey." Default to the `probe` skill
  for "should I try X." Cap at one deep-research doc per *landed* lesson.
- **Status.** Behavioral; the `skills/collection/preregister-experiment` skill encodes the
  header to demand.

### 3. Delegate measurement to sub-agents; keep selection for yourself
Fan-out reads ("sweep these 27 chunks, report the per-chunk NERL distribution") are
ideal sub-agent jobs and keep the bulk out of your main context. But *select* (what
to try next, off `state.yaml`) is where the "keep confirming the wall" drift crept
in — an agent will always find one more plausible variant.
- **Mechanism.** `Agent`/`Explore` sub-agents for measurement and broad reads; you
  + `state.yaml` for the next-experiment decision.
- **Status.** Pattern; used in this session (two reader agents over the transcripts).

### 4. Force the verdict artifact as the last step of a run, not a follow-up
`loop.md` §5 says a finished try produces a lesson + a `state.yaml` diff; lesson
12's hidden oracle→auto gap is what post-hoc verdicts cost.
- **Mechanism.** The run's final step is an agent call that drafts the
  `lesson_*.md` header→verdict and the `state.yaml` change from the actual output.
  A run isn't "done" until both exist.
- **Status.** Convention in `projects/nisb-base-26/CLAUDE.md` §3; not yet wired into a run script.

### 5. Have an agent add hard preflight asserts for your silent-failure class
random-init-on-bad-prefix, all-zero-output-on-HDF5-lock, ignored CLI overrides are
documented as things to *remember* — so they recur.
- **Mechanism.** One agent session: assert at each site (weight-load random-init
  detection, non-zero-output check after write, warn-on-ignored-override). Capture
  the "faithful reproducing command" per experiment family as a `just` recipe so
  stale-ckpt / wrong-prefix / cwd-import bugs stop being reconstructed by hand.
- **Status.** Proposed; good next agent task.

### 6. Use a second model specifically on branch-killing negatives
A false-positive win wastes one run; a false-negative *invariant* prunes a
possibly-good lever forever — the more expensive error.
- **Mechanism.** When a result would kill a branch (MALIS, SDT-ft), have
  `codex:rescue` or a `verify` sub-agent re-verify the measurement before you write
  the invariant into `state.yaml`. Routine wins don't need it.
- **Status.** Pattern; you already have the `codex` tooling.

## Cost / context hygiene
Your MEMORY + `state.yaml` + `lessons.md` index is the right pattern (small index →
drill down). Keep resisting the urge to dump whole `error_analysis/` into context;
point the agent at the index and let it fetch. Sessions that read 80k-token
transcripts should delegate that read (as this session did) rather than carry it.

## The through-line
Your diagnostic engine is better than your execution trigger, and Claude Code's
natural pull toward analysis and plans amplifies exactly that imbalance. Aim the
tooling the other way — agent-enforced gates, experiments-not-surveys,
verdict-as-exit-condition — so the easy path for both you and the agent becomes
shipping the risky run.
