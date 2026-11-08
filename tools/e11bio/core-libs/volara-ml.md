# volara-ml

**GitHub:** https://github.com/e11bio/volara-ml
**Language:** Python | **Stars:** 1
**PyPI:** `pip install volara-ml` (extras: `[torch]`, `[jax]`)

Plugin adding model inference to [volara](volara.md). Contributes one blockwise task,
`Predict`, plus a framework-agnostic `Model` abstraction so the same pipeline runs a PyTorch
checkpoint or a JAX model without changing task code.

## Key Features
- `Predict` blockwise task: standard image→image inference over an arbitrarily large volume
- `TorchModel` and `JaxModel` behind a common `Model` interface
- Shape algebra handled for you: `min_input_shape` / `min_output_shape` / `min_step_shape`
  → derives valid input/output block shapes and the context (halo) needed per block
- Multi-head outputs: `out_channels` is a list, so one forward pass can write affs + LSDs +
  embeddings to separate zarr arrays
- Automatic dtype conversion via `out_range` → uint8 quantization on write
- GPU assignment per worker (`select_device(worker_id)`)
- Internally builds a small gunpowder pipeline (`ArraySource` → `CallablePredict` → `ArrayWrite`)

## API
```python
from volara_ml.models import TorchModel
from volara_ml.blockwise import Predict
from volara.datasets import Raw, Affs

model = TorchModel(
    save_path=Path("model.pt"),          # torchscript / pickled module
    checkpoint_file=Path("checkpoint"),  # state dict, or {"model_state_dict": ...}
    in_channels=18,
    min_input_shape=Coordinate(84, 268, 268),
    min_output_shape=Coordinate(44, 228, 228),
    min_step_shape=Coordinate(2, 2, 2),
    out_channels=[3, 10],                # e.g. affs (3) + LSDs (10)
    out_range=(0.0, 1.0),
    pred_size_growth=Coordinate(0, 100, 100),   # optional: bigger blocks than the minimum
)

predict = Predict(
    checkpoint=model,
    in_data=Raw(store="data.zarr/raw"),
    out_data=[Affs(store="data.zarr/affs", neighborhood=[...]), None],  # None = discard a head
    num_workers=4,
)
predict.run_blockwise()
```

`Model` fields worth knowing:
`in_channels`, `min_input_shape`, `min_output_shape`, `min_step_shape`, `out_channels`,
`out_range`, `context_override` (force a halo instead of deriving it), `pred_size_growth`.

## Relevance to PyTC
Direct comparison point for PyTC's own sliding-window inference. The useful idea is
declaring the model's shape contract (min in/out/step) as data and letting the framework
derive block geometry — PyTC currently encodes this in inference config. Also a clean pattern
for multi-head models writing to separate output arrays in one pass.
