# Preprint-Barcode-Analysis

**GitHub:** https://github.com/e11bio/Preprint-Barcode-Analysis
**Language:** Jupyter Notebook / Python | **Stars:** 1

Barcode-distribution analysis for the PRISM preprint — how many distinct "protein bit" barcodes
are actually expressed per neuron, how often two neurons collide on the same barcode, and
whether the population is bimodal. Written by an intern analysis team; no top-level README
(`ADVANCED_ANALYSIS_README.md` documents the advanced pass).

## Analyses
`Plotting-scripts/`:
| Script | What it answers |
|--------|-----------------|
| `barcode-length.py` | Distribution of barcode length (bits on per neuron) |
| `collisions.py` | Barcode collision rate between neurons |
| `epitope-distribution.py` | Per-epitope expression frequency |
| `hierarchical_clustering_clean.py` | Subpopulation structure |
| `monte_carlo_modeling.py`, `monte_carlo_interpretation.py`, `plot_monte_carlo.py` | MC model of AAV infection / barcode draw |
| `spatial_filter_analysis.py` | Spatial confounds in the soma set |
| `soma_preprocessing.py`, `plot_settings.py` | Shared loading + figure style |

Advanced pass (`advanced_barcode_analysis.py`, `bimodal_barcode_analysis.py`,
`hamming_weight_analysis.py`): epitope co-occurrence, hierarchical clustering, infection-marker
correlation, channel preference, t-SNE embedding, co-expression network analysis, and
correlation of imaging-derived expression against NGS pool-sequencing counts. GMM/Poisson fits
in `bimodal_analysis_results/`.

## Data in-repo
`Data/neuron_barcodes_fixed_keys.npz`, `Data/neuron_barcodes_full_roi.npz` (per-neuron barcode
vectors), `Data/221208-pool-seq{,-clean}.csv` (NGS pool composition), `Data/LS-somas.csv` plus
`LS-somas_*.zarr` (soma coordinates, scores, is-cell and alignment-issue flags from two
independent annotators — `_AM`, `_MW`, `_KL`).

```bash
pip install numpy scipy pandas matplotlib scikit-learn seaborn networkx statsmodels
python run_advanced_analysis.py --data Data/neuron_barcodes_fixed_keys.npz \
                                --ngs Data/221208-pool-seq-clean.csv --output results/
```

## Relevance to PyTC
Reference for the *evaluation* side of barcode-based reconstruction: barcode collision rate is
the ceiling on how much a barcode can disambiguate a merge, and these scripts are the concrete
implementation of that calculation. The multi-annotator soma zarrs are also a small, real
example of storing per-object annotation agreement. Caveats: intern code, committed
`__pycache__` and `.DS_Store`, no packaging or tests — read it, don't import it.

Related: [combinatorics_dash](combinatorics_dash.md) (the design-side version of the same
math), [pool-analysis](pool-analysis.md) (where the NGS CSVs come from).
