# VAST Lite export parsing notes for Claude Code

This single file combines the prior spec pack for parsing files exported from **VAST Lite 1.5.0**.

These notes are grounded in the VAST Lite 1.5.0 manual:
- Segmentation metadata can be exported as plain text or CSV.
- Annotation-layer metadata can be exported as CSV.
- Skeleton data can be exported as CSV, and skeletons can also be imported from CSV and SWC.
- Tool-layer agglomeration information is stored in skeleton node `EXT` values and can also be copied out via clipboard export.

## Scope

This document is designed to help an LLM:

1. identify the likely VAST export type,
2. parse it conservatively,
3. preserve hierarchy and identifiers,
4. avoid inventing semantics when the file lacks headers or field descriptions,
5. convert the content into normalized JSON or pandas-like tables.

## Recommended workflow for Claude Code

1. Read the top-level parsing instructions below first.
2. Detect file type using extension, delimiter, and header text.
3. Apply the most specific section below.
4. If a CSV has headers, trust the header names over heuristics.
5. If a CSV has no headers, infer columns conservatively and mark uncertain mappings.
6. Never mutate source files; write normalized outputs separately.

## Normalized output target

For downstream code, prefer converting every source into one of these forms:

- `segments.jsonl` or `segments.parquet`
- `annotation_objects.jsonl` or `annotation_objects.parquet`
- `skeleton_nodes.parquet`
- `skeleton_edges.parquet`
- `parse_report.json`

Where uncertainty exists, include:

- `source_file`
- `parser_name`
- `header_present`
- `field_mapping_confidence`
- `warnings`

## Source basis

These specs were derived from the VAST Lite 1.5.0 manual, especially the sections on segmentation metadata export/load, annotation-layer data export/import, skeleton export/import, and tool-layer EXT usage.

---

# CLAUDE.md — parse VAST Lite exports safely

You are reading files exported from **VAST Lite 1.5.0**.

Your job is to parse them into normalized machine-readable structures **without guessing beyond the evidence in the file**.

## Primary rules

1. Preserve every raw column.
2. Add normalized columns only when mapping confidence is high.
3. If the file includes a header row, use it as the source of truth.
4. If the file does not include a header row, infer cautiously and emit a warning.
5. Keep hierarchy fields exactly as integers/strings from source.
6. Never renumber object IDs, segment IDs, node IDs, or parent/child links.
7. Distinguish clearly between:
   - segmentation objects,
   - annotation objects,
   - skeleton nodes,
   - skeleton edges,
   - SWC points,
   - auxiliary EXT/agglomeration data.
8. If a field is ambiguous, keep both `raw_<name>` and `guessed_<name>`.
9. Produce a parse report summarizing assumptions, warnings, and row counts.

## Detection order

### 1) Segmentation metadata export

Likely when:
- file is `.txt` or `.csv`
- first lines mention segment metadata columns
- rows contain segment ID, flags, colors, anchor XYZ, hierarchy IDs, bbox, and segment name

Use the section: **VAST segmentation metadata export**

### 2) Annotation layer metadata export

Likely when:
- file is `.csv`
- rows represent annotation objects rather than nodes
- fields appear to include object hierarchy, names, colors, flags, user IDs, and possibly total lengths

Use the section: **VAST annotation-layer metadata export**

### 3) Skeleton data export

Likely when:
- file is `.csv`
- rows represent nodes and/or edges
- columns mention node coordinates, parent/child relationships, labels, diameters, edge type, edge weight, or object IDs

Use the section: **VAST skeleton data export and import**

### 4) SWC skeleton import/export

Likely when:
- file is `.swc`
- rows match classic SWC: `id type x y z radius parent`

Use the section: **VAST skeleton data export and import**

### 5) EXT / agglomeration auxiliary exports

Likely when:
- plain text copied from clipboard
- one integer per line or delimited lists of IDs
- content corresponds to Chunked Region Collector source IDs stored in skeleton-node EXT values

