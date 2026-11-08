# ABISS — watershed + mean/max affinity agglomeration

Vendored at `lib/abiss/` in the PyTC checkout; the binary this repo calls is
`lib/abiss/build/ws`. Driven through `scripts/run_abiss_volume.py` (whole volume,
in memory) or `scripts/run_abiss_chunk.py` (chunked), wired into a config's
`decoding.steps` as `decode_abiss`.

Read this before writing a new ABISS config. Every item below cost a wasted run
or a wrong number somewhere in this repo, and none of it is discoverable from the
ABISS CLI help.

## When to prefer it over affinity-CC

Measured on MICrONS Pinky, each decoder at its own leave-one-out optimum:

| decoder | VOI | oracle-merge ceiling |
|---|---:|---:|
| affinity CC | 2.03 | 1.94 |
| **ABISS** | **1.02** | **0.90** |

CC's ceiling sits at its own base score: its errors are false merges baked into
the fragments, which no downstream agglomeration can undo. ABISS's watershed
produces near-merge-free fragments instead, so the remaining error is
split-dominated and therefore still recoverable. Dense neuropil with touching
processes is exactly the regime where this matters.

Scope: one dataset, one pair of tuned decoders. Treat it as a strong prior for
EM-like neuropil, not a universal ranking.

## Thresholds do not transfer between tutorials

**The single most expensive trap here.** If step 1 saves with
`inference.model.channel_activations: scale_sigmoid`, the stored value is
`sigmoid(0.2 * logit)`, not a probability. Measured on the IST LICONN val
artifact, that affinity spans about `[0.03, 0.81]` and **never reaches 0.88**, so
a copied threshold is not operating on the scale its author intended.

Two consequences, both load-bearing:

- Give `ws_high_threshold` / `ws_low_threshold` as **percentiles** (e.g. `"94%"`,
  `"20%"`). Percentiles are invariant to the compression and to any later change
  of activation.

  > **Corrected 2026-09-24.** This block previously said a `ws_high` above the
  > data maximum "seeds nothing — a silent empty result." That is wrong, and the
  > reason matters. In `lib/abiss/src/ws/basic_watershed.hpp:76-92` the steepest
  > neighbour is *always* followed and `>= high` only adds **extra** unconditional
  > connections, so `high` is a **force-connect** threshold, not a seed threshold.
  > Above the data maximum it simply disables forced connections and yields a
  > plain steepest-ascent watershed — the finest fragments and the best
  > attainable ceiling, which is why ABISS is traditionally run near
  > `high = 0.999`. Measured on IST LICONN val (job 3015994, 6 cubes, both
  > checkpoints): `high = 1.0`, above the data max of 0.823/0.885, gives a normal
  > segmentation **bit-identical** to `"94%"`. `ws_high` is in fact **inert**
  > across `"79%"`–`1.0` on that volume. The percentile advice above still
  > stands — it is good practice and keeps the value meaningful across
  > activations — but it is not load-bearing for `ws_high`, and whatever failure
  > originally produced the "seeds nothing" sentence is unexplained by this
  > reading. `ws_merge_threshold`, an absolute in the compressed space, remains
  > the threshold that genuinely does not transfer. See
  > `projects/msi-liconn-moe20um-2608/lessons/abiss_decode_tuning.md`.
- `ws_merge_threshold` is an **absolute value in the compressed space** and must
  be swept per volume. Mapping a plain-sigmoid optimum through the same
  compression (`p -> sigmoid(0.2*logit(p))`) gives a useful bracket, not an
  answer: on IST LICONN val the mapping suggested 0.50–0.60 and the measured
  optimum was 0.47.

Always check the actual min/max of the affinity before choosing a threshold. A
threshold above the data maximum is indistinguishable from a bad model.

## Conventions that silently shift the result

| Key | Value | Why |
|---|---|---|
| `channels` | `[2, 1, 0]` | This repo stores channel *c* as the edge along array axis *c* (z, y, x). ABISS `ws` reads an `(X, Y, Z, C)` volume whose channel 0 is the **X** edge. The triplet is reversed, not permuted arbitrarily. |
| `edge_storage` | `source` | The `banis` affinity target writes edge `(i, i+1)` at voxel *i*; `ws` reads the value at *i* as edge `(i-1, i)`. Without this the boundary map is one voxel off along **every** axis. |
| `ws_merge_function` | `max` | Monotone-invariant, so a sweep in the compressed space explores the same family of segmentations it would on uncompressed probabilities. **`mean` is not** — do not substitute it without uncompressing first. |
| `ws_size_threshold` | raise it (e.g. `10000000`) | `merge_segments` only merges regions *under* this size. The stock `400` stops agglomeration almost immediately, so the affinity criterion never gets to decide. |
| `ws_dust_threshold` | `200` | Ordinary small-object removal. |

## Two traps in the surrounding machinery

**Output filenames are built from every decoder kwarg.**
`runtime/output_naming._format_one_decode_step` slugifies each kwarg *value* into
the filename — including the whole `command` string and any absolute paths in it.
Adding `--abiss-home` and `--abiss-workdir` pushes it past 255 characters and the
job dies with `OSError: [Errno 36] File name too long` **after** the decode has
already run. On a 2.08 G-voxel volume that is 43 minutes thrown away.

Fix: set a short reserved `tag` in the step kwargs (`tag: abiss_max047`). It
replaces the auto-slug entirely and is stripped before the decoder call by
`decoding/graph.py::_resolve_decoder_kwargs`. Short tutorials escape this only
because their command strings happen to be short.

