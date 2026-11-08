# Other deep-learning repos

**GitHub:** https://github.com/orgs/ZettaAI/repositories
**Status:** as of 2026-11-06

| Repo | Kind | Notes |
|---|---|---|
| [pytorch_connectomics](https://github.com/ZettaAI/pytorch_connectomics) | fork, snapshot 2023-01 | No Zetta commits; frozen copy of PyTC v0.x. Not used upstream of DeepEM. |
| [metroem](https://github.com/ZettaAI/metroem) | fork of seung-lab/metroem, 7 ahead | Alignment-model training: finetuner gradient clipping ("might prevent flipped edges"), skip initial prediction, `ReduceLROnPlateau` (2022). See [../registration/alignment.md](../registration/alignment.md). |
| [modelhouse](https://github.com/ZettaAI/modelhouse) | fork, 9 ahead | Model loading from cloud; uses CloudFiles to survive missing credentials (2023). |
| [scalenet](https://github.com/ZettaAI/scalenet) | mirror | Multiscale PyTorch module (UNet, pyramids). |
| [ncc_inference](https://github.com/ZettaAI/ncc_inference) | mirror | NCCNet inference on CloudVolume. |
| [onnx2torch](https://github.com/ZettaAI/onnx2torch) | mirror + branch `fix/conv-pad-same` | ONNX → PyTorch; Zetta ships models as ONNX. |
| [vit-pytorch](https://github.com/ZettaAI/vit-pytorch) | mirror | — |
