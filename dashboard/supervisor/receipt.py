"""Publish one compute-node execution receipt, including failed attempts."""
import json
import os
import socket
import signal
import subprocess
import time
from pathlib import Path

from dashboard.app.safety import publish_replace
from .store import encode
from .verify import digest


def run(manifest, summarize, preflight=None):
    record = json.loads(Path(manifest).read_text())
    started = time.time()
    inputs, outputs, summary = {}, [], {}
    exit_code = 1
    def interrupted(signum, frame):
        raise RuntimeError("Worker interrupted by signal " + str(signum))
    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        if preflight is not None:
            preflight(record)
        out = Path(record["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        for name, expected in record["inputs_digest"].items():
            actual = digest(expected["path"])
            inputs[name] = actual
            if actual != expected:
                raise ValueError("Input changed: " + name)
            source = record["assignment_record"]["inputs"][name]
            if "from" in source:
                (out / source["filename"]).symlink_to(expected["path"])
        if record["step"] == "harness_sleep":
            time.sleep(record["parameters"].get("seconds", 1))
            (out / "done.json").write_text('{"done":true}\n')
            exit_code = 0
        else:
            exit_code = subprocess.run(record["command"], env=dict(os.environ, BV_RESULT_DIR=str(out))).returncode
        for output in record["outputs_declared"]:
            if Path(output["path"]).is_file():
                outputs.append(digest(output["path"]))
        if exit_code == 0:
            summary = summarize(record)
    except Exception as exc:
        summary = {"error": str(exc)}
        exit_code = exit_code or 1
    finally:
        receipt = dict(schema=1, attempt=record["attempt"], request_id=record["request_id"], goal=record["goal"],
                       assignment=record["assignment"], step=record["step"], job_name=os.environ.get("SLURM_JOB_NAME"),
                       slurm_job_id=os.environ.get("SLURM_JOB_ID"), host=socket.gethostname(), started=started,
                       ended=time.time(), exit_code=exit_code, command=record["command"], parameters=record["parameters"],
                       inputs=inputs, outputs=outputs, slurm_cpus=os.environ.get("SLURM_CPUS_ON_NODE"), summary=summary)
        publish_replace(Path(record["receipt_path"]), (encode(receipt) + "\n").encode())
        signal.signal(signal.SIGTERM, previous)
    return exit_code
