# funlib.run (E11 fork)

**GitHub:** https://github.com/e11bio/funlib.run
**Fork of:** [funkelab/funlib.run](https://github.com/funkelab/funlib.run) (0★)
**Stars:** 0
**Divergence:** none — snapshot fork (created 2024-02-07; upstream last pushed 2021-10-27)

Thin Python wrapper for submitting jobs via **`bsub`** (LSF), optionally inside a container.
Builds the command line, handles resource flags (`-n` cpus, `-gpu`, `-q` queue, `-P` project),
and can run the job through singularity with mount handling.

**No E11 modifications**, and upstream is unmaintained since 2021.

```python
from funlib.run import run
cmd = run(
    command="python train.py",
    num_cpus=5, num_gpus=1, queue="gpu_rtx",
    singularity_image="/path/to/image.sif",
    mount_dirs=["/nrs", "/groups"],
    execute=False,     # return the command string instead of running it
)
```

## Relevance to PyTC
Low. The lab's clusters are SLURM, not LSF — [volara](../core-libs/volara.md)'s
`SlurmWorker`/`LSFWorker` in `volara/workers.py` is a newer, better-maintained version of the
same idea. Listed for completeness of the org survey.
