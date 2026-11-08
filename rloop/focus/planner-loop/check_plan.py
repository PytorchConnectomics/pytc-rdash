#!/usr/bin/env python3
"""Check that the CCC science requirements are present and frozen."""
import re
import sys
from pathlib import Path


def check(path):
    text = Path(path).read_text()
    match = re.search(r'^## Review checks\s*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    if not match:
        print('Missing ## Review checks')
        return 1
    section = match.group(1)
    errors = []
    for number in range(1, 5):
        lines = re.findall(r'^S' + str(number) + r'\b.*$', section, re.M)
        if len(lines) != 1 or not lines[0].partition(':')[2].strip() or not re.search(r'evidence\s+path\s*:\s*\S', lines[0], re.I):
            errors.append('S%d missing or incomplete' % number)
    for line in section.splitlines():
        if re.search(r'<[^>]*>', line):
            errors.append(line)
    for error in errors:
        print(error)
    return bool(errors)


if __name__ == '__main__':
    sys.exit(check(sys.argv[1]))
