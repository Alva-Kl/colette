"""Configuration file management."""

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "colette"
CONFIG_FILE = CONFIG_DIR / "config.json"
PROJECTS_FILE = CONFIG_DIR / "projects.json"
TEMPLATES_FILE = CONFIG_DIR / "templates.json"
TEMPLATE_SCRIPTS_DIR = CONFIG_DIR / "templates"
PROJECT_HOOKS_DIR = CONFIG_DIR / "projects"
MACHINE_SCRIPTS_DIR = CONFIG_DIR / "machines"
HOOK_FAILURES_FILE = CONFIG_DIR / "hook-failures.json"
_MAX_HOOK_FAILURES = 200
TEMPLATE_HOOK_FILENAMES = {
    "oncreate": ".oncreate",
    "onstart": ".onstart",
    "onstop": ".onstop",
    "onlogs": ".onlogs",
    "onupdate": ".onupdate",
    "ondelete": ".ondelete",
    "coletterc": ".coletterc",
}

_HOOK_VAR_DOCS = """\
# Available Colette environment variables:
# $COLETTE_PROJECT_NAME  — name of the project
# $COLETTE_PROJECT_PATH  — absolute path to the project directory
# $COLETTE_MACHINE_NAME  — name of the configured machine
# $COLETTE_TEMPLATE_NAME — name of the template used by the project
# $COLETTE_PARAM_<KEY>   — custom template parameters (defined in template config)
# $SUPER                 — path to parent hook (set when a project hook overrides a template hook)
#                          call `source "$SUPER"` to inherit the template hook behaviour
"""


def ensure_config_dir():
    """Create config directory if it doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATE_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_HOOKS_DIR.mkdir(parents=True, exist_ok=True)


def load_config():
    """Load machine and default machine configuration."""
    if not CONFIG_FILE.exists():
        return {"machines": {}, "default_machine": None}
    return json.loads(CONFIG_FILE.read_text())


def save_config(cfg):
    """Save machine and default machine configuration."""
    ensure_config_dir()
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2) + "\n")


def load_projects():
    """Load list of all projects."""
    if not PROJECTS_FILE.exists():
        return []
    return json.loads(PROJECTS_FILE.read_text())


def save_projects(projects):
    """Save list of all projects."""
    ensure_config_dir()
    PROJECTS_FILE.write_text(json.dumps(projects, indent=2) + "\n")


def load_templates():
    """Load template registry."""
    if not TEMPLATES_FILE.exists():
        return {"templates": []}
    return json.loads(TEMPLATES_FILE.read_text())


def save_templates(templates):
    """Save template registry."""
    ensure_config_dir()
    TEMPLATES_FILE.write_text(json.dumps(templates, indent=2) + "\n")


def get_project(name):
    """Get a project by name, return None if not found."""
    return next((p for p in load_projects() if p["name"] == name), None)


def get_machine(cfg, machine_name):
    """Get a machine by name from config, return None if not found."""
    return cfg.get("machines", {}).get(machine_name)


def require_machine(cfg, machine_name):
    """Get a machine by name or exit with an error."""
    from colette_cli.utils.formatting import err

    machine = get_machine(cfg, machine_name)
    if not machine:
        err(f"machine '{machine_name}' not found.")
    return machine


def get_template_dir(template_name):
    """Return the local configuration directory for a template's hook files."""
    return TEMPLATE_SCRIPTS_DIR / template_name


def ensure_template_dir(template_name):
    """Ensure a template hook directory exists and return it."""
    ensure_config_dir()
    template_dir = get_template_dir(template_name)
    template_dir.mkdir(parents=True, exist_ok=True)
    return template_dir


def get_template_hook_path(template_name, hook_name):
    """Return the path of a template hook file."""
    filename = TEMPLATE_HOOK_FILENAMES[hook_name]
    return get_template_dir(template_name) / filename


def template_hook_exists(template_name, hook_name):
    """Return whether a template hook file exists."""
    return get_template_hook_path(template_name, hook_name).exists()


def read_template_hook(template_name, hook_name):
    """Read a template hook file if present."""
    hook_path = get_template_hook_path(template_name, hook_name)
    if not hook_path.exists():
        return None
    return hook_path.read_text()


def write_template_hook(template_name, hook_name, content):
    """Write a template hook file and make it executable when appropriate."""
    template_dir = ensure_template_dir(template_name)
    hook_path = template_dir / TEMPLATE_HOOK_FILENAMES[hook_name]
    hook_path.write_text(content)
    mode = 0o755 if hook_name != "coletterc" else 0o644
    os.chmod(hook_path, mode)
    return hook_path


def remove_template_dir(template_name):
    """Remove a template hook directory if it exists."""
    template_dir = get_template_dir(template_name)
    if not template_dir.exists():
        return
    for child in template_dir.iterdir():
        if child.is_file() or child.is_symlink():
            child.unlink()
    template_dir.rmdir()


def get_project_hook_dir(project_name):
    """Return the local configuration directory for a project's hook files."""
    return PROJECT_HOOKS_DIR / project_name


def ensure_project_hook_dir(project_name):
    """Ensure a project hook directory exists and return it."""
    ensure_config_dir()
    d = get_project_hook_dir(project_name)
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_project_hook_path(project_name, hook_name):
    """Return the path of a project-specific hook file."""
    return get_project_hook_dir(project_name) / TEMPLATE_HOOK_FILENAMES[hook_name]