Use the section: **VAST tool-layer EXT values and auxiliary exports**

## Output contract

For each parsed file, emit:

```json
{
  "source_file": "...",
  "detected_format": "...",
  "header_present": true,
  "tables": {
    "main": "...",
    "nodes": "...",
    "edges": "..."
  },
  "warnings": [],
  "mapping_confidence": "high|medium|low"
}
```

## Parsing style

- Prefer UTF-8.
- Handle Windows newlines.
- Detect delimiter from comma, tab, semicolon.
- Treat quoted strings carefully.
- Preserve empty fields as null.
- Preserve large integers as 64-bit safe values when possible.
- Do not coerce flags fields into booleans only; keep the raw integer too.

## Validation checks

- IDs should be unique where the format implies uniqueness.
- Parent/child/prev/next references should either be 0/null or point to known IDs.
- Bounding boxes should have min <= max when both are present.
- For SWC, parent should be -1 or a valid prior node.
- For skeleton CSV, do not assume one row equals one node unless the file structure proves it.

## Failure mode

If the format is not fully identifiable:

1. classify it as `unknown_vast_export`,
2. preserve raw rows,
3. provide the most likely interpretation,
4. list exactly which assumptions need confirmation.

---

# VAST segmentation metadata export

## What VAST says

VAST can export segment metadata to a text file or CSV. The manual explicitly documents the column layout for the text export, and says the same metadata can alternatively be saved as CSV.

## Canonical columns documented by the manual

The segmentation metadata file contains these fields:

1. `segment_id`
2. `flags`
3. `primary_r`
4. `primary_g`
5. `primary_b`
6. `primary_pattern`
7. `secondary_r`
8. `secondary_g`
9. `secondary_b`
10. `secondary_pattern`
11. `anchor_x`
12. `anchor_y`
13. `anchor_z`
14. `parent_id`
15. `child_id`
16. `prev_id`
17. `next_id`
18. `collapsed_folder_id`
19. `bbox_min_x`
20. `bbox_max_x`
21. `bbox_min_y`
22. `bbox_max_y`
23. `bbox_min_z`
24. `bbox_max_z`
25. `segment_name`

## Flags interpretation

The manual documents these flag bits:

- bit `0`: `is_used`
- bit `8`: `is_expanded`
- bits `16-17`: selection state
  - `1`: selected
  - `2`: in child group of selected
- bits `24-27`: segment tag (`0..15`)

Keep the raw integer flags field and also derive helper columns:

- `flag_is_used`
- `flag_is_expanded`
- `flag_selection_state`
- `flag_tag`

## Hierarchy semantics

Treat these IDs as linked-list / tree references:

- `parent_id`
- `child_id`
- `prev_id`
- `next_id`
- `collapsed_folder_id`

`0` means no linked object.

## Important caveats

- Bounding boxes may be incorrect if voxels were deleted.
- Loading edited metadata back into VAST may fail if segment counts differ.
- Manually corrupted files may cause VAST-side problems even if some parser checks exist.

## Parsing guidance

### Text export

If the file begins with a prose header describing the columns:
- preserve the header text,
- skip commentary lines for the tabular parse,
- then parse the remaining records.

### CSV export

If a header row exists, use it.
If no header row exists, map by the 25-column order above.

### Name field

The manual says the segment name is stored as text in quotes in the text layout.
So:
- support quoted strings,
- allow commas inside quoted names,
- trim outer quotes but preserve raw text separately.

## Recommended normalized schema

```text
segment_id: int
flags_raw: int
flag_is_used: bool|null
flag_is_expanded: bool|null
flag_selection_state: int|null
flag_tag: int|null
primary_r/g/b/pattern: int|null
secondary_r/g/b/pattern: int|null
anchor_x/y/z: int|null
parent_id/child_id/prev_id/next_id: int|null
collapsed_folder_id: int|null
bbox_min_x/max_x/min_y/max_y/min_z/max_z: int|null
segment_name: string|null
raw_row: string|object
```

