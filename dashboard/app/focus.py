"""Read notebook decisions and weekly next items."""
import re
from .projects import get_project
from .safety import resolve_within
from .questions import _frontmatter


def read(settings, project):
    get_project(settings, project)
    directory = resolve_within(settings.repo_root, 'projects', project, 'focus')
    result = []
    if not directory.is_dir():
        return dict(notebooks=result)
    for item in sorted(directory.glob('F-*.md')):
        path = resolve_within(directory, item.name)
        with path.open('rb') as source:
            text = source.read(65536).decode('utf-8', errors='replace')
        meta, body = _frontmatter(text)
        title = re.search(r'^# (.+)$', body, re.M)
        decision = re.search(r'^.*\bDecision needed:\s*(.*)$', body, re.M | re.I)
        section = re.search(r'^## Next\s*\n(.*?)(?=^## |\Z)', body, re.M | re.S)
        items = []
        if section:
            for line in section.group(1).splitlines():
                match = re.match(r'^\s*(?:[-*]|\d+\.) (?:\[([ xX])\]\s*)?(.*)', line)
                if match:
                    items.append(dict(text=match.group(2), done=bool(match.group(1) and match.group(1).lower() == 'x')))
        result.append(dict(id=path.stem, title=title.group(1) if title else '', owner=(meta or {}).get('owner', ''), decision=decision.group(1).strip() if decision else '', next=items, has_next=bool(section)))
    return dict(notebooks=result)