def project_hook_exists(project_name, hook_name):
    """Return whether a project-specific hook file exists."""
    return get_project_hook_path(project_name, hook_name).exists()


def read_project_hook(project_name, hook_name):
    """Read a project-specific hook file if present."""
    hook_path = get_project_hook_path(project_name, hook_name)
    if not hook_path.exists():
        return None
    return hook_path.read_text()


def write_project_hook(project_name, hook_name, content):
    """Write a project-specific hook file and make it executable when appropriate."""
    d = ensure_project_hook_dir(project_name)
    hook_path = d / TEMPLATE_HOOK_FILENAMES[hook_name]
    hook_path.write_text(content)
    mode = 0o755 if hook_name != "coletterc" else 0o644
    os.chmod(hook_path, mode)
    return hook_path


def scaffold_project_hook_files(project_name):
    """Ensure a project has concrete hook files in the config directory."""
    ensure_project_hook_dir(project_name)
    for hook_name in TEMPLATE_HOOK_FILENAMES:
        if not project_hook_exists(project_name, hook_name):
            if hook_name == "coletterc":
                content = (
                    _HOOK_VAR_DOCS
                    + 'source "$SUPER"\n\n'
                    + f"# Colette sources this file when it creates a tmux session for\n"
                    f"# project '{project_name}'.\n"
                )
            else:
                content = (
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n\n"
                    + _HOOK_VAR_DOCS
                    + 'source "$SUPER"\n\n'
                    + f"# Colette runs this hook for project '{project_name}' during {hook_name}.\n"
                )
            write_project_hook(project_name, hook_name, content)


def load_hook_failures():
    """Load the hook failure log; returns an empty list if not present or malformed."""
    if not HOOK_FAILURES_FILE.exists():
        return []
    try:
        return json.loads(HOOK_FAILURES_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def append_hook_failure(entry):
    """Append a hook failure entry to the log, keeping at most _MAX_HOOK_FAILURES entries."""
    ensure_config_dir()
    failures = load_hook_failures()
    failures.append(entry)
    if len(failures) > _MAX_HOOK_FAILURES:
        failures = failures[-_MAX_HOOK_FAILURES:]
    HOOK_FAILURES_FILE.write_text(json.dumps(failures, indent=2) + "\n")


def clear_hook_failures():
    """Clear the hook failure log."""
    ensure_config_dir()
    HOOK_FAILURES_FILE.write_text("[]\n")


# ---------------------------------------------------------------------------
# Machine-specific template hook helpers
# ---------------------------------------------------------------------------

def get_machine_template_dir(machine_name, template_name):
    """Return the hook directory for a template override on a specific machine."""
    return MACHINE_SCRIPTS_DIR / machine_name / "templates" / template_name


def ensure_machine_template_dir(machine_name, template_name):
    """Ensure a machine-specific template hook directory exists and return it."""
    d = get_machine_template_dir(machine_name, template_name)
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_machine_template_hook_path(machine_name, template_name, hook_name):
    """Return the path of a machine-specific template hook file."""
    filename = TEMPLATE_HOOK_FILENAMES[hook_name]
    return get_machine_template_dir(machine_name, template_name) / filename


def machine_template_hook_exists(machine_name, template_name, hook_name):
    """Return whether a machine-specific template hook file exists."""
    return get_machine_template_hook_path(machine_name, template_name, hook_name).exists()


def read_machine_template_hook(machine_name, template_name, hook_name):
    """Read a machine-specific template hook file if present."""
    hook_path = get_machine_template_hook_path(machine_name, template_name, hook_name)
    if not hook_path.exists():
        return None
    return hook_path.read_text()


def write_machine_template_hook(machine_name, template_name, hook_name, content):
    """Write a machine-specific template hook file and make it executable."""
    d = ensure_machine_template_dir(machine_name, template_name)
    hook_path = d / TEMPLATE_HOOK_FILENAMES[hook_name]
    hook_path.write_text(content)
    mode = 0o755 if hook_name != "coletterc" else 0o644
    os.chmod(hook_path, mode)
    return hook_path


def get_machine_template_params(machine, template_name):
    """Return machine-specific params for a template, or an empty dict."""
    for tmpl in machine.get("templates") or []:
        if tmpl.get("name") == template_name:
            return dict(tmpl.get("params") or {})
    return {}


def upsert_machine_template_entry(cfg, machine_name, template_name, description=None, params=None):
    """Write description/params into a machine's template entry in config.json."""
    machine = cfg.get("machines", {}).get(machine_name)
    if not machine:
        return cfg
    templates = machine.setdefault("templates", [])
    for t in templates:
        if t.get("name") == template_name:
            if description is not None:
                if description:
                    t["description"] = description
                else:
                    t.pop("description", None)
            if params is not None:
                if params:
                    t["params"] = params
                else:
                    t.pop("params", None)
            return cfg
    entry = {"name": template_name}
    if description:
        entry["description"] = description
    if params:
        entry["params"] = params
    templates.append(entry)
    return cfg


def rename_machine_template_dir(machine_name, old_name, new_name):
    """Rename the machine-specific template hook directory."""
    old_dir = get_machine_template_dir(machine_name, old_name)
    new_dir = get_machine_template_dir(machine_name, new_name)
    if old_dir.exists() and not new_dir.exists():
        old_dir.rename(new_dir)