**Scratch defaults to node-local `/tmp`.** Both ABISS `ws` and the HDF5 exchange
fall back to `tempfile.gettempdir()`. On this cluster that cannot hold the ~25 GB
XYZC affinity plus 8–16 GB per segmentation. Pin both `workdir` and
`--abiss-workdir` under `/projects`.

## Sizing

Measured on IST LICONN val, `(3, 145, 4290, 3345)` float16 = 2.08 G voxels:

- decode ~43 min, **peak RSS 147 GB** — 170 GB worked, 128 GB OOM'd
- scoring ~7 min, its own ~95 GB (both volumes downcast to uint32)
- single-volume ABISS holds the whole affinity in memory (~25 GB as float32
  before `ws` internals); use `run_abiss_chunk.py` above that

## Choosing the merge threshold

**With GT.** Sweep and score. ABISS computes the watershed once and repeats only
the merge step, so N thresholds cost ~1 watershed + N scorings — sweep properly
rather than guessing.

The optimum is typically **flat with a steep cliff below it**. On IST LICONN val
slabs, 0.45–0.49 spanned 0.012 VOI (immaterial), while 0.41 was already 0.90 and
0.38 collapsed to 1.56 on merge-VOI 1.19. **Err high, never low.**

**A slab score is optimistic.** On the same volume, slab mean VOI was 0.7367 and
whole-val was 0.9129 — and 0.149 of that 0.176 gap was the *split* term. GT
truncated at slab boundaries leaves cross-slab splits unpenalised, so the slab
*number* flatters the decode. Tune on the whole volume, or treat the slab value
as an upper bracket.

> **Corrected 2026-09-24.** This paragraph previously concluded that a slab
> objective "picks a threshold that is too **high**." Measured on IST LICONN val
> (jobs 3014277, 3015923, 3015924), crops pick **low**, and the displacement
> grows as the crop shrinks:
>
> | tuning geometry | eb2 | eb8 |
> |---|---:|---:|
> | whole volume (2.08 Gvox) | 0.47 | 0.47 |
> | full-Z slabs | 0.47 | 0.44 |
> | interior cubes (14 Mvox) | 0.41 | 0.44 |
>
> No crop picked above the whole-volume optimum; three of four picked below. The
> optimistic-*score* claim above holds; the direction claim did not, and
> "err high, never low" was being followed for a reason that turned out to be
> backwards even though the advice itself is still right (the cliff below is
> real). Crops also **mis-size gaps**: a criterion comparison measured 0.040 /
> 0.011 VOI on cubes and 0.069 / 0.069 on the whole volume. Use crops to search,
> then re-measure the winner whole-volume with the threshold re-swept. See
> `projects/msi-liconn-moe20um-2608/lessons/sweep_discipline.md`.

**Without GT.** `tutorials/neuron_liconn_moe/sweep_merge_threshold.py` implements
the GT-free selection used on the ExPID96/99 volumes: match a reference
percentile of the affinity distribution, then veto thresholds where a single
segment spans the field (a runaway-agglomeration shape test) and step up the grid
until the veto clears. It reports labels, coverage, largest/second segment share
and median object volume per threshold.

Know what it cannot see: the shape test only rejects **field-spanning chains**.
It is blind to local false merges, and blind to the false *splits* that a
too-high threshold produces — which is the error it systematically biases toward.
A GT-free threshold choice is an operating point, not a validation.

**Layer naming.** The published layer name encodes the chosen threshold to three
decimals (`..._seg_abiss_mt0589`). One volume,
`ExPID96_2ndgel_S1_40XW001_18x`, predates that convention and is pinned in
`volumes.py::LEGACY` to a two-decimal `mt060`; its threshold really is 0.6000, so
the name is correct in the old form and must not be "fixed" — renaming would
orphan the layer already on GCS. The hazard is different: because that name is
*fixed*, decoding a **different model or threshold** for that volume produces a
file whose name still says `mt060` and still says nothing about the model. Scope
the output tree per model (`MOE_OUT_ROOT`) and read the true value from
`mt_sweep.json`, never from the filename.

## Where this is used

| Config | Volume |
|---|---|
| `tutorials/neuron_liconn_ist/2_abiss.yaml` | IST LICONN final_proofread val (has GT; the reference for every number above) |
| `tutorials/neuron_liconn_ist/2_abiss_eb8.yaml` | same volume, 4-GPU checkpoint |
| `tutorials/neuron_liconn_moe/2_abiss.yaml` + `sweep_merge_threshold.py` | ExPID96/99 moe volumes (no GT) |
| `tutorials/neuron_j0126/3_abiss.yaml` | j0126, via `run_abiss_chunk.py` |
| `tutorials/neuron_microns_pinky_abiss.yaml` | Pinky — source of the comparison table, and of the thresholds that must **not** be copied |

`neuron_j0126/3_abiss.yaml` carries a top-level `notes:` key. That is only legal
because `run_abiss_chunk.py` consumes it; files parsed by the strict `Config`
schema through `scripts/main.py` **raise** on unknown top-level keys.

## Sources

Measurements are from the 2026-08-26/28 IST LICONN sessions and the 2026-09-04/05
moe batch, plus the 2026-09-17 decode-tuning runs (jobs 3015841–3017281) that
produced the two corrections marked above. Full derivations, including the whole-val decode and its job IDs, are
in `projects/msi-liconn-ist-26/lessons/lesson_mip0_resolution_gate.md` §7, §9–§11.
Every number above is scoped to the volume named with it; none is a default for a
new dataset.
