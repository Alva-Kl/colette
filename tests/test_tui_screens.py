"""Tests for colette_cli.tui.screens — screen builders and actions."""

import pytest
from argparse import Namespace
from unittest.mock import patch, MagicMock

from tests.conftest import (
    write_config,
    write_projects,
    write_templates,
    make_local_machine,
    make_project,
)

LOCAL_CFG = {
    "machines": {"local": make_local_machine("/tmp/projects")},
    "default_machine": "local",
}


def _item_labels(items):
    return [i.label for i in items]


class _SyncThread:
    """Drop-in for threading.Thread that runs target synchronously."""
    def __init__(self, target, daemon=False):
        self._target = target
    def start(self):
        self._target()


def _call_action(item):
    """Call a leaf MenuItem's action with curses suspended (patched out)."""
    with patch("curses.endwin"), patch("curses.doupdate"):
        item.run()


# ---------------------------------------------------------------------------
# project_list_items
# ---------------------------------------------------------------------------

class TestProjectListItems:
    def test_global_actions_always_present(self, tmp_config):
        from colette_cli.tui.screens import project_list_items
        labels = _item_labels(project_list_items())
        for label in ("Create project", "Link project", "Start All", "Stop All"):
            assert label in labels

    def test_global_actions_come_after_projects(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.tui.screens import project_list_items
        save_config(LOCAL_CFG)
        save_projects([make_project("my-proj")])
        items = project_list_items()
        labels = _item_labels(items)
        proj_idx = labels.index("my-proj")
        start_idx = labels.index("Start All")
        assert proj_idx < start_idx

    def test_projects_listed_under_machine_title(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.tui.screens import project_list_items
        save_config(LOCAL_CFG)
        save_projects([make_project("my-proj")])
        labels = _item_labels(project_list_items())
        assert "my-proj" in labels

    def test_no_projects_placeholder_present(self, tmp_config):
        from colette_cli.tui.screens import project_list_items
        labels = _item_labels(project_list_items())
        assert "(no projects)" in labels

    def test_start_all_calls_cmd_start(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        # Must call project_list_items inside patch so binding picks up mock
        with patch("colette_cli.session.cmd_start") as mock_start, \
             patch("builtins.input"), \
             patch("curses.endwin"), patch("curses.doupdate"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Start All").run()
        mock_start.assert_called_once()
        assert mock_start.call_args[0][0].projects == []
        assert mock_start.call_args[0][0].machine is None

    def test_stop_all_calls_cmd_stop(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        with patch("colette_cli.session.cmd_stop") as mock_stop, \
             patch("builtins.input"), \
             patch("curses.endwin"), patch("curses.doupdate"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Stop All").run()
        mock_stop.assert_called_once()
        assert mock_stop.call_args[0][0].projects == []

    def test_create_project_calls_cmd_create(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        with patch("colette_cli.project.cmd_create") as mock_create, \
             patch("colette_cli.tui.forms.ask", side_effect=["new-proj", "local", ""]), \
             patch("colette_cli.tui.screens.threading.Thread", _SyncThread):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Create project").run()
        mock_create.assert_called_once()
        assert mock_create.call_args[0][0].name == "new-proj"

    def test_create_project_aborts_on_empty_name(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        with patch("colette_cli.project.cmd_create") as mock_create, \
             patch("colette_cli.tui.forms.ask", return_value=None):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Create project").run()
        mock_create.assert_not_called()

    def test_link_project_calls_cmd_link(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "mydir"
        project_dir.mkdir()
        with patch("colette_cli.project.cmd_link") as mock_link, \
             patch("colette_cli.tui.forms.ask", side_effect=[str(project_dir), "local", ""]):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Link project").run()
        mock_link.assert_called_once()
        assert mock_link.call_args[0][0].path == str(project_dir)

    def test_link_project_aborts_on_empty_path(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        with patch("colette_cli.project.cmd_link") as mock_link, \
             patch("colette_cli.tui.forms.ask", return_value=None):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Link project").run()
        mock_link.assert_not_called()


# ---------------------------------------------------------------------------
# project_action_items
# ---------------------------------------------------------------------------

class TestProjectActionItems:
    def _get_items(self, project=None):
        from colette_cli.tui.screens import project_action_items
        return project_action_items(project or make_project())

    def test_returns_all_expected_actions(self, tmp_config):
        write_config(tmp_config, LOCAL_CFG)
        labels = _item_labels(self._get_items())
        for expected in ("Open session", "Start", "Stop", "Code", "Logs", "Edit hooks", "Delete", "Unlink"):
            assert expected in labels, f"missing: {expected}"

    def test_action_order(self, tmp_config):
        write_config(tmp_config, LOCAL_CFG)
        labels = _item_labels(self._get_items())
        assert labels == ["Open session", "Code", "Logs", "Start", "Stop", "Edit hooks", "Unlink", "Delete"]

    def test_start_calls_cmd_start_with_project_name(self, tmp_config):
        write_config(tmp_config, LOCAL_CFG)
        project = make_project("my-proj")
        with patch("colette_cli.session.cmd_start") as mock_start, \
             patch("builtins.input"), \
             patch("curses.endwin"), patch("curses.doupdate"):
            items = self._get_items(project)
            next(i for i in items if i.label == "Start").run()
        mock_start.assert_called_once()
        args = mock_start.call_args[0][0]
        assert args.projects == ["my-proj"]
        assert args.machine is None

    def test_stop_calls_cmd_stop_with_project_name(self, tmp_config):
        write_config(tmp_config, LOCAL_CFG)
        project = make_project("my-proj")
        with patch("colette_cli.session.cmd_stop") as mock_stop, \
             patch("builtins.input"), \
             patch("curses.endwin"), patch("curses.doupdate"):
            items = self._get_items(project)
            next(i for i in items if i.label == "Stop").run()
        mock_stop.assert_called_once()
        assert mock_stop.call_args[0][0].projects == ["my-proj"]

    def test_delete_calls_cmd_delete_with_project_name(self, tmp_config):
        write_config(tmp_config, LOCAL_CFG)
        project = make_project("my-proj")
        with patch("colette_cli.project.cmd_delete") as mock_delete, \
             patch("colette_cli.tui.forms.type_to_confirm", return_value=True), \
             patch("colette_cli.tui.screens.threading.Thread", _SyncThread):
            items = self._get_items(project)
            next(i for i in items if i.label == "Delete").run()
        mock_delete.assert_called_once()
        assert mock_delete.call_args[0][0].name == "my-proj"

    def test_unlink_calls_cmd_unlink_with_project_name(self, tmp_config):
        write_config(tmp_config, LOCAL_CFG)
        project = make_project("my-proj")
        with patch("colette_cli.project.cmd_unlink") as mock_unlink, \
             patch("builtins.input"), \
             patch("curses.endwin"), patch("curses.doupdate"):
            items = self._get_items(project)
            next(i for i in items if i.label == "Unlink").run()
        mock_unlink.assert_called_once()
        assert mock_unlink.call_args[0][0].name == "my-proj"

    def test_edit_hooks_is_submenu(self, tmp_config):
        write_config(tmp_config, LOCAL_CFG)
        edit_hooks = next(i for i in self._get_items() if i.label == "Edit hooks")
        assert not edit_hooks.is_leaf

    def test_logs_is_leaf(self, tmp_config):
        write_config(tmp_config, LOCAL_CFG)
        logs = next(i for i in self._get_items() if i.label == "Logs")
        assert logs.is_leaf


# ---------------------------------------------------------------------------
# template_action_items
# ---------------------------------------------------------------------------

class TestTemplateActionItems:
    def test_returns_create_edit_hooks_edit_parameters(self, tmp_config):
        from colette_cli.tui.screens import template_action_items
        labels = _item_labels(template_action_items("my-tmpl"))
        assert labels == ["Create project", "Edit hooks", "Edit parameters"]

    def test_edit_hooks_is_submenu(self, tmp_config):
        from colette_cli.tui.screens import template_action_items
        edit_hooks = next(i for i in template_action_items("my-tmpl") if i.label == "Edit hooks")
        assert not edit_hooks.is_leaf

    def test_edit_parameters_is_submenu(self, tmp_config):
        from colette_cli.tui.screens import template_action_items
        edit_params = next(i for i in template_action_items("my-tmpl") if i.label == "Edit parameters")
        assert not edit_params.is_leaf

    def test_create_project_calls_cmd_create(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import template_action_items
        save_config(LOCAL_CFG)
        items = template_action_items("my-tmpl")
        create = next(i for i in items if i.label == "Create project")
        with patch("colette_cli.project.cmd_create") as mock_create, \
             patch("colette_cli.tui.forms.ask", return_value="new-proj"), \
             patch("colette_cli.tui.screens.threading.Thread", _SyncThread):
            create.run()
        mock_create.assert_called_once()
        args = mock_create.call_args[0][0]
        assert args.name == "new-proj"
        assert args.template == "my-tmpl"

    def test_create_project_aborts_on_empty_name(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import template_action_items
        save_config(LOCAL_CFG)
        items = template_action_items("my-tmpl")
        create = next(i for i in items if i.label == "Create project")
        with patch("colette_cli.project.cmd_create") as mock_create, \
             patch("colette_cli.tui.forms.ask", return_value=None):
            create.run()
        mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# template_param_items
# ---------------------------------------------------------------------------

class TestTemplateParamItems:
    def _setup(self, tmp_config, params=None):
        from colette_cli.utils.config import save_config, save_templates
        save_config(LOCAL_CFG)
        save_templates({"templates": [{"name": "tmpl", "params": params or {}}]})

    def test_add_parameter_item_always_present(self, tmp_config):
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config)
        items = template_param_items("tmpl")
        assert items[0].label == "Add parameter"
        assert items[0].is_leaf

    def test_no_params_shows_placeholder(self, tmp_config):
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config)
        labels = _item_labels(template_param_items("tmpl"))
        assert "(no parameters)" in labels

    def test_existing_params_appear(self, tmp_config):
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config, params={"PORT": "8080", "ENV": "dev"})
        labels = _item_labels(template_param_items("tmpl"))
        assert "PORT" in labels
        assert "ENV" in labels

    def test_param_item_shows_value_as_detail(self, tmp_config):
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config, params={"PORT": "8080"})
        port_item = next(i for i in template_param_items("tmpl") if i.label == "PORT")
        assert port_item.detail == "8080"

    def test_param_item_has_edit_and_remove_children(self, tmp_config):
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config, params={"PORT": "8080"})
        port_item = next(i for i in template_param_items("tmpl") if i.label == "PORT")
        assert not port_item.is_leaf
        child_labels = _item_labels(port_item.get_children())
        assert "Edit value" in child_labels
        assert "Remove" in child_labels

    def test_add_parameter_saves_to_metadata(self, tmp_config):
        from colette_cli.utils.config import save_config, save_templates, load_templates
        from colette_cli.tui.screens import template_param_items
        save_config(LOCAL_CFG)
        save_templates({"templates": [{"name": "tmpl"}]})
        items = template_param_items("tmpl")
        with patch("colette_cli.tui.forms.ask", side_effect=["MYKEY", "myval"]):
            items[0].run()  # Add parameter
        tmpl = next(t for t in load_templates()["templates"] if t["name"] == "tmpl")
        assert tmpl.get("params", {}).get("MYKEY") == "myval"

    def test_add_parameter_aborts_on_empty_key(self, tmp_config):
        from colette_cli.utils.config import save_config, save_templates, load_templates
        from colette_cli.tui.screens import template_param_items
        save_config(LOCAL_CFG)
        save_templates({"templates": [{"name": "tmpl"}]})
        items = template_param_items("tmpl")
        with patch("colette_cli.tui.forms.ask", return_value=None):
            items[0].run()
        tmpl = next(t for t in load_templates()["templates"] if t["name"] == "tmpl")
        assert not tmpl.get("params")

    def test_remove_parameter_deletes_from_metadata(self, tmp_config):
        from colette_cli.utils.config import load_templates
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config, params={"PORT": "8080"})
        items = template_param_items("tmpl")
        port_item = next(i for i in items if i.label == "PORT")
        remove_item = next(i for i in port_item.get_children() if i.label == "Remove")
        with patch("colette_cli.tui.forms.confirm", return_value=True):
            remove_item.run()
        tmpl = next(t for t in load_templates()["templates"] if t["name"] == "tmpl")
        assert "PORT" not in (tmpl.get("params") or {})

    def test_edit_parameter_updates_value(self, tmp_config):
        from colette_cli.utils.config import load_templates
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config, params={"PORT": "8080"})
        items = template_param_items("tmpl")
        port_item = next(i for i in items if i.label == "PORT")
        edit_item = next(i for i in port_item.get_children() if i.label == "Edit value")
        with patch("colette_cli.tui.forms.ask", return_value="9090"):
            edit_item.run()
        tmpl = next(t for t in load_templates()["templates"] if t["name"] == "tmpl")
        assert tmpl["params"]["PORT"] == "9090"


# ---------------------------------------------------------------------------
# config_menu_items / machine_list_items / machine_action_items
# ---------------------------------------------------------------------------

class TestConfigMenuItems:
    def test_has_machines_and_projects(self, tmp_config):
        from colette_cli.tui.screens import config_menu_items
        labels = _item_labels(config_menu_items())
        assert "Machines" in labels
        assert "Projects" in labels

    def test_both_are_submenus(self, tmp_config):
        from colette_cli.tui.screens import config_menu_items
        for item in config_menu_items():
            assert not item.is_leaf


class TestMachineListItems:
    def test_add_machine_is_first_item(self, tmp_config):
        from colette_cli.tui.screens import machine_list_items
        items = machine_list_items()
        assert items[0].label == "Add machine"
        assert items[0].is_leaf

    def test_configured_machines_appear(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import machine_list_items
        save_config(LOCAL_CFG)
        labels = _item_labels(machine_list_items())
        assert "local" in labels

    def test_no_machines_shows_placeholder(self, tmp_config):
        from colette_cli.tui.screens import machine_list_items
        labels = _item_labels(machine_list_items())
        assert "(no machines configured)" in labels

    def test_default_machine_shown_in_detail(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import machine_list_items
        save_config(LOCAL_CFG)
        local_item = next(i for i in machine_list_items() if i.label == "local")
        assert local_item.detail == "default"


class TestMachineActionItems:
    def test_returns_edit_set_default_templates_remove(self, tmp_config):
        from colette_cli.tui.screens import machine_action_items
        labels = _item_labels(machine_action_items("local"))
        assert "Edit" in labels
        assert "Set as default" in labels
        assert "Templates" in labels
        assert "Remove" in labels

    def test_templates_is_submenu(self, tmp_config):
        from colette_cli.tui.screens import machine_action_items
        templates = next(i for i in machine_action_items("local") if i.label == "Templates")
        assert not templates.is_leaf

    def test_edit_calls_cmd_config_edit_machine(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        # cmd_config_edit_machine imported at call time of machine_action_items
        with patch("colette_cli.config.cmd_config_edit_machine") as mock_edit, \
             patch("builtins.input", return_value=""), \
             patch("curses.endwin"), patch("curses.doupdate"):
            from colette_cli.tui.screens import machine_action_items
            items = machine_action_items("local")
            next(i for i in items if i.label == "Edit").run()
        mock_edit.assert_called_once()
        assert mock_edit.call_args[0][0].machine_name == "local"

    def test_set_default_calls_cmd_config_set_default(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        with patch("colette_cli.config.cmd_config_set_default") as mock_sd, \
             patch("builtins.input", return_value=""), \
             patch("curses.endwin"), patch("curses.doupdate"):
            from colette_cli.tui.screens import machine_action_items
            items = machine_action_items("local")
            next(i for i in items if i.label == "Set as default").run()
        mock_sd.assert_called_once()
        assert mock_sd.call_args[0][0].machine_name == "local"


# ---------------------------------------------------------------------------
# config_project_list_items
# ---------------------------------------------------------------------------

class TestConfigProjectListItems:
    def test_lists_all_projects(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.tui.screens import config_project_list_items
        save_config(LOCAL_CFG)
        save_projects([make_project("a"), make_project("b")])
        labels = _item_labels(config_project_list_items())
        assert "a" in labels
        assert "b" in labels

    def test_no_projects_placeholder(self, tmp_config):
        from colette_cli.tui.screens import config_project_list_items
        items = config_project_list_items()
        assert items[0].label == "(no projects)"

    def test_project_items_are_submenus(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.tui.screens import config_project_list_items
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        proj_item = next(i for i in config_project_list_items() if i.label == "proj")
        assert not proj_item.is_leaf

    def test_project_detail_shows_template(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.tui.screens import config_project_list_items
        save_config(LOCAL_CFG)
        save_projects([make_project("proj", template="my-tmpl")])
        proj_item = next(i for i in config_project_list_items() if i.label == "proj")
        assert proj_item.detail == "my-tmpl"


# ---------------------------------------------------------------------------
# main_menu_items
# ---------------------------------------------------------------------------

class TestMainMenuItems:
    def test_has_all_top_level_entries(self, tmp_config):
        from colette_cli.tui.screens import main_menu_items
        labels = _item_labels(main_menu_items())
        for label in ("Projects", "Templates", "Config", "Monitor"):
            assert label in labels

    def test_monitor_is_leaf(self, tmp_config):
        from colette_cli.tui.screens import main_menu_items
        monitor = next(i for i in main_menu_items() if i.label == "Monitor")
        assert monitor.is_leaf

    def test_projects_templates_config_are_submenus(self, tmp_config):
        from colette_cli.tui.screens import main_menu_items
        items = main_menu_items()
        for label in ("Projects", "Templates", "Config"):
            item = next(i for i in items if i.label == label)
            assert not item.is_leaf, f"{label} should be a submenu"
