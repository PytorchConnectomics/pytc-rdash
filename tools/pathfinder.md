# PATHFINDER Reference

**PATHFINDER** (Precise Analysis, Tracing and High Fidelity Interpretation of
Neuronal Data for Exhaustive Reconstruction) is a multi-stage AI agglomeration
system that reconstructs complete neurons from an EM base segmentation by
reasoning about morphology at progressively larger spatial scales.

**Paper:** Januszewski, Templier, Hayworth, Peale, Hess. *Accelerating Neuron
Reconstruction with PATHFINDER.* bioRxiv 2025.05.16.654254v1 (2025-05-21), CC-BY.
Google Research / HHMI Janelia.
**DOI:** https://doi.org/10.1101/2025.05.16.654254
**PDF:** `lib/pathfinder/pathfinder_2025.05.16.654254v1.pdf`
**Code/data:** "released upon publication" — not yet available.

## Core Idea

Automated reconstruction is a two-step process (segment → agglomerate);
agglomeration is the accuracy bottleneck. Prior methods reuse the *small-FOV*
base model for pairwise scoring, which (1) misses true pairs separated by gaps,
(2) can't see micron-scale morphology, and (3) makes locally-optimal pairwise
decisions. PATHFINDER instead uses **three specialized models at increasing FOV**,
with a high-recall candidate generator feeding a large-FOV shape filter and a
higher-order combinatorial search.

## The Three Stages

| Stage | Model | FOV | Role |
|---|---|---|---|
| 1. Base segmentation | **FFN v1.5** | 0.5 µm | Large, low-merge supervoxels |
| 2. Candidate generation | **SENSE** | 2–4 µm | High-recall superset of merge pairs |
| 3. Plausibility scoring | **SHAPE** | 20 µm | Filter merge errors by shape + combinatorial search |

- **FFN v1.5** — Flood-Filling Network with 20 residual modules + layer norm,
  AdamW, grad accumulation; input 16 nm (2× downsampled, 8× cheaper). Coarse-to-
  fine over a 9-class semantic model (vessels → glia → rest). **Oversegmentation
  Consensus (OC)** cuts mergers 9.9× (cost 1.8× splits); FFN-agglo cuts splits
  2.2×. vs v1.0: **10× fewer mergers**, ~32–36% fewer splits.
- **SENSE** (SinglE Neuron Segment Expander) — residual **U-Net** taking image +
  a spherical "prompt" of a segment, predicting its continuation across the FOV
  in one forward pass. **Linear** scaling in #segments (vs quadratic pairwise
  FFN-agglo). 3 variants × 7 checkpoints → **97% recall**. Run in *high-recall*
  mode to produce an overcomplete candidate graph for downstream filtering.
- **SHAPE** (Scoring Hypothesis Assemblies using Plausibility Evaluation) —
  **PointNeXt** on point clouds sampled from segment meshes (8192 pts, 10-µm-
  radius sphere; dense voxels infeasible — fill rate ~1/r²). Classifies
  plausible vs implausible neurite shape; negatives = bad SENSE merges. Key:
  **inference-time averaging over 16 point samples × 16 rotations improves
  precision AND recall simultaneously** (−44% F1 error); accuracy scales
  logarithmically with training-set size.

### Combinatorial search (the central novelty)
SHAPE scores *arbitrary* objects, not just pairs. Starting from the
pairwise-SHAPE-filtered SENSE graph, it scores connected **subgraphs up to order
4** within a 10-µm context window on a 1-µm grid, then an iterative optimizer +
**global reconciliation** removes the minimal edge set that eliminates all
low-scoring (invalid) subgraphs while adding the fewest splits. Tractable because
(a) it starts from large FFN supervoxels and (b) SENSE prefilters the space.
Considering higher-order motifs beats pairwise filtering on the Pareto frontier.

## Dataset & Evaluation

- **IBEAM-mSEM** (Ion Beam Etching & Milling + multibeam SEM) mouse cortex,
  8×8×8 nm³; analyzed cuboid 80.4×84.8×99.2 µm³ (~0.68M µm³, ~1.32 TB).
  Alignment via **SOFIMA**.
- Reference: all 4.45 m of axons (>59k fragments) + dendrite trunks manually
  proofread. Metric = topological **nERL** (TEASAR skeletons), evaluated on
  **unmyelinated axons only** (4,284 mm) — the hardest case.

## Results (Table 1 — axon quality by stage)

| Stage | nERL | splits | mergers |
|---|---|---|---|
| FFN v1.0 (agglo) | 76.6% | 33,835 | 347 |
| FFN v1.5 (agglo) | 82.0% | 23,085 | 33 |
| **PATHFINDER** | **94.2%** | **2,862** | **702** |

- Order-of-magnitude reduction in *both* split and merge rates vs prior SOTA
  (RoboEM, Schmidt 2024); prior similar-scale work reached only ~52% global nERL.
- **84× proofreading throughput** gain (67,200 vs ~800 µm³/h) vs the optimistic
  whole-mouse-brain projection of Jefferis et al. (2023) — makes proofreading
  cost comparable to imaging cost at whole-brain scale.

## Notable details
- **Dust particles:** 8 wafer artifacts obscure full section depth → localized
  splits; reconnected via bipartite **linear-sum-assignment** (Jonker–Volgenant)
  weighted by SHAPE scores (67% recall / 93% precision).
- **Error topology:** 89% of false splits involve orphan or single-face-crossing
  (SFC) segments → prioritizing orphan/SFC review catches 95% of splits.
- **Merge detection:** SHAPE flags suspected mergers (low mean score + low
  rotational variance) for targeted human review.
- Positioned as **complementary** to auto-proofreading (NEURD, RoboEM): it
  directly maximizes automated accuracy rather than mimicking human decisions.

## Relevance to PyTC

- Current **SOTA reference point for axon nERL** and the agglomeration / error-
  correction problem we track. PATHFINDER's 94.2% axon nERL via shape-plausibility
  scoring is the mechanism that closes the gap we hit on NISB, where no GT-free
  auto error-correction beats ~0.601 NERL (cf. cc3d oracle ceiling, waterz/bridge
  affinity stitching failures).
- Transferable ideas: (1) high-recall candidate generation **decoupled** from
  scoring; (2) a large-FOV **point-cloud shape model** as a merge-error filter
  (contrast our affinity-threshold stitching, which chains); (3) **higher-order
  motif** agglomeration with global reconciliation instead of pairwise; (4)
  inference-time rotation/sample averaging as a free accuracy lever for
  point-cloud scoring.

> Note: key figures (Table 1, 94.2% nERL, 84×, 67,200 µm³/h) verified against
> rendered PDF pages — the `pdftotext` CID-font warning only affected symbols
> (e.g. `×`), not digits.
