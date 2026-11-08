# Skills — canonical methods and additional adapters

The scientific method is owned here by **[probe](../probe/SKILL.md)**, with
accepted procedure in `probe/protocol/` and proposed changes in `probe/reviews/`.
General reusable skills and the thin adapters below are owned by **dw-kb**.
Read only the selected skill; do not copy its definition into project notes.

Locate `kb/skills/` in a full dw-os checkout, or the sibling `dw-kb/skills/` in
a BC checkout (the established BC location is
`/projects/weilab/weidf/lib/dw-kb/skills/`). An explicitly supplied or installed
skill path also works. The catalog is also on GitHub (requires repository access):
[dw-kb/skills/SKILLS_INDEX.md](https://github.com/donglaiw/dw-kb/blob/main/skills/SKILLS_INDEX.md).

- **Full catalog/index:** `dw-kb/skills/SKILLS_INDEX.md` (includes the pinned Orchestra, LabClaw and AI Hero collections)
- **Software-engineering craft (AI Hero):** `dw-kb/skills/aihero/INDEX.md` —
  debugging, testing, module design, and writing for agents. These govern
  whether *code* is correct; `probe` governs whether a *scientific claim* is
  supported. Keep both.
- **Curated agent-repo adapters:** `dw-kb/skills/AGENT_REPOS.md` — literature
  triage, biomedical tool selection, evidence review, code surveys and ZGCM
  recipes. In dw-os these are linked into this repository's `skills/` for
  OpenClaw discovery; the editable definitions remain in dw-kb.
- **AI-Research-SKILLs** (Orchestra, by category): `dw-kb/skills/AI-Research-SKILLs/`
- **Advisory focus review:** `dw-kb/skills/research/research-depth/`
- **Preregistration adapter:** `dw-kb/skills/engineering/preregister-experiment/`
  resolves the project's adopted probe method; it does not duplicate gate rules.
- **Code conventions:** `dw-kb/skills/engineering/code-writing-rules/`
- **Performance and slides:** `dw-kb/skills/engineering/kaiming-ml-perf/`,
  `dw-kb/skills/slide/`

To use a skill, read its `SKILL.md` under `dw-kb/skills/` before starting.

Preferred for this lab (paths under `dw-kb/skills/`):

| Task | Skill |
|------|-------|
| Image segmentation | `AI-Research-SKILLs/18-multimodal/segment-anything/` |
| Multi-GPU training | `AI-Research-SKILLs/08-distributed-training/pytorch-lightning/` |
| Training monitoring | `AI-Research-SKILLs/13-mlops/tensorboard/` |
| Training recipes | `AI-Research-SKILLs/10-optimization/ml-training-recipes/` |
| Paper figures / writing | `AI-Research-SKILLs/20-ml-paper-writing/` |
| Research ideation | `AI-Research-SKILLs/21-research-ideation/brainstorming-research-ideas/` |
| Full autonomous research | `AI-Research-SKILLs/0-autoresearch-skill/` |
| Advisory focus/pivot review within an assigned project | `research/research-depth/` |
| Preregistration through the project's adopted probe protocol | `engineering/preregister-experiment/` |
| Code discipline | `engineering/code-writing-rules/` |
| A hard bug or a performance regression in research code | `aihero-skills/skills/engineering/diagnosing-bugs/` |
| Deciding what to test, and where the seam goes | `aihero-skills/skills/engineering/tdd/` with `aihero-skills/skills/engineering/codebase-design/` |
| Sharpening an underspecified request before building | `aihero-skills/skills/productivity/grilling/` |
| Writing or editing a `CLAUDE.md`, `SKILL.md`, or any agent-read doc | `aihero-skills/skills/productivity/writing-for-agents/` |

## Bundled here

- **[probe](../probe/SKILL.md)** — the scientific experiment loop (see above).
- **[radd-hypo](radd-hypo/SKILL.md)** — write one hypothesis or task as a
  self-contained contract card under `projects/<project>/cards/`, validated by
  `probe/scripts/check_readiness.py`, so a fresh Claude or Codex session can
  execute it from the card alone. Install by symlink, as with `probe/`:
  `ln -s "$PWD/skills/radd-hypo" ~/.claude/skills/radd-hypo`.

- **[radd-task](radd-task/SKILL.md)** — capture one unit of work as a job card in
  a project's `jobs` column, with the real submit commands and a `probe-status`
  fence tracking its artifacts and SLURM jobs. Triggered by a prompt starting
  `radd-task:`. Use `radd-hypo` instead when the request is really a question.

(`resume-fleet.sh` stays in this repo — it's an operational fleet script, not a skill.)
