"""Template system for project lifecycle scripts and configurations."""

from .executor import build_hook_command, build_project_bootstrap, run_template_hook
from .registry import (
    SCRIPT_KEYS,
    get_machine_template,
    get_project_template_name,
    get_template_metadata,
    list_template_hook_paths,
    list_machine_template_names,
    normalize_machine_templates,
    remove_template_metadata,
    scaffold_template_hook_files,
    upsert_template_metadata,
)

__all__ = [
    "SCRIPT_KEYS",
    "build_hook_command",
    "build_project_bootstrap",
    "get_machine_template",
    "get_project_template_name",
    "get_template_metadata",
    "list_template_hook_paths",
    "list_machine_template_names",
    "normalize_machine_templates",
    "remove_template_metadata",
    "run_template_hook",
    "scaffold_template_hook_files",
    "upsert_template_metadata",
]
