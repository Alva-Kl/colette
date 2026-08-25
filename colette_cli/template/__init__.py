"""Template system for project lifecycle scripts and configurations."""

from .executor import (
    build_hook_command,
    build_project_bootstrap,
    compute_effective_template_hook,
    run_template_hook,
    run_onupdate_for_template,
)
from .registry import (
    SCRIPT_KEYS,
    get_creatable_template,
    get_machine_template,
    get_project_template_name,
    get_template_metadata,
    list_creatable_template_names,
    list_creatable_templates,
    list_machine_template_hook_paths,
    list_machine_template_names,
    normalize_machine_templates,
    scaffold_template_hook_files,
)

__all__ = [
    "SCRIPT_KEYS",
    "build_hook_command",
    "build_project_bootstrap",
    "compute_effective_template_hook",
    "get_creatable_template",
    "get_machine_template",
    "get_project_template_name",
    "get_template_metadata",
    "list_creatable_template_names",
    "list_creatable_templates",
    "list_machine_template_hook_paths",
    "list_machine_template_names",
    "normalize_machine_templates",
    "run_onupdate_for_template",
    "run_template_hook",
    "scaffold_template_hook_files",
]
