"""Config package exports."""

from .commands import (
    cmd_config,
    cmd_config_add_machine,
    cmd_config_add_template,
    cmd_config_edit_hook,
    cmd_config_edit_machine,
    cmd_config_edit_project_hook,
    cmd_config_edit_template,
    cmd_config_list,
    cmd_config_list_templates,
    cmd_config_remove_machine,
    cmd_config_remove_template,
    cmd_config_set_default,
)

__all__ = [
    "cmd_config",
    "cmd_config_add_machine",
    "cmd_config_add_template",
    "cmd_config_edit_hook",
    "cmd_config_edit_machine",
    "cmd_config_edit_project_hook",
    "cmd_config_edit_template",
    "cmd_config_list",
    "cmd_config_list_templates",
    "cmd_config_remove_machine",
    "cmd_config_remove_template",
    "cmd_config_set_default",
]
