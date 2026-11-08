# well-plate-assay

**GitHub:** https://github.com/e11bio/well-plate-assay
**Language:** Jupyter Notebook / Python | **Stars:** 0
**Status:** dormant (last push 2022-09-27, the oldest active-development repo in the org)

Small package for processing well-plate assay data from Nikon Elements: reads the exported
measurements, maps them onto the physical plate layout, and plots per-well results.

## Layout
| Path | Purpose |
|------|---------|
| `wellplate/extract.py` | Parse Elements exports into tidy tables |
| `wellplate/elements.py` | Nikon Elements file handling |
| `wellplate/plots.py` | Per-well / per-plate plotting |
| `app/plate_map.py`, `app/plate_map_plots.py`, `app/data.json` | Plate-map app |
| `notebooks/colab_process_well_plate.ipynb` | Colab processing walkthrough |
| `notebooks/open_elements_data.ipynb` | Reading Elements data |

```bash
conda env create -f environment.yml
pip install -e .
```

## Relevance to PyTC
None directly — screening/assay tooling, not image analysis. Included for completeness of the
org survey.
