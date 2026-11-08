# crackle

**GitHub:** https://github.com/ZettaAI/crackle
**Language:** C++/Python | **Status (2026-11-06):** original (not a GitHub fork); last push 2026-06-10

Next-generation 3D segmentation compression codec by William Silversmith (`crackle-codec` on PyPI): crack-code boundaries + label pins, optional Markov context model; random-access queries (`labels`, `contains`, `num_labels`, per-label decode) without full decompression. Description says "ZettaAI fork: label compression experiments". 2026 work: faster CCL-based compression, faster single-label decode and bboxes, CLI conversion (nii/nrrd/tiff), point clouds. Seung-lab entry: [../../seung-lab/core-libs/](../../seung-lab/core-libs/) (transitive dep of kimimaro).
