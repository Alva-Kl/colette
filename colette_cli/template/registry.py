"""Template registry."""

from colette_cli.utils.config import (
    _HOOK_VAR_DOCS,
    ensure_machine_template_dir,
    get_machine_template_hook_path,
    machine_template_hook_exists,
    write_machine_template_hook,
)


SCRIPT_KEYS = ("oncreate", "onstart", "onstop", "onlogs", "onupdate", "ondelete", "coletterc")


def _default_hook_content(template_name, hook_name):
    if hook_name == "coletterc":
        return (
            _HOOK_VAR_DOCS
            + f"# Colette sources this file when it creates a tmux session for\n"
            f"# projects using the '{template_name}' template.\n"
        )
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        + _HOOK_VAR_DOCS
        + f"# Colette runs this hook for the '{template_name}' template during {hook_name}.\n"
    )


def scaffold_template_hook_files(template_name, machine_name):
    """Ensure a template has concrete hook files in its machine-specific directory."""
    ensure_machine_template_dir(machine_name, template_name)
    for hook_name in SCRIPT_KEYS:
        if not machine_template_hook_exists(machine_name, template_name, hook_name):
            write_machine_template_hook(
                machine_name,
                template_name,
                hook_name,
                _default_hook_content(template_name, hook_name),
            )


def list_machine_template_hook_paths(machine_name, template_name):
    """Return existing hook file paths for a machine-specific template."""
    hook_paths = {}
    for hook_name in SCRIPT_KEYS:
        hook_path = get_machine_template_hook_path(machine_name, template_name, hook_name)
        if hook_path.exists():
            hook_paths[hook_name] = str(hook_path)
    return hook_paths


def normalize_machine_templates(machine):
    return machine.get("templates") or []


def get_machine_template(machine, template_name):
    for template in normalize_machine_templates(machine):
        if template["name"] == template_name:
            return template
    return None


def list_machine_template_names(machine):
    return [template["name"] for template in normalize_machine_templates(machine)]


def list_creatable_templates(machine, machine_name):
    """Return templates that can be used to create a new project on *machine*.

    This is this connection's own explicitly configured templates, plus —
    for a remote (ssh) machine — any templates the remote reported about
    itself via `colette config sync`. Cached entries carry the same
    type/path-or-url metadata the remote uses for itself, which is enough to
    provision a new project directly on the remote (path/url are resolved
    there, not on the controller), even though this controller never
    authored them.
    """
    templates = list(normalize_machine_templates(machine))
    if machine.get("type") == "ssh":
        from colette_cli.utils.config import load_machine_cache
        cache = load_machine_cache(machine_name)
        if cache:
            known = {t["name"] for t in templates}
            for t in cache.get("templates", []):
                if t.get("name") and t["name"] not in known:
                    templates.append(t)
    return templates


def list_creatable_template_names(machine, machine_name):
    return [t["name"] for t in list_creatable_templates(machine, machine_name)]


def get_creatable_template(machine, machine_name, template_name):
    return next(
        (t for t in list_creatable_templates(machine, machine_name) if t["name"] == template_name),
        None,
    )


def get_project_template_name(project):
    return project.get("template")


def get_template_metadata(machine, machine_name, template_name):
    """Get template metadata for a machine-specific template.

    Reads description and params from the machine's template entry in
    config.json. Returns machine-specific hooks_dir and scripts paths.
    """
    if not template_name:
        return None

    machine_entry = next(
        (t for t in ((machine or {}).get("templates") or []) if t.get("name") == template_name),
        {},
    )
    metadata = {"name": template_name}
    if machine_entry.get("description"):
        metadata["description"] = machine_entry["description"]
    if machine_entry.get("params"):
        metadata["params"] = machine_entry["params"]

    scaffold_template_hook_files(template_name, machine_name)
    metadata["scripts"] = list_machine_template_hook_paths(machine_name, template_name)
    from colette_cli.utils.config import get_machine_template_dir as _get_mt_dir
    metadata["hooks_dir"] = str(_get_mt_dir(machine_name, template_name))
    return metadata
