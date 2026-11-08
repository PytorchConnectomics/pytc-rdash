# ZettaAI Repository Index

**GitHub:** https://github.com/orgs/ZettaAI/repositories (60 public repos on 2026-11-06; 43 forks, 17 originals)

Zetta AI is the Seung-lab spin-out that ran the automated reconstructions for MICrONS and FlyWire. It now sells stitching, alignment, segmentation, synapse detection and CAVE proofreading as a service, and contributes to BRAIN CONNECTS. Its core code (**DeepEM**, **zetta_utils**) is private. The public org is mostly forks of seung-lab, funkelab and CAVE repos. The useful signal is **what Zetta changed in those forks**, much of it on branches. Survey written 2026-11-06 from `gh api` compare data plus a Software Heritage archive of DeepEM.

## Directory structure

```
zettaai/
├── deep-learning/             DeepEM (private, archived copy), Augmentor, DataProvider3, malis, other
├── segmentation-pipeline/     waterz, abiss/labiss, Synaptor, seuron, chunkflow, other
├── io-formats/                cloud-volume + cloud-files perf, crackle, provenance (cirrus-volume)
├── registration/              corgie, metroem, SEAMLeSS, rigidity
├── proofreading-visualization/ zettaai-neuroglancer (Calcada), CAVE stack + Go servers
└── infrastructure/            zetta_utils (private) + mazepa, samwise, kombu-worker, gke-gpu-monitor, other
```

Unchanged mirrors are listed in each folder's `other.md` table and do not get their own pages. Upstream libraries are documented in [seung-lab.md](seung-lab.md).

## Where the activity is (2026)

| Repo | Zetta-only work | Who |
|---|---|---|
| [zettaai-neuroglancer](zettaai/proofreading-visualization/zettaai-neuroglancer.md) | Calcada proofreading datasource, voxel editing; daily pushes | TechMagic contractors, Chris Jordan |
| [DeepEM](zettaai/deep-learning/DeepEM.md) (private) | class registry, APEX heads, synaptic-partner net, SR, EMA/focal/BF16/DDP, MALIS | Kisuk Lee, Nico Kemnitz, Ran Lu |
| [waterz](zettaai/segmentation-pipeline/waterz.md) | semantic-taint constraints, near-linear merge, dust merge | Dodam Ih, Akhilesh Halageri, Tri |
| [abiss](zettaai/segmentation-pipeline/abiss.md) | Python watershed/agglomeration, memory cuts | Tri, Dodam Ih, Akhilesh Halageri |
| [Augmentor](zettaai/deep-learning/Augmentor.md), [DataProvider3](zettaai/deep-learning/DataProvider3.md) | FIB-SEM noise, degradations, uniform isotropic flips; rejection-sampling locations | Kisuk Lee |
| [cloud-volume / cloud-files](zettaai/io-formats/cloud-volume-files.md) | Rust obstore backend, isal gzip, thread-local I/O | Nico Kemnitz |
| [crackle](zettaai/io-formats/crackle.md) | segmentation codec | William Silversmith |

## Getting DeepEM back

The repo went private between 2026-08-25 and 2026-09-06. **Software Heritage holds a full snapshot from 2026-08-25** (all 55 branches, PR heads, tags). The Wayback Machine has only 2020 HTML pages and no public fork exists. A bare-git download was requested from the SWH Vault on 2026-11-06. Commands and the branch timeline are in [zettaai/deep-learning/DeepEM.md](zettaai/deep-learning/DeepEM.md). zetta_utils has no public copy anywhere; [its page](zettaai/infrastructure/zetta_utils.md) collects what is visible from the outside.

## What can be learned

1. **Semantic-aware agglomeration fixes merges without retraining.** waterz now refuses merges across "tainted" semantic labels (by voxel ratio) and has size, segment and dust-merge constraints. DeepEM trains the matching semantic heads (glia, soma, nucleus, vessel, myelin, ECS). This is directly testable on our affinity → waterz pipelines wherever a semantic channel exists.
2. **Agglomeration speed is still being worked on.** Near-linear merge with O(1) edge lookup and a vector union-find, the scoring function precompiled (no runtime JIT), and abiss as an in-process Python library with the GIL released. Use their waterz branch before writing our own.
3. **Multi-head models need one registry.** DeepEM's `ClassSpec` makes one string the key for the output module, the ONNX output, the loss, the metric and the dataset. That is a useful pattern for PyTC multi-task configs.
4. **Two silent geometry bugs to audit in any port.**
   - emvision's `BilinearUp` never interpolated along z in "isotropic" RSUNets. Current PyTC `BilinearUp3d` is fine (checked 2026-11-06), but checkpoints or configs from emvision-based iso models are suspect.
   - Augmentor's `FlipRotateIsotropic` was not uniform over the 48 cube symmetries until 2026-10.
   - Also: ONNX export below opset 11 gives a `Resize` that does not match PyTorch.
5. **Sampling memory.** Storing all mask voxel indices per worker gets replaced by rejection sampling inside the mask's bounding box, with an exact fallback. A DataProvider3 bug also overwrote mask locations instead of taking their union. Both are worth checking in our samplers for sparse LICONN/NISB masks.
6. **Augmentations for low-SNR data.** FIB-SEM noise, contrast compression, an image-degradation pipeline, section gaps, simplex-noise warps and z-subsampling for super-resolution. All are pinned by seeded characterization tests before refactoring.
7. **Proofreading as ranked, timed review.** Calcada shows model-ranked merge candidates and scored split-error points, has a trace mode, and logs time per decision. "Seconds of human time per fixed error" is the metric Zetta optimises, and the one automated-proofreading work should report.
8. **Provenance enforced at write time.** cirrus-volume will not write without sources, a motivation and a process record. It is the same idea as our probe receipts, applied to output volumes.
9. **I/O before GPUs.** Rust object-store clients, GIL-free gzip and threading only when it pays. They point to cloud I/O as the bottleneck in petascale inference.
10. **Ops shape.** Typed, versioned CUE specs over a Python builder registry (zetta_utils), preemptible containers that sync state (samwise), GKE GPU stockout monitoring, and per-customer branches (zebrafish, fly CNS, larva, worm, V1DD).

## Related indexes

[seung-lab.md](seung-lab.md) (upstreams of most forks) · [e11bio.md](e11bio.md) · [deepem.md](deepem.md) (PyTC's view of DeepEM)
