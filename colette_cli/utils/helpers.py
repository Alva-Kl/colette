"""Utility functions for project grouping and filtering."""


def build_projects_by_machine(projects, filter_machine=None):
    """Group projects by machine, optionally filtered by machine name."""
    by_machine = {}
    for p in projects:
        m = p.get("machine", "unknown")
        if filter_machine and m != filter_machine:
            continue
        by_machine.setdefault(m, []).append(p)
    return by_machine


def filter_projects_by_name(projects, selected_names):
    """Filter projects to a provided set of project names."""
    if not selected_names:
        return list(projects)
    selected = set(selected_names)
    return [project for project in projects if project["name"] in selected]
