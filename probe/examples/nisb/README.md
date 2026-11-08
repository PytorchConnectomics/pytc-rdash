# Real NERL evaluator regression example

This adapter exercises **the caller's PyTC evaluator and actual `em_erl` backend**
on tiny synthetic inputs. It is a CPU regression check, not an NISB experiment,
baseline reproduction, or method-adoption change. No real NISB volume or node-LUT
cache is included. Existing [NISB scientific state](../../../projects/nisb-base-26/state.yaml)
and [local method](../../../projects/nisb-base-26/loop.md) retain their authority.

## Use

Run from the `dw-research` root with a Python environment containing NumPy,
NetworkX, and the backend's dependencies (including imageio). Supply your own
local checkout paths. Nothing is installed or downloaded by this adapter.

```bash
# Default: source/dependency inspection only; JSON to stdout, no imports of
# PyTC/em_erl/NumPy/NetworkX, no evaluator calls, no files written.
python probe/examples/nisb/nerl_adapter.py --code-repo /path/to/pytorch_connectomics

# An uninstalled backend source checkout can be supplied explicitly.
python probe/examples/nisb/nerl_adapter.py \
  --code-repo /path/to/pytorch_connectomics --backend-repo /path/to/em_erl

# Explicit CPU execution, optionally writing one new local receipt.
python probe/examples/nisb/nerl_adapter.py \
  --code-repo /path/to/pytorch_connectomics --backend-repo /path/to/em_erl \
  --run --receipt /path/to/local/new-nerl-receipt.json

# Recheck source/input identity and recorded assertions; no scoring.
python probe/examples/nisb/nerl_adapter.py \
  --code-repo /path/to/pytorch_connectomics --backend-repo /path/to/em_erl \
  --verify-receipt /path/to/local/new-nerl-receipt.json
```

`--code-repo` is required. The backend source checkout must contain
`em_erl/__init__.py` or `src/em_erl/__init__.py`; without `--backend-repo`, an
installed `em_erl` package is located without importing it. The real evaluator is
loaded directly from `connectomics/metrics/nerl.py`, avoiding unrelated PyTC
training imports. Python bytecode writes are disabled in all modes. Run mode uses
in-memory arrays and graphs, one worker, and no pickle, HDF5 cache, GPU, or network.
The optional receipt parent directory must already exist. Existing destinations,
including symlinks, are refused; `--receipt` requires `--run`.

## Checks and fixed parameters

[fixtures.json](fixtures.json) contains all inputs, expectations, and their
derivations. Two separate GT skeletons each have five nodes and four unit edges.
The segmentation is a `(3, 3, 5)` ZYX `uint32` array with zero background. Graph
positions are ZYX, resolution is `[1, 1, 1]`, there is no mask, and both `chunk_num`
and `num_workers` are 1. **`merge_threshold=1` is supplied explicitly**; PyTC's
current default of 50 is not used.

| Check | Expected NERL | What it tests |
|---|---:|---|
| Perfect | 1 | Separate, intact skeletons |
| Split | 0.65625 | One cut leaves length-2 and length-1 runs; crossing edge is lost |
| False merge | 0 | One predicted ID covers both complete skeletons |
| One-node overlap | 0.28125 | A single foreign node still triggers the strict merge penalty |
| Invalid 2D input | `ValueError` | PyTC's actual decoded-volume shape rejection |

The inspected backend counts GT/prediction pairs using
`pair_count >= merge_threshold` in `em_erl/eval.py:compute_erl_score`. Thus at 1,
one overlapping skeleton node qualifies; increasing the threshold can ignore
smaller overlaps. This is scoring leniency, not a segmentation repair. Mask merge
handling is a separate branch and is not tested here. ERL weights surviving run
lengths by GT length; [the fixture rationales](fixtures.json) show the hand-derived
expected values. Absolute comparison tolerance is `1e-10`.

## Receipt and limits

The JSON receipt distinguishes `execution.status` (`not_run`, `completed`, `error`)
from `validity.status` (`unknown`, `pass`, `fail`, `invalid`). A completed process
can have failing checks. Every receipt states `scientific_verdict=not_evaluated`
and `baseline_reproduced=false`. Missing dependencies are reported explicitly;
inspection says `not_tested` even when package paths are present, because imports
and transitive dependencies have not been tested.

SHA-256 manifests cover this adapter, the full input/expectation file, the actual
PyTC NERL module, and the backend package's Python/native files. Source hashes are
checked before and after the run; a change invalidates the result. Git revisions
are additional context, not substitutes for worktree hashes. An exported backend
without Git metadata correctly has a null Git revision. NumPy/NetworkX/imageio
versions are recorded on execution; their full installations and all system
libraries are not hashed.

Receipts include local absolute source paths for diagnosis; keep them on the
owning host unless separately cleared for sharing. Shared example files contain
only synthetic inputs and repository-relative source identities. No PyTC,
project-state, method, or planning file is modified. Imported evaluator code is
trusted local code, not a sandboxed plugin.

`--verify-receipt` compares content identities, so equivalent source locations
may move between checks. It also checks the expected values against the current
fixtures and recomputes each recorded pass/fail assertion and its aggregate.
An incomplete/error run cannot pass this consistency check. It verifies byte
identity and receipt consistency only:
the checksum is not a signature, does not authenticate the producer, and cannot
prove an execution occurred. Read `original_validity` separately; identity can
match a failed regression receipt. Re-run explicitly for new execution evidence.

Exit codes: 0 for inspection, a passing run, or a consistent receipt with matching
identity; 1 for regression/source-stability failure, identity mismatch, or
inconsistent recorded assertions; 2 for missing
dependencies, bad arguments/paths, unreadable input, or other execution errors.

For adapter behavior tests (no mock scoring), from the research root:

```bash
python -m unittest discover -s probe/tests -p test_nerl_adapter.py
```

Set `NERL_TEST_CODE_REPO` and `NERL_TEST_BACKEND_REPO` to opt in to the same five
real CPU checks and receipt revalidation within that test suite. Otherwise the
integration test is explicitly skipped; the command above does not install a
backend or reproduce a scientific baseline.
