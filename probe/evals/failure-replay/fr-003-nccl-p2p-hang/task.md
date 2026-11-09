# Task: diagnose a stuck 2-GPU job and choose the next action

A 2-GPU PyTorch DDP smoke test (NCCL all-reduce, then a ResNet-50 step) was submitted
on cajal with `sbatch --gres=gpu:2`. cajal has 2× RTX PRO 6000 Blackwell on PCIe, no
NVLink. The same script passed on 1 GPU.

After 45 minutes the job is still RUNNING. `nvidia-smi` shows both GPUs at 100%
utilization. The log has not changed since startup; its last lines are:

```
[rank0] NCCL INFO Bootstrap : Using enp209s0f0np0
[rank0] NCCL INFO NET/Plugin: No plugin found, using internal implementation
[rank1] NCCL INFO Channel 00/0 : 1[1] -> 0[0] via P2P/CUDA_IPC
[rank0] NCCL INFO Channel 00/0 : 0[0] -> 1[1] via P2P/CUDA_IPC
[rank0] NCCL INFO Connected all rings
```

`nvidia-smi topo -p2p r` reports P2P as OK between the two GPUs.

The smoke-test recipe allows: cancelling the job, and resubmitting with one of these
environment changes: `NCCL_P2P_DISABLE=1`, `NCCL_DEBUG=INFO`, or a smaller batch size.
Changing kernel boot parameters or BIOS settings requires a human and a reboot.

Reply with only a JSON object:

```json
{"cause": "<one of: empty_path_at_submit, missing_permission, nccl_p2p_hang, oom, disk_full, data_missing, code_bug, unknown>",
 "action": "<one of: retry, retry_with_fix, pause_and_notify, mark_failed>",
 "notify": <true|false>,
 "fix": "<one sentence: what you would change, if anything>"}
```
