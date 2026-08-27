"""Utility functions for project grouping and filtering."""

import shlex
import sys
from pathlib import Path


def prompt(prompt_text):
    """input() that returns '' instead of blocking/crashing when stdin isn't
    a real terminal (e.g. driven by a script or agent), rather than raising
    EOFError. Every caller already treats a blank answer as "skip this
    optional value", "keep the current value", or "decline this
    confirmation", so a non-interactive caller gets that same safe default
    for anything it didn't pass as a flag, instead of a crash.
    """
    if not sys.stdin.isatty():
        return ""
    return input(prompt_text)


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


def is_remote_machine(machine):
    """Return True if the machine is a remote SSH machine."""
    return bool(machine and machine.get("type") == "ssh")


def resolve_ide_command(machine, path):
    """Resolve a machine's ide_command into an argv list, ready for subprocess.run.

    The configured (or default) command template is split into argv tokens
    *before* any substitution, so a path or host containing spaces can never
    fragment into extra arguments. '{host}' and '{path}' tokens are then
    substituted into each token. If no token contained '{path}', the resolved
    path is appended as a trailing argument (so a bare local value like "code"
    or "zed" works unchanged). The result is always run as a local subprocess
    (never over SSH) — ide_command targets a remote via its own argv syntax
    (e.g. a vscode-remote:// or ssh:// URI), not by SSHing out.
    """
    from colette_cli.utils.config import (
        DEFAULT_IDE_COMMAND_LOCAL,
        DEFAULT_IDE_COMMAND_REMOTE,
    )

    is_remote = is_remote_machine(machine)
    default = DEFAULT_IDE_COMMAND_REMOTE if is_remote else DEFAULT_IDE_COMMAND_LOCAL
    template = machine.get("ide_command") or default

    host = machine.get("host", "")
    tokens = shlex.split(template)
    resolved = [token.replace("{host}", host).replace("{path}", path) for token in tokens]
    if not any("{path}" in token for token in tokens):
        resolved.append(path)
    return resolved


def iter_machine_projects(projects, cfg, filter_machine=None, filter_names=None):
    """Yield (machine_name, machine_projects, machine, is_remote) for each machine.

    Groups *projects* by machine (optionally filtered by *filter_machine*),
    applies *filter_names* per machine, and resolves the machine config and
    remote flag from *cfg*. Skips machines with no matching projects after
    filtering.
    """
    from colette_cli.utils.config import get_machine
    by_machine = build_projects_by_machine(projects, filter_machine)
    for machine_name, machine_projects in sorted(by_machine.items()):
        machine_projects = filter_projects_by_name(machine_projects, filter_names or [])
        if not machine_projects:
            continue
        machine = get_machine(cfg, machine_name) or {}
        yield machine_name, machine_projects, machine, is_remote_machine(machine)


def write_project_record(machine, machine_name, project):
    """Persist a project record wherever it belongs: this machine's own
    projects.json if *machine* is local, or that machine's own projects.json
    over SSH if it's remote. Returns True on success.

    *project* may come from the merged load_projects() view (which tags
    cached entries with internal `_cached`/`_synced_at` keys) — those are
    always stripped before persisting.
    """
    record = {k: v for k, v in project.items() if not k.startswith("_")}
    if is_remote_machine(machine):
        from colette_cli.utils.ssh import push_project_entry
        return push_project_entry(machine, machine_name, record)
    from colette_cli.utils.config import load_local_projects, save_local_projects
    projects = [p for p in load_local_projects() if p["name"] != record["name"]]
    projects.append(record)
    save_local_projects(projects)
    return True


def delete_project_record(machine, machine_name, name):
    """Remove a project record (by name) wherever it lives: this machine's own
    projects.json, or the owning remote machine's own projects.json over SSH.
    Returns True on success.
    """
    if is_remote_machine(machine):
        from colette_cli.utils.ssh import remove_remote_project_entry
        return remove_remote_project_entry(machine, machine_name, name)
    from colette_cli.utils.config import load_local_projects, save_local_projects
    save_local_projects([p for p in load_local_projects() if p["name"] != name])
    return True


def all_template_names(cfg=None):
    """Return a set of all template names across all machines.

    For remote (ssh) machines this includes templates only known through
    the read-only sync cache — not just ones explicitly configured on this
    controller — so the project/template global namespace check stays
    correct even for a remote's own, never-locally-configured templates.
    """
    from colette_cli.template.registry import list_creatable_template_names
    from colette_cli.utils.config import load_config
    if cfg is None:
        cfg = load_config()
    names = set()
    for machine_name, machine in cfg.get("machines", {}).items():
        names.update(list_creatable_template_names(machine, machine_name))
    return names


def find_template_as_project(name, cfg=None):
    """Return a project-like dict for a directory-type template, or None.

    Searches all machines for a template named *name*. If found and the
    template is of type 'directory' with a configured path, returns:
        {"name": name, "machine": machine_name, "path": path, "template": name}
    Returns None for git-type templates (no local path) or if not found.
    """
    from colette_cli.utils.config import load_config
    if cfg is None:
        cfg = load_config()
    for machine_name, machine in cfg.get("machines", {}).items():
        for tmpl in machine.get("templates", []):
            if tmpl.get("name") != name:
                continue
            if tmpl.get("type", "directory") != "directory":
                return None
            path = tmpl.get("path", "").strip()
            if not path:
                return None
            return {
                "name": name,
                "machine": machine_name,
                "path": path,
                "template": name,
            }
    return None


def detect_project_from_cwd():
    """Return the project name whose path matches the current working directory, or None."""
    from colette_cli.utils.config import load_projects
    cwd = Path.cwd().resolve()
    for project in load_projects():
        project_path = Path(project["path"]).expanduser().resolve()
        if project_path == cwd:
            return project["name"]
    return None
