"""Template registry."""

from colette_cli.utils.config import (
    _HOOK_VAR_DOCS,
    ensure_machine_template_dir,
    ensure_template_dir,
    get_machine_template_hook_path,
    get_template_dir,
    get_template_hook_path,
    machine_template_hook_exists,
    template_hook_exists,
    write_machine_template_hook,
    write_template_hook,
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


def scaffold_template_hook_files(template_name, machine_name=None):
    """Ensure a template has concrete hook files in the config directory.

    When *machine_name* is provided, scaffolds to the machine-specific
    directory. When *machine_name* is None, falls back to the legacy shared
    directory.
    """
    if machine_name:
        ensure_machine_template_dir(machine_name, template_name)
        for hook_name in SCRIPT_KEYS:
            if not machine_template_hook_exists(machine_name, template_name, hook_name):
                write_machine_template_hook(
                    machine_name,
                    template_name,
                    hook_name,
                    _default_hook_content(template_name, hook_name),
                )
    else:
        ensure_template_dir(template_name)
        for hook_name in SCRIPT_KEYS:
            if not template_hook_exists(template_name, hook_name):
                write_template_hook(
                    template_name,
                    hook_name,
                    _default_hook_content(template_name, hook_name),
                )


def scaffold_machine_template_hook_files(machine_name, template_name):
    """Ensure machine-specific hook files exist for a template on a machine."""
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


def list_template_hook_paths(template_name):
    """Return existing hook file paths for a template."""
    hook_paths = {}
    for hook_name in SCRIPT_KEYS:
        hook_path = get_template_hook_path(template_name, hook_name)
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


def get_project_template_name(project):
    return project.get("template")


def get_template_metadata(machine, machine_name, template_name):
    """Get template metadata for a machine-specific template.

    Reads description and params from the machine's template entry in
    config.json first, falling back to the legacy templates.json.
    Returns machine-specific hooks_dir and scripts paths.
    """
    if not template_name:
        return None

    machine_entry = next(
        (t for t in (machine.get("templates") or []) if t.get("name") == template_name),
        {},
    )
    metadata = {"name": template_name}
    if machine_entry.get("description"):
        metadata["description"] = machine_entry["description"]
    if machine_entry.get("params"):
        metadata["params"] = machine_entry["params"]

    if "description" not in metadata or "params" not in metadata:
        from colette_cli.utils.config import load_templates as _load_templates
        templates_cfg = _load_templates()
        legacy_entry = next(
            (t for t in templates_cfg.get("templates", []) if t.get("name") == template_name),
            {},
        )
        if "description" not in metadata and legacy_entry.get("description"):
            metadata["description"] = legacy_entry["description"]
        if "params" not in metadata and legacy_entry.get("params"):
            metadata["params"] = legacy_entry["params"]

    scaffold_template_hook_files(template_name, machine_name)
    metadata["scripts"] = list_machine_template_hook_paths(machine_name, template_name)
    from colette_cli.utils.config import get_machine_template_dir as _get_mt_dir
    metadata["hooks_dir"] = str(_get_mt_dir(machine_name, template_name))
    return metadata


def upsert_template_metadata(
    templates_cfg, template_name, description=None, params=None
):
    templates = list(templates_cfg.get("templates", []))
    for template in templates:
        if template.get("name") == template_name:
            if description is not None:
                template["description"] = description
            if params is not None:
                if params:
                    template["params"] = params
                else:
                    template.pop("params", None)
            template.pop("scripts", None)
            templates_cfg["templates"] = templates
            return templates_cfg

    entry = {"name": template_name}
    if description:
        entry["description"] = description
    if params:
        entry["params"] = params
    templates.append(entry)
    templates_cfg["templates"] = templates
    return templates_cfg


def remove_template_metadata(templates_cfg, template_name):
    templates_cfg["templates"] = [
        template
        for template in templates_cfg.get("templates", [])
        if template.get("name") != template_name
    ]
    return templates_cfg
