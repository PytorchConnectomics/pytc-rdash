"""Registered projects and the two addressable card levels."""
import logging

from .safety import Error, card_ref, project_id, resolve_within




def discover(settings, project):
    root = resolve_within(settings.repo_root, "projects", project, "cards")
    refs, ignored = [], 0
    if not root.exists():
        return refs, ignored
    for directory, prefix in [(root, ""), (root / "inbox", "inbox/")]:
        if not directory.exists():
            continue
        resolve_within(root, prefix)
        for path in sorted(directory.iterdir()):
            if path.name.startswith(".") or path.name == "README.md":
                continue
            if prefix == "" and path.name == "inbox" and path.is_dir() and not path.is_symlink():
                continue
            try:
                ref = card_ref(prefix + path.name)
                resolve_within(root, ref)
                if not path.is_file():
                    raise ValueError()
                refs.append(ref)
            except (Error, ValueError):
                ignored += 1
    return refs, ignored


def list_projects(settings):
    root = resolve_within(settings.repo_root, "projects")
    result = []
    for path in sorted(root.iterdir()):
        if path.name == "TEMPLATE":
            continue
        try:
            project_id(path.name)
            resolve_within(root, path.name)
            if not path.is_dir():
                continue
            spec = resolve_within(path, "spec.md")
            cards = resolve_within(path, "cards")
            if not spec.is_file() and not cards.is_dir():
                continue
            refs, ignored = discover(settings, path.name)
            result.append(dict(id=path.name, label=settings.project_labels.get(path.name, path.name.replace("_", " ").replace("-", " ")),
                               card_count=len(refs), ignored_paths=ignored, has_spec=spec.is_file()))
        except Error as exc:
            logging.warning("Omitting project %s: %s", path.name, exc)
    return result


def get_project(settings, value):
    project_id(value)
    for project in list_projects(settings):
        if project["id"] == value:
            return project
    raise Error(404, "unknown_project", "Project is not registered")
