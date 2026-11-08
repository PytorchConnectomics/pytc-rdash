# <YEAR> <Cluster> <Person> <Topic>

## GOAL
- **Task:** <1-3 lines: what, target objects, data modality>
- **Data modality:** <EM, confocal, etc.>

## TASK CONTRACT

Keep the contract in this spec or the selected existing task file. Link to
canonical sections instead of copying project state. Choose `engineering`,
`science`, or `exploration`; science also needs a `method` reference to the
existing adoption record. Do not invent a hypothesis for an engineering task.

The optional block below supports the read-only readiness checker. It checks
reference structure and local targets; it does not certify the contents or grant
permission to execute. Replace nulls only from the actual assignment.

```probe-contract
{
  "schema_version": 1,
  "kind": "exploration",
  "references": {
    "objective": "spec.md#goal",
    "acceptance": "spec.md#acceptance",
    "evidence": "spec.md#evidence",
    "authority": null
  }
}
```

### Acceptance

- **Deliverable / decision:** <what this task must produce or help decide>
- **Engineering checks:** <how correct execution is demonstrated>
- **Science, when applicable:** <question, competing explanations, evaluator,
  controls, and which observation changes the next decision>
- **Closest prior attempt:** <reference and material difference, if applicable>

### Evidence

- **Inputs and evaluator:** <permitted references and versions; unknowns explicit>
- **Expected outputs:** <artifact locations and verification command, where known>
- **Conclusion:** <owning run/lesson record; distinguish plans from observed results>

### Assignment and limits

- **Authority:** <existing task/instruction reference, allowed actions and host>
- **Resources:** <budget, prior consumption, remaining amount or unknown>
- **Stop / review conditions:** <when to stop or return a decision>

Point `references.authority` here after recording the actual assignment. Method
adoption and scientific state remain in their existing owners.

## ENVIRONMENT

### Paths
| Role | Path |
|------|------|
| Config | `data.yaml` (`input_folder`, `output_folder`) |
| Input | `{input_folder}/` |
| Output | `{output_folder}/` |
| Results (rdash jobs) | `<runs root>/<project>/results/` on the execution host, from `projects/config/rdash-launch.yaml` (cajal: `/data/runs/<project>/results/`; never under `~` or a checkout) |

### Cluster
- **System:** Harvard FASRC / BC
- **Conda env:** `<env_name>`
- **Activate:** `conda activate <env_name>`

### Tools
- **tools/em_util.md**
- **tools/pytc.md** (if training)

## DATA SPEC

### Raw Input
- **Location:** `{input_folder}/<pattern>`
- **Shape:** `(Z, Y, X)` or `(Z, Y, X, C)` uint8
- **Resolution:** X x Y x Z nm (XYZ)
- **Channels:** (if multi-channel)
  - `im[:,:,0]` = <description>

## TASKS

### 1. <Task Name>: `<script>.py` `TODO`
<What this task does.>

**Usage:**
```bash
python <script>.py <args>
```

## TRACKS

Segmentation workflow: the planned approaches per task and the end-to-end runs that combine
them (board → **Milestones**; optional, `"tracks": {}` when a project plans by questions).
An optional top-level `"tasks": ["data", ...]` fixes the board's task columns. Cards name the tracks they serve in `track:` (comma separated;
`shared` = a prerequisite of every track in its task) and the target volume in `cube:`
(omitted = every cube). Name a cube `<dataset>-<crop>` (e.g. `Brain2-B`,
`ExPID82-val`) so the board shows where it comes from. `status`: planned · active · chosen · dropped. `needs` lists the
inputs a track accepts. Replace the placeholders; delete tracks you will not try. Worked
example: any project `spec.md` with a `## TRACKS` fence.

A milestone is an approach, higher level than a track: the runs that make it up and the output it
delivers (`tasks`, optional, limits which task columns count). Each track belongs to one
milestone (`milestone` on the track), and the Milestones view shows it only there. `status`: planned · current · done ·
dropped. Questions (one problem each) live in `questions/Q-NNN[-<owner>]_<slug>.md` with `task:`,
`milestone:` and optional `rung`, `eval_data`, `metric`, `train_data`, `owner` in frontmatter; cards cite `question: Q-NNN[-<owner>]`. In multi-person repos, new cards follow `dashboard/TEMPLATE.md` (owner in ID, `owner:`, dated owner filename); legacy IDs remain unchanged. Template in
that project's `questions/README.md`. Board → **Milestones** shows the
milestone × task matrix of questions and tracks; every view shows the milestone strip.

```rdash-tracks
{
  "tracks": {
    "data": {
      "raw-clip":   {"milestone": "M1", "status": "planned", "desc": "<recipe, e.g. p1-p99 clip (+ CLAHE)>"},
      "aligned-v1": {"milestone": "M2", "status": "planned", "desc": "<recipe, e.g. liconn_aligned_u8_v1>"}
    },
    "deep-learning": {
      "pretrained": {"status": "planned", "needs": ["raw-clip", "aligned-v1"], "desc": "<checkpoint, grid nm>"},
      "finetune":   {"status": "planned", "needs": ["aligned-v1"], "desc": "<base, training data, grid nm>"}
    },
    "decoding": {
      "abiss-mean": {"status": "planned", "desc": "chunked ABISS, mean agglomeration"},
      "abiss-max":  {"status": "planned", "desc": "ABISS max agglomeration (per tile + stitch)"}
    },
    "evaluation": {
      "qc":         {"status": "planned", "desc": "<GT-free QC or proofread metric>"}
    }
  },
  "runs": [
    {"name": "<dataset>-<crop>-pretrained", "cube": "<dataset>-<crop>", "path": ["raw-clip", "pretrained", "abiss-max", "qc"]},
    {"name": "<dataset>-<crop>-finetune", "cube": "<dataset>-<crop>", "path": ["aligned-v1", "finetune", "abiss-mean", "qc"]}
  ],
  "milestones": [
    {"id": "M1", "name": "<approach>", "status": "current", "output": "<what exists when done>",
     "check": "<how it is checked>", "runs": ["<dataset>-<crop>-pretrained"]},
    {"id": "M2", "name": "<approach>", "status": "planned", "output": "<what exists when done>",
     "runs": ["<dataset>-<crop>-finetune"]}
  ]
}
```

## MILESTONES

Declared as `milestones` in the `rdash-tracks` block above.
