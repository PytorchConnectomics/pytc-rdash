# waterz (ZettaAI fork)

**GitHub:** https://github.com/ZettaAI/waterz
**Language:** C++/Python | **Status (2026-11-06):** fork of funkey/waterz, 21 ahead, 8 branches; last push 2026-08-03

Watershed + hierarchical agglomeration on affinity graphs (Funke et al.). Zetta's most active 2026 algorithm repo.

## ZettaAI changes
| Date | Who | Change |
|---|---|---|
| 2025-03 | Tri (`trivoldus28`) | **semantic / size / segment constraints** on merges; fix RAG-based agglomeration segfault |
| 2026-03 | Dodam Ih | **semantic taint**: a segment carrying a "tainted" semantic label (ratio threshold, label 0 = none) may only merge with other tainted segments |
| 2026-03 | Dodam Ih | perf: stream affinities into the stats provider; raw-pointer voxel loop; single hash lookups; no redundant voxel counting; constraint providers short-circuit |
| 2026-05 | Nico Kemnitz | 64-bit `maxId` in `initialize_with_rag`; `<cstdint>` fixes |
| 2026-06 | Dodam Ih | tolerate float rounding in stale-edge rescoring; ship `discretize_queue=256` precompiled (no runtime JIT of the Cython template) |
| 2026-07-19 | Akhilesh Halageri | **near-linear merge**: O(1) `findEdge` / staleness / `removeIncEdge`, union-find in a vector |
| 2026-08-03 | Dodam Ih | `dodam/size-merge`: size-based **dust merge** (`merge_segments`, `merge_dust`) |

## Takeaways
- Semantic-aware agglomeration (block merges across glia/soma/vessel/myelin labels from the multi-head DeepEM output) is how Zetta fights merge errors without retraining the affinity net. The same idea applies to LICONN/NISB where a semantic head exists.
- Precompiling the default scoring function removes waterz's notorious first-call compile and makes it usable in short-lived cluster tasks.
