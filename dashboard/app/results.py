"""JSON measurements only. Declarations never become commands or verdicts."""
import json
import math
import os
import re
from . import inspection, jobs
from .config import roots_for


def number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def declarations(body):
    match = jobs.FENCE.search(body or '')
    if not match:
        return []
    try:
        fence = json.loads(match.group(1))
        rows = fence.get('results', []) if isinstance(fence, dict) else []
        return rows[:64] if isinstance(rows, list) else []
    except (ValueError, RecursionError):
        return []


def validate(row):
    if not isinstance(row, dict):
        return 'invalid_declaration'
    for field in ('name', 'path', 'key'):
        if not isinstance(row.get(field), str) or not 1 <= len(row[field]) <= 512 or '\x00' in row[field]:
            return 'invalid_' + field
    if not row['path'].lower().endswith('.json'):
        return 'unsupported_format'
    parts = row['key'].split('.')
    if len(parts) > 8:
        return 'key_too_deep'
    if '' in parts:
        return 'empty_key_segment'
    if any(not re.fullmatch(r'[A-Za-z0-9_-]+', part) for part in parts):
        return 'invalid_key_segment'
    if 'source' in row and (not isinstance(row['source'], str) or len(row['source']) > 2000):
        return 'invalid_source'
    if 'baseline' in row and not number(row['baseline']):
        return 'invalid_baseline'
    if row.get('direction') not in (None, 'higher', 'lower'):
        return 'invalid_direction'
    return None


def measurement(row, observed):
    result = {k: row[k] for k in ('name', 'path', 'key', 'baseline', 'direction', 'source') if k in row}
    result.update({k: v for k, v in observed.items() if k != 'data'})
    if observed['state'] != 'present':
        return result
    def unreadable(reason):
        return dict(result, state='unreadable', reason=reason)
    try:
        value = json.loads(observed['data'])
    except (ValueError, UnicodeError, RecursionError):
        return unreadable('invalid_json')
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 32:
            return unreadable('nesting_too_deep')
        if isinstance(item, (dict, list)):
            pending.extend((v, depth + 1) for v in (item.values() if isinstance(item, dict) else item))
    for part in row['key'].split('.'):
        try:
            value = value[int(part)] if isinstance(value, list) and part.isdigit() else value[part]
        except (KeyError, IndexError, TypeError, ValueError):
            return unreadable('missing_key')
    if isinstance(value, bool):
        return unreadable('boolean_metric')
    if type(value) not in (int, float):
        return unreadable('nonnumeric_metric')
    if not number(value):
        return unreadable('nonfinite_metric')
    result.update(value=value, as_of=observed['mtime'])
    if 'baseline' in row:
        try:
            delta = value - row['baseline']
            if not number(delta):
                return unreadable('nonfinite_delta')
            result['delta'] = delta
        except OverflowError:
            return unreadable('nonfinite_delta')
    return result


def annotate(records, settings, project):
    groups = {}
    for record in records:
        status = jobs.declared_status(record['body'])
        mode, reason = inspection.resolve_host(settings, status['host'], status['host_ok'])
        host = status['host'] if mode == 'ssh' else ''
        roots = roots_for(settings, project, host)
        record['results'] = []
        for declared in declarations(record['body']):
            error = validate(declared)
            row = ({k: declared[k] for k in ('name', 'path', 'key', 'baseline', 'direction', 'source')
                   if k in declared and (number(declared[k]) if k == 'baseline' else isinstance(declared[k], str))}
                   if isinstance(declared, dict) else {})
            row.setdefault('name', 'Invalid result')
            if error:
                if 'baseline' in row and not number(row['baseline']):
                    row.pop('baseline')
                record['results'].append(dict(row, state='unreadable', reason=error))
                continue
            if None in roots:
                record['results'].append(dict(row, state='unknown', reason='root_unavailable'))
                continue
            if mode == 'none':
                record['results'].append(dict(row, state='unknown', reason=reason))
                continue
            path = row['path']
            if not os.path.isabs(path):
                if host:
                    record['results'].append(dict(row, state='refused', reason='remote_relative_path'))
                    continue
                # Default-root aliases were resolved at configuration load. Map
                # their lexical relative prefix to that pinned resolved root.
                parts = path.split('/')
                defaults = [root for owner, root in settings.default_result_roots if owner == project]
                if parts[0] in ('results', 'logs') and len(defaults) == 2:
                    base = defaults[0 if parts[0] == 'results' else 1]
                    path = os.path.normpath(os.path.join(base, *parts[1:]))
                else:
                    path = os.path.normpath(str(settings.repo_root.resolve() / 'projects' / project / path))
            group = groups.setdefault((host, roots), [])
            target = dict(row)
            record['results'].append(target)
            group.append((path, row, target))
    for (host, roots), group in groups.items():
        observed = inspection.cached(host, 'content', [path for path, _, _ in group], roots=roots)
        for path, row, target in group:
            target.update(measurement(row, observed[path]))
    return records
