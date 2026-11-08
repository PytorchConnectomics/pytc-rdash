"""Detect duplicate card IDs and mismatched owner segments."""
import re
import sys
from collections import defaultdict
from .config import Settings
from .projects import discover, list_projects
from .safety import resolve_within


def duplicate_ids(settings):
    findings = []
    for project in list_projects(settings):
        seen = defaultdict(list)
        for ref in discover(settings, project['id'])[0]:
            path = resolve_within(settings.repo_root, 'projects', project['id'], 'cards', ref)
            text = path.read_text(errors='replace')
            front = text.split('---', 2)
            if len(front) < 3 or front[0].strip():
                continue
            fields = dict(re.findall(r'^([a-z_]+):\s*(.*?)\s*$', front[1], re.M))
            identifier = fields.get('id', '').strip('"\'')
            if not identifier:
                continue
            relative = str(path.relative_to(settings.repo_root))
            seen[identifier].append(relative)
            match = re.fullmatch(r'[A-Z0-9]+(?:-[A-Z0-9]+)*-[A-Z0-9]+-([a-z][a-z0-9-]{0,31})-\d{3,}', identifier)
            if match and fields.get('owner', '').strip('"\'') != match.group(1):
                findings.append((relative, identifier, 'owner mismatch'))
        for identifier, paths in seen.items():
            if len(paths) > 1:
                findings.append((', '.join(paths), identifier, 'duplicate id'))
    return findings


if __name__ == '__main__':
    found = duplicate_ids(Settings.from_env())
    for path, identifier, reason in found:
        print(path, identifier, reason)
    sys.exit(bool(found))