## Minimal validations

- `segment_id` should be unique.
- Hierarchy links should resolve to known segment IDs or 0/null.
- Bounding boxes should satisfy min <= max when present.
- `flag_tag` should be in `0..15`.

---

# VAST annotation-layer metadata export

## What VAST says

VAST can export annotation-layer metadata to a `.CSV` text file. The exported content is metadata for annotation objects in the current layer. The manual states that import can selectively restore:

- object hierarchy
- names
- colors
- user flags
- user IDs

The manual also notes that this export includes **total lengths for skeletons**.

## Important limitation

The manual excerpt available here does **not** enumerate the exact CSV column order for annotation-layer metadata.
Therefore this spec is intentionally **header-driven**.

## What an annotation object can be

At minimum, the exported rows likely correspond to annotation objects such as:

- folders
- skeleton objects

Do not assume every row is a skeleton.

## Strong parsing strategy

### If header row is present

Use the header row as the schema source of truth.
Typical high-confidence groups to detect:

- identity: `id`, `object_id`
- hierarchy: `parent`, `child`, `prev`, `next`, folder relationships
- naming: `name`
- color: RGB or packed color columns
- flags: one or more flag columns or packed flag values
- user IDs: one unsigned integer-like column
- type: folder vs skeleton
- total length: likely numeric, only meaningful for skeleton objects

### If header row is absent

Do not invent fixed column names.
Instead:
- load all columns as `col_1`, `col_2`, ...
- inspect value patterns,
- produce only tentative mappings,
- mark `mapping_confidence = low` unless corroborated externally.

## Recommended normalized representation

### Table: `annotation_objects`

Suggested normalized fields:

```text
object_id: int|string
object_type: string|null
name: string|null
parent_id: int|string|null
child_id: int|string|null
prev_id: int|string|null
next_id: int|string|null
color_r/g/b: int|null
color_border_r/g/b: int|null
user_id: int|string|null
total_length: float|null
flags_raw: string|int|null
raw_columns: object
```

### Flags

The manual states that each annotation layer supports up to 64 named flags per object.
If flags are exported as separate columns:
- preserve each flag column,
- do not collapse them prematurely.

If flags are exported as a packed integer or bitstring:
- preserve raw form,
- only decode when the file/header makes that representation explicit.

## Validation

- Object IDs should be unique if present.
- If hierarchy fields exist, referenced IDs should resolve or be null/0.
- `total_length` should be numeric where present.
- `user_id` may exceed signed 32-bit range; preserve as 64-bit-safe integer or string.

## Guidance for Claude Code

When asked to parse annotation-layer metadata:

1. prefer files with headers,
2. infer object type from explicit columns only,
3. keep a `raw_columns` map,
4. output a warning when object type or hierarchy mapping is uncertain.

---

# VAST skeleton data export and import

## What VAST says

VAST can:

- export skeleton data from an annotation layer to `.CSV`,
- import skeleton data from `.CSV` and `.SWC`,
- export skeleton models through `vasttools.m` to OBJ/MTL, PLY, and SWC.

The manual describes the CSV export as containing **node and edge information of all skeletons**.
CSV imported back into VAST must match the same format as exported from VAST.
SWC imports are expected to be:

- in micrometer scale,
- with positive Z axis,
- matching the `vasttools.m` export convention,
- without X/Y swap,
- without Z inversion.

## Important limitation

The manual excerpt available here does **not** provide the exact exported CSV column list for skeleton CSV.
Therefore the CSV parser should be **header-first and structure-aware**.

## Skeleton model assumptions from the manual

VAST skeletons are binary trees:

- one root node per skeleton,
- each node has at most one parent,
- each node has up to two children,
- nodes can have labels,
- nodes have diameters,
- edges can have types and weights,
- tool-layer workflows may store source IDs in node `EXT` values.

## CSV parsing strategy

### Case A: separate node and edge tables in one file

Possible signs:
- section markers,
- blank-line-separated tables,
- columns that clearly refer to nodes vs edges.

