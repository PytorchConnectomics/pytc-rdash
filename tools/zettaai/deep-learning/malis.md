# malis (ZettaAI fork)

**GitHub:** https://github.com/ZettaAI/malis
**Language:** Python | **Status (2026-11-06):** fork of TuragaLab/malis, 4 ahead + `pytorch-conversion` branch; last push 2025-11-26

MALIS structured loss for affinity learning (Turaga et al.).

## ZettaAI changes (Kisuk Lee, 2025-11)
- Python 3.10 / PEP 517 build; PEP 8 cleanup.
- `pytorch-conversion`: **MALIS ported from TensorFlow to PyTorch** with autograd; `segmask_to_affmask` for binary-mask affinity graphs. Integrated into DeepEM branch `malis` (2025-11-25).

## Takeaway
A maintained, PyTorch-native MALIS with modern packaging; a candidate drop-in for PyTC affinity experiments that want a topology-aware loss.
