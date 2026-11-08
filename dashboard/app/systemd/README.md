# systemd units for a team hub

The board runs on the team's always-on hub as a user service, from a service-only
clone of the **team repository** with `rdash/` initialised as its submodule. These
are templates: copy them to `~/.config/systemd/user/`, replace `TEAM_REPO` with the
clone's directory name under `$HOME` and the `Environment=` values with the team's
hosts, then `systemctl --user daemon-reload && systemctl --user enable --now
<name>.service <name>-sync.timer`.

| Unit | Does |
|---|---|
| `rdash.service` | runs `rdash_service.py`, which starts the board through `research_dash.sh` and restarts it if its health check fails |
| `rdash-sync.service` + `.timer` | runs `rdash_sync.sh` every minute: collect run receipts, commit what the board wrote, rebase on `origin/main`, push |

Each team's installed copies (with real hosts) are recorded in that team's repository,
not here.
