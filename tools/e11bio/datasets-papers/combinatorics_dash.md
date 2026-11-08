# combinatorics_dash

**GitHub:** https://github.com/e11bio/combinatorics_dash
**Language:** Jupyter Notebook / Python | **Stars:** 0 | **License:** GPL-3.0

"n choose k options and trends, for calculating ideal math × biological × imaging constraints."
The **design-side** counterpart to [Preprint-Barcode-Analysis](Preprint-Barcode-Analysis.md):
given how many epitope channels you can image (n) and how many bits a neuron expresses (k),
how many distinguishable barcodes do you get, and what collision rate does that imply for a
target neuron count?

## Contents
| File | Purpose |
|------|---------|
| `combinatorics.ipynb`, `combinatorics-integrated.ipynb` | Core n-choose-k barcode-space exploration |
| `encoding.ipynb` | Encoding schemes and their error-correction properties |
| `barcode_birthday.py` | Birthday-problem collision probability for a barcode pool |
| `bits_for_confidence.py` | Bits needed to reach a target identification confidence |
| `e11-bow-modeling/brainbow_model_mouseline.py`, `mouse_line.ipynb` | Brainbow-style mouse-line modeling |
| `e11-bow-modeling/test_barcoding_regimes.ipynb` | Compare barcoding regimes |

## Relevance to PyTC
Directly useful for reasoning about **how much a barcode channel can actually help
segmentation**. `barcode_birthday.py` and `bits_for_confidence.py` give the quantitative answer
to "at N neurons in this volume, how often will two adjacent processes share a barcode and
therefore be unmergeable evidence?" — the number that bounds any barcode-aware merge/split
correction the lab might build. Small, readable, no dependencies beyond numpy/scipy.
