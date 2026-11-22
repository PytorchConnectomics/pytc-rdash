#!/usr/bin/env python3
"""Check an iteration folder before its receipt counts: effects settled, progress block filled.

  python3 rloop/focus/planner-loop/check_receipt.py <iter-dir> [--effects-only]

effects.md: every `intent En` has a later `settled En ok|error|aborted` line. An open intent
or an `unknown` settlement exits 1: look the job up by its exact job-name and comment
(`sacct --name=<job-name> --format=JobID,State,Comment`), then append the settled line, or
set the notebook to `needs-you` asking whether it ran. Never submit again before then.
receipt.md (skipped with --effects-only): the Progress block has a filled Proving check
(pass | fail | not run), Changed since last iteration, and Next (FINISH | CONTINUE | SWITCH).
Exit 0 complete, 1 open or incomplete, 2 malformed or missing input.
"""
import re
import sys
from pathlib import Path

LINE = re.compile(r'^- (intent|settled) (E\d+) (\S+) (.*)$')
OUTCOMES = ('ok', 'error', 'aborted', 'unknown')


def check_effects(path):
    """List of problems; [] when every intent is settled with a known outcome."""
    if not path.exists():
        return []          # an iteration that touched nothing external needs no file
    intents, settled, problems = {}, {}, []
    text = re.sub(r'<!--.*?-->', '', path.read_text(), flags=re.S)
    for number, line in enumerate(text.splitlines(), 1):
        if not line.startswith('- intent') and not line.startswith('- settled'):
            continue
        m = LINE.match(line)
        if not m:
            problems.append(f'{path.name}:{number}: malformed: {line}')
            continue
        kind, eid, _, rest = m.groups()
        if kind == 'intent':
            if eid in intents:
                problems.append(f'{path.name}:{number}: duplicate intent {eid}')
            intents[eid] = number
        else:
            outcome = rest.split()[0] if rest.split() else ''
            if eid not in intents:
                problems.append(f'{path.name}:{number}: settled {eid} has no earlier intent')
            elif outcome not in OUTCOMES:
                problems.append(f'{path.name}:{number}: settled {eid} outcome must be one of {"|".join(OUTCOMES)}')
            else:
                settled[eid] = (outcome, number)
    for eid, number in intents.items():
        if eid not in settled:
            problems.append(f'{path.name}:{number}: {eid} has no settled line: reconcile by exact job-name before any new submit')
        elif settled[eid][0] == 'unknown':
            problems.append(f'{path.name}:{settled[eid][1]}: {eid} settled unknown: needs a person to confirm whether it ran')
    return problems


def check_progress(path):
    if not path.exists():
        return [f'{path.name}: missing']
    text = re.sub(r'<!--.*?-->', '', path.read_text(), flags=re.S)
    block = re.search(r'^## Progress\s*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    if not block:
        return [f'{path.name}: missing ## Progress']
    body, problems = block.group(1), []
    rules = {
        'Proving check': r'^Proving check:\s*[^<\s].*→\s*(pass|fail|not run)\s*$',
        'Changed since last iteration': r'^Changed since last iteration:\s*[^<\s]',
        'Next': r'^Next:\s*(FINISH|CONTINUE|SWITCH)\b(?!\s*\|)',
    }
    for name, rule in rules.items():
        if not re.search(rule, body, re.M):
            problems.append(f'{path.name}: Progress line "{name}" missing or not filled')
    return problems


def main(argv):
    if not argv or not Path(argv[0]).is_dir():
        print(__doc__, file=sys.stderr)
        return 2
    folder = Path(argv[0])
    problems = check_effects(folder / 'effects.md')
    if '--effects-only' not in argv:
        problems += check_progress(folder / 'receipt.md')
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
