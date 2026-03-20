"""Template registry."""

from colette_cli.utils.config import (
    ensure_template_dir,
    get_template_dir,
    get_template_hook_path,
    template_hook_exists,
    write_template_hook,
)


SCRIPT_KEYS = ("oncreate", "onstart", "onstop", "onlogs", "coletterc")


def _default_hook_content(template_name, hook_name):
    if hook_name == "coletterc":
        return (
            f"# Colette sources this file when it creates a tmux session for\n"
            f"# projects using the '{template_name}' template.\n"
        )
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        f"# Colette runs this hook for the '{template_name}' template during {hook_name}.\n"
    )


def scaffold_template_hook_files(template_name):
    """Ensure a template has concrete hook files in the config directory."""
    ensure_template_dir(template_name)
    for hook_name in SCRIPT_KEYS:
        if not template_hook_exists(template_name, hook_name):
            write_template_hook(
                template_name,
                hook_name,
                _default_hook_content(template_name, hook_name),
            )


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


def get_template_metadata(templates_cfg, template_name):
    if not template_name:
        return None
    for template in templates_cfg.get("templates", []):
        if template.get("name") == template_name:
            metadata = dict(template)
            scaffold_template_hook_files(template_name)
            metadata["scripts"] = list_template_hook_paths(template_name)
            metadata["hooks_dir"] = str(get_template_dir(template_name))
            return metadata
    scaffold_template_hook_files(template_name)
    return {
        "name": template_name,
        "scripts": list_template_hook_paths(template_name),
        "hooks_dir": str(get_template_dir(template_name)),
    }


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