If present, split into:
- `skeleton_nodes`
- `skeleton_edges`

### Case B: one flat table with one row per node

Possible columns:
- skeleton/object ID
- node ID / DFS number
- x, y, z
- parent node ID
- child1 node ID
- child2 node ID
- label
- diameter
- color / node color
- ext
- exclude flag

### Case C: mixed node-edge rows

If row type is explicit, preserve row-type and then normalize into separate node and edge tables.

## SWC parsing

Classic SWC layout:

1. node id
2. type
3. x
4. y
5. z
6. radius
7. parent id

Recommended normalized fields:

```text
node_id: int
swc_type: int
x_um: float
y_um: float
z_um: float
radius_um: float
parent_node_id: int
```

Keep coordinate-unit metadata as:

- `coordinate_unit = "micrometer"`
- `z_axis_direction = "positive"`

## Recommended normalized schema for VAST CSV

### `skeleton_nodes`

```text
skeleton_id: int|string|null
node_id: int|string|null
node_dfsnr: int|string|null
x: float|int|null
y: float|int|null
z: float|int|null
label: string|null
diameter: float|null
ext: int|string|null
exclude_from_agglomeration: bool|null
raw_columns: object
```

### `skeleton_edges`

```text
skeleton_id: int|string|null
edge_id: int|string|null
parent_node_id: int|string|null
child_node_id: int|string|null
edge_type: string|int|null
edge_weight: float|null
raw_columns: object
```

## High-value heuristics

- If a column looks like `EXT`, preserve it exactly.
- If columns suggest parent/child binary-tree structure, do not rewrite into arbitrary graph format until after raw preservation.
- If labels exist, keep them as UTF-8 strings.
- If coordinates are integers in CSV, do not force float unless needed.

## Validation

- Each skeleton should have at most one root when parent links are available.
- Parent links should not form cycles.
- Edge endpoints should resolve to known nodes.
- SWC parent IDs should reference earlier rows or `-1`.

---

# VAST tool-layer EXT values and auxiliary exports

## Chunked Region Collector

The VAST manual states that the **Chunked Region Collector** uses skeletons from an annotation layer to collect supervoxels from a source segmentation and generate merged voxelized objects.

The key detail for parsing is:

- sampled source segment IDs are stored in skeleton-node **EXT** values,
- this agglomeration information is saved with the annotation layer file,
- VAST can copy selected EXT lists to the clipboard.

## What to expect in exported/copied auxiliary data

Possible formats include:

- one integer ID per line,
- comma-separated integer IDs,
- whitespace-separated integer IDs,
- grouped outputs for one skeleton or all skeletons in a folder.

The manual does not specify a formal standalone file format for this clipboard export in the excerpt available here.
So parsing should be intentionally lightweight and lossless.

## Parsing guidance

### EXT list export

Normalize into:

```text
record_id: int
source_segment_id: int|string
source_text: string
```

If grouping markers are present, also preserve:

- `group_name`
- `skeleton_id`
- `object_name`

### Annotation-layer coupling

If an annotation-layer or skeleton-data CSV already contains an `EXT` column:
- do not split it out into a separate file unless requested,
- instead expose both raw and parsed integer values.

## Other related VAST outputs worth handling nearby

### Volume measurements

The manual says VAST can export volume measurements as plain text or CSV.
Treat these as separate measurement exports rather than segmentation metadata.
Likely fields include segment IDs and measurement values by mip/region.
Do not confuse them with the segment metadata table.

### Segment metadata vs. agglomeration IDs

Keep these separate:
- segmentation metadata describes VAST segment objects,
- EXT/agglomeration IDs usually refer to source IDs from an oversplit source segmentation.

They are not guaranteed to share the same ID namespace.

## Validation

- Accept duplicate source IDs unless deduplication is explicitly requested.
- Preserve order, because order may reflect node traversal or clipboard export behavior.
- If values are not parseable as integers, preserve raw tokens and warn.
