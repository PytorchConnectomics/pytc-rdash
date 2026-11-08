# cirrus-volume, provenance-toolbox

**GitHub:** https://github.com/ZettaAI/cirrus-volume
**Language:** Python | **Status (2026-11-06):** originals; last push 2025-08 / 2023-12

- **[provenance-toolbox](https://github.com/ZettaAI/provenance-toolbox)**: standard `Process` (description, parameters, code environment) objects written into CloudVolume provenance files.
- **cirrus-volume**: a CloudVolume wrapper that **refuses writes** unless the caller supplies (1) sources, (2) a motivation, (3) a `Process`. Reads are unchanged.

## Takeaway
Enforced provenance at the write call is the same discipline as the probe receipts in this repository, applied to every output volume. Cheap to copy for shared PyTC output buckets.
