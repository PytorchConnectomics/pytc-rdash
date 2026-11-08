#!/usr/bin/env python3
"""Run a research card's prompt through the Codex CLI (latest model + live web search) and save the report.

A research card (`task: research`, id `<PROJ>-DR-NNN`) holds a self-contained `## Prompt` section: the
problem, what was tried and measured, constraints, and the deliverable. This script sends that prompt to
`codex --search exec` (read-only sandbox, ephemeral session, run in an empty scratch directory so the
model sees only the prompt) and writes the final message to `projects/<p>/research/<DR-NNN>.md`, headed
by provenance: card, model, reasoning effort, codex version, prompt sha256, start/end time, exit code.
The report is model output: treat its claims as leads to verify, not as results.

ChatGPT "deep research" is not exposed by the Codex CLI; the closest is the newest model with live web
search at high reasoning effort, which is the default here.

    python3 tools/codex_research/run.py projects/<p>/cards/<card>.md [--model gpt-6.1-sol] [--effort high]
    python3 tools/codex_research/run.py <card> --section "Follow-up prompt 1" --suffix b   # a follow-up -> DR-NNNb.md
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CODEX = Path.home() / ".local/bin/codex"


def section(text: str, name: str) -> str:
    m = re.search(rf"^## {name}[ \t]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("card", type=Path)
    ap.add_argument("--model", default="gpt-6.1-sol")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--timeout", type=int, default=5400)
    ap.add_argument("--section", default="Prompt", help="card section holding the prompt, e.g. 'Follow-up prompt 1'")
    ap.add_argument("--suffix", default="", help="report name suffix, e.g. 'b' -> research/DR-001b.md")
    a = ap.parse_args()
    text = a.card.read_text()
    cid = re.search(r"^id:\s*(\S+)", text, re.M).group(1)
    prompt = section(text, a.section)
    if not prompt:
        sys.exit(f"{a.card}: no '## {a.section}' section")
    short = cid.split("-", 1)[1] if cid.count("-") >= 2 else cid
    out = a.card.parent.parent / "research" / f"{short}{a.suffix}.md"
    out.parent.mkdir(exist_ok=True)
    version = subprocess.run([str(CODEX), "--version"], capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(prompt.encode()).hexdigest()[:12]
    t0 = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with tempfile.TemporaryDirectory() as tmp:
        last = Path(tmp) / "last.md"
        log = out.with_suffix(".log")
        with open(log, "w") as lf:
            p = subprocess.run([str(CODEX), "--search", "exec", "-m", a.model, "-c", f"model_reasoning_effort={a.effort}",
                                "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-C", tmp, "-o", str(last), "-"],
                               input=prompt, text=True, stdout=lf, stderr=subprocess.STDOUT, timeout=a.timeout)
        body = last.read_text() if last.exists() else "(no final message; see the log)"
    head = (f"# {short}{a.suffix}: Codex research report ({a.section})\n\n"
            f"> Model output, not verified. Card [{cid}](../cards/{a.card.name}); model `{a.model}`, reasoning effort `{a.effort}`, "
            f"live web search; {version}; prompt sha256 `{sha}`; {t0} to {time.strftime('%Y-%m-%dT%H:%M:%S%z')}; exit {p.returncode}. "
            f"Full log: `{log.name}` (not tracked).\n\n")
    out.write_text(head + body + "\n")
    print(out)
    return p.returncode


if __name__ == "__main__":
    sys.exit(main())
