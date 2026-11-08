# fiji-friends

**GitHub:** https://github.com/e11bio/fiji-friends
**Language:** Jupyter Notebook / Python / ImageJ macro | **Stars:** 1

Loose collection of Fiji macros and Python helpers for everyday microscopy chores — mainly
converting large imaging files into quick-reference JPGs/PNGs and building screening montages.
Explicitly a grab-bag: "open script of interest, read commentary and caveats, use whatever
functions are helpful and adjust."

## Contents
| Script | Purpose |
|--------|---------|
| `40x-MIP-maker.py` | Maximum-intensity projections from 40× acquisitions |
| `nd2-to-tif.ijm` | Nikon ND2 → TIFF conversion |
| `export_N5_tile_to_tif.py` | Pull a single N5 tile out to TIFF |
| `cell_montages.py` | Per-cell montage assembly |
| `screening_montage_nikon.py`, `screening_single-img_nikon.py` | Screening-plate montages |
| `live_preview_tiles_on_grid_annotated.py` | Preview tiles laid out on the acquisition grid |
| `stitch_settings_generator.py` | Generate stitching parameter files |
| `check_repackage_corrupted_tiles.py` | Detect and repackage corrupted tiles |
| `duplicate_montage_save_ROIs.ijm` | Duplicate a montage and save ROIs |
| `DF_metadata_extractor.py` | Extract metadata into a dataframe |
| `data_requirements_interactive_notebook.ipynb` | Storage/throughput planning |
| `Hugo/density_analysis_*.ipynb` | Cell-density analysis notebooks |

## Relevance to PyTC
Low as a dependency, occasionally useful as reference. `check_repackage_corrupted_tiles.py`
and `stitch_settings_generator.py` address real failure modes in large tiled acquisitions
(corrupt tiles, hand-tuned stitch parameters) that are easy to underestimate when planning a
pipeline. No package, no tests — copy a script, don't depend on the repo.
