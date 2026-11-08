"""Read the authored ladder without inferring gate results."""
import re
from .safety import resolve_within


def _table(text, heading):
    match = re.search(r'^## ' + heading + r'\s*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    if not match:
        return []
    lines = [line.strip() for line in match.group(1).splitlines() if line.strip().startswith('|')]
    if len(lines) < 2:
        return []
    cells = lambda line: [cell.strip() for cell in line.strip('|').split('|')]
    header = [re.sub(r'[^a-z0-9]+', '_', x.lower()).strip('_') for x in cells(lines[0])]
    return [dict(zip(header, cells(line))) for line in lines[2:]]


def read(settings):
    path = resolve_within(settings.repo_root, 'LADDER.md')
    if not path.exists():
        return dict(rows=[], gates=[], errors=[], missing=True)
    with path.open('rb') as source:
        text = source.read(1048576).decode('utf-8', errors='replace')
    rows = _table(text, 'Rungs')
    errors = []
    for row in rows:
        if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', row.get('month', '')):
            errors.append('Invalid month: ' + row.get('month', ''))
        row['gates_met'] = 0
        for key in ('g1', 'g2', 'g3'):
            value = row.get(key, '')
            tag = re.match(r'^\[([^]]+)\]\s*', value)
            if tag and tag.group(1) in ('met', 'open', 'failed'):
                state, value = tag.group(1), value[tag.end():]
            else:
                state = 'none' if value in ('', '-', '—') else 'target'
                if tag:
                    errors.append('Unknown gate tag: ' + tag.group(0).strip())
            row[key] = dict(state=state, text=value)
            row['gates_met'] += state == 'met'
    return dict(rows=rows, gates=_table(text, 'Gates'), errors=errors, missing=False)
