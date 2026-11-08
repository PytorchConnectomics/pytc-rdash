# rdash — the research tooling shared by the jams

The board (`dashboard/`), the probe protocol (`probe/`), the planner-loop handoff templates
(`rloop/focus/planner-loop/`), the agent skills (`skills/`), coding standards and reusable
library docs (`tools/`). **No project content lives here.** Projects live in the team repos,
`pytc-jam` (BC) and `pytc-jam-msi` (Mindspan), which consume this repository as a submodule at
`rdash/`; so does DW's private `dw-research`.

One upstream, three consumers: a board fix made by either team lands here through a PR and
reaches the other team on the next submodule bump, never through a copy.

## Using it from a team repo

```bash
git submodule update --init rdash
RDASH_REPO_ROOT=$(pwd) python3 -m rdash.dashboard.app.server   # the board reads projects/ of the repo it runs in
```

Host tables, runs roots and cluster facts are per team and live in each team repo's
`projects/config/`, not here. `skills/rdash/SKILL.md` in each team repo is that team's copy.

## Contributing

PRs only; tests must pass:

```bash
python3 -m unittest discover -s dashboard/tests -t .
python3 -m unittest discover -s probe/tests -t .
```

Seeded 2026-11-08 from `dw-research` by its exporter (history-free). The `SHARED_FROM.json`
marker records the source revision; it is informational once this repository is canonical.
