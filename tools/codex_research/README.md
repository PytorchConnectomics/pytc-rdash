# codex_research

Research cards: ask the newest ChatGPT model (through the Codex CLI on hebb, with live web search) for a literature review or
for what to try next on a stuck problem. The answer is saved in the project and linked from the card.

- **Card:** `projects/<p>/cards/<date>_dr-<slug>.md`, id `<PROJ>-DR-NNN`, `task: research`, `question:` the question it serves. It needs a
  self-contained `## Prompt` section, because the model sees nothing else: the problem, what was tried with the measured numbers, the
  constraints, and the deliverable (ranked options, concrete experiments, cost, citations with URLs, and evidence separated from speculation).
- **Run (hebb):** `python3 tools/codex_research/run.py projects/<p>/cards/<card>.md` writes `projects/<p>/research/DR-NNN.md`, with a provenance
  header (model, effort, codex version, prompt sha). The raw log is `research/DR-NNN.log`, which is gitignored. Defaults: `gpt-6.1-sol`, effort `high`.
- **Follow-ups:** add `## Follow-up prompt N` to the same card (self-contained again: summarise what the earlier report said) and run with
  `--section "Follow-up prompt N" --suffix b` (c, ...).
- **Read it as leads.** Check any claim before it changes a plan. Record what was adopted on the card's Evidence and in the question.

The Codex CLI does not expose ChatGPT "deep research". The newest model with `--search` at high effort is the closest equivalent.
