# F-NNN iter-NN — effects

Append-only. One `intent` line **before** every external action that changes something
(`rsub`/`sbatch`, a GCS upload, a push to a shared branch), one `settled` line after it returns.
Reads (`squeue`, `sacct`, `ls`) need no line. A session that starts or resumes this iteration
reads this file first. Method: rules 8–9 in [README.md](README.md).

<!-- Format, one line each; ids E1, E2, ... in order:
- intent E1 2026-11-22T21:05-05:00 submit host=bc card=cards/<file>.md job-name=<exact> comment=<exact> replay=never
- settled E1 2026-11-22T21:06-05:00 ok slurm=3463245
Outcomes: ok | error | aborted | unknown. replay: never (submit, upload, push) | safe (re-runnable). -->
