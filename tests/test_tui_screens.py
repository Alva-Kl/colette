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


def _call_action(item):
    """Call a leaf MenuItem's action with curses suspended (patched out)."""
    with patch("curses.endwin"), patch("curses.doupdate"):
        item.run()


# ---------------------------------------------------------------------------
# _suspend / _suspend_with_pause error handling
# ---------------------------------------------------------------------------

class TestSuspendHelpers:
    def test_suspend_catches_system_exit_and_prompts(self):
        """_suspend must not let SystemExit escape — shows error and pauses."""
        from colette_cli.tui.screens import _suspend

        def failing():
            raise SystemExit(1)

        wrapped = _suspend(failing)
        with patch("curses.endwin"), patch("curses.doupdate"), \
             patch("builtins.input") as mock_input:
            wrapped()  # must not raise

        mock_input.assert_called_once()

    def test_suspend_with_pause_catches_system_exit(self):
        """_suspend_with_pause must not let SystemExit escape."""
        from colette_cli.tui.screens import _suspend_with_pause

        def failing():
            raise SystemExit(1)

        wrapped = _suspend_with_pause(failing)
        with patch("curses.endwin"), patch("curses.doupdate"), \
             patch("builtins.input") as mock_input:
            wrapped()  # must not raise

        mock_input.assert_called_once()

    def test_suspend_normal_action_does_not_prompt(self):
        """_suspend must NOT add an extra prompt for successful actions."""
        from colette_cli.tui.screens import _suspend
        called = []

        def ok():
            called.append(True)

        wrapped = _suspend(ok)
        with patch("curses.endwin"), patch("curses.doupdate"), \
             patch("builtins.input") as mock_input:
            wrapped()

        assert called == [True]
        mock_input.assert_not_called()

    def test_popup_shows_running_then_output(self):
        """_popup must call show_running before the command, then show_output."""
        from colette_cli.tui.screens import _popup
        call_order = []

        def cmd():
            call_order.append("cmd")
            print("done")

        wrapped = _popup(cmd)
        with patch("colette_cli.tui.forms.show_running", side_effect=lambda *a, **k: call_order.append("running")) as mr, \
             patch("colette_cli.tui.forms.show_output") as mo:
            wrapped()

        assert call_order == ["running", "cmd"]
        mo.assert_called_once()
        assert "done" in mo.call_args[0][0]

    def test_popup_strips_ansi(self):
        """_popup must strip ANSI escape codes before calling show_output."""
        from colette_cli.tui.screens import _popup

        def cmd():
            print("\x1b[1mBold\x1b[0m text")

        wrapped = _popup(cmd)
        with patch("colette_cli.tui.forms.show_running"), \
             patch("colette_cli.tui.forms.show_output") as mo:
            wrapped()

        assert "\x1b" not in mo.call_args[0][0]
        assert "Bold text" in mo.call_args[0][0]

class TestProjectListItems:
    def test_global_actions_always_present(self, tmp_config):
        from colette_cli.tui.screens import project_list_items
        labels = _item_labels(project_list_items())
        for label in ("Create project", "Link project", "Start All", "Stop All", "Update All"):
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
        with patch("colette_cli.session.cmd_start") as mock_start, \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Start All").run()
        mock_start.assert_called_once()
        assert mock_start.call_args[0][0].projects == []
        assert mock_start.call_args[0][0].machine is None

    def test_per_machine_start_all_calls_cmd_start_with_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        with patch("colette_cli.session.cmd_start") as mock_start, \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Start All — local").run()
        mock_start.assert_called_once()
        assert mock_start.call_args[0][0].machine == "local"
        assert mock_start.call_args[0][0].projects == []

    def test_per_machine_stop_all_calls_cmd_stop_with_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        with patch("colette_cli.session.cmd_stop") as mock_stop, \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Stop All — local").run()
        mock_stop.assert_called_once()
        assert mock_stop.call_args[0][0].machine == "local"
        assert mock_stop.call_args[0][0].projects == []

    def test_stop_all_calls_cmd_stop(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        with patch("colette_cli.session.cmd_stop") as mock_stop, \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Stop All").run()
        mock_stop.assert_called_once()
        assert mock_stop.call_args[0][0].projects == []

    def test_update_all_calls_cmd_update(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        with patch("colette_cli.session.cmd_update") as mock_update, \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Update All").run()
        mock_update.assert_called_once()
        assert mock_update.call_args[0][0].projects == []
        assert mock_update.call_args[0][0].machine is None

    def test_per_machine_update_all_calls_cmd_update_with_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        with patch("colette_cli.session.cmd_update") as mock_update, \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Update All — local").run()
        mock_update.assert_called_once()
        assert mock_update.call_args[0][0].machine == "local"
        assert mock_update.call_args[0][0].projects == []

    def test_create_project_calls_cmd_create(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        with patch("colette_cli.project.cmd_create") as mock_create, \
             patch("colette_cli.tui.forms.ask", side_effect=["new-proj", "local", ""]), \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
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
        for expected in ("Open session", "Start", "Stop", "Update", "Code", "Copilot", "Logs", "Monitor", "Edit hooks", "Delete", "Unlink"):
            assert expected in labels, f"missing: {expected}"

    def test_action_order(self, tmp_config):
        write_config(tmp_config, LOCAL_CFG)
        labels = _item_labels(self._get_items())
        assert labels == ["Open session", "Code", "Copilot", "Logs", "Monitor", "Start", "Stop", "Update", "Edit hooks", "Unlink", "Delete"]

    def test_start_calls_cmd_start_with_project_name(self, tmp_config):
        write_config(tmp_config, LOCAL_CFG)
        project = make_project("my-proj")
        with patch("colette_cli.session.cmd_start") as mock_start, \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
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
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            items = self._get_items(project)
            next(i for i in items if i.label == "Stop").run()
        mock_stop.assert_called_once()
        assert mock_stop.call_args[0][0].projects == ["my-proj"]

    def test_delete_calls_cmd_delete_with_project_name(self, tmp_config):
        write_config(tmp_config, LOCAL_CFG)
        project = make_project("my-proj")
        with patch("colette_cli.project.cmd_delete") as mock_delete, \
             patch("colette_cli.tui.forms.type_to_confirm", return_value=True), \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            items = self._get_items(project)
            next(i for i in items if i.label == "Delete").run()
        mock_delete.assert_called_once()
        assert mock_delete.call_args[0][0].name == "my-proj"

    def test_unlink_removes_project_from_config(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects, load_projects
        write_config(tmp_config, LOCAL_CFG)
        project = make_project("my-proj")
        save_projects([project])
        with patch("colette_cli.tui.forms.confirm", return_value=True):
            items = self._get_items(project)
            next(i for i in items if i.label == "Unlink").run()
        assert not any(p["name"] == "my-proj" for p in load_projects())

    def test_unlink_aborts_on_cancel(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects, load_projects
        write_config(tmp_config, LOCAL_CFG)
        project = make_project("my-proj")
        save_projects([project])
        with patch("colette_cli.tui.forms.confirm", return_value=False):
            items = self._get_items(project)
            next(i for i in items if i.label == "Unlink").run()
        assert any(p["name"] == "my-proj" for p in load_projects())

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
        assert labels == ["Create project", "Run update", "Edit hooks", "Edit parameters"]

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
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
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


    def test_add_machine_creates_local_machine(self, tmp_config):
        from colette_cli.utils.config import load_config
        from colette_cli.tui.screens import machine_list_items
        items = machine_list_items()
        with patch("colette_cli.tui.forms.ask", side_effect=["newmachine", "local", "", "/projects"]), \
             patch("colette_cli.tui.forms.confirm", return_value=False):
            next(i for i in items if i.label == "Add machine").run()
        cfg = load_config()
        assert "newmachine" in cfg["machines"]
        assert cfg["machines"]["newmachine"]["projects_dir"] == "/projects"
        assert cfg["machines"]["newmachine"]["type"] == "local"

    def test_add_machine_aborts_on_empty_name(self, tmp_config):
        from colette_cli.utils.config import load_config
        from colette_cli.tui.screens import machine_list_items
        items = machine_list_items()
        with patch("colette_cli.tui.forms.ask", return_value=None):
            next(i for i in items if i.label == "Add machine").run()
        assert not load_config().get("machines")

    def test_add_machine_creates_ssh_machine(self, tmp_config):
        from colette_cli.utils.config import load_config
        from colette_cli.tui.screens import machine_list_items
        items = machine_list_items()
        # name, type=ssh, host, key (empty → skip), no initial template, projects_dir, no set-default
        with patch("colette_cli.tui.forms.ask",
                   side_effect=["sshm", "ssh", "dev@myhost", "", "", "/projects"]), \
             patch("colette_cli.tui.forms.confirm", return_value=False):
            next(i for i in items if i.label == "Add machine").run()
        cfg = load_config()
        assert "sshm" in cfg["machines"]
        m = cfg["machines"]["sshm"]
        assert m["type"] == "ssh"
        assert m["host"] == "dev@myhost"
        assert "ssh_key" not in m
        assert m["projects_dir"] == "/projects"


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

    def test_edit_updates_machine_config(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        items = machine_action_items("local")
        with patch("colette_cli.tui.forms.ask", side_effect=["local", "/new/projects"]):
            next(i for i in items if i.label == "Edit").run()
        cfg = load_config()
        assert cfg["machines"]["local"]["projects_dir"] == "/new/projects"

    def test_remove_machine_removes_from_config(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        items = machine_action_items("local")
        with patch("colette_cli.tui.forms.confirm", return_value=True):
            next(i for i in items if i.label == "Remove").run()
        assert "local" not in load_config().get("machines", {})

    def test_remove_machine_aborts_on_cancel(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        items = machine_action_items("local")
        with patch("colette_cli.tui.forms.confirm", return_value=False):
            next(i for i in items if i.label == "Remove").run()
        assert "local" in load_config().get("machines", {})

    def test_edit_aborts_on_esc(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        items = machine_action_items("local")
        with patch("colette_cli.tui.forms.ask", return_value=None):
            next(i for i in items if i.label == "Edit").run()
        # Config unchanged
        assert load_config()["machines"]["local"]["projects_dir"] == "/tmp/projects"

    def test_remove_machine_clears_default_when_only_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        items = machine_action_items("local")
        with patch("colette_cli.tui.forms.confirm", return_value=True):
            next(i for i in items if i.label == "Remove").run()
        cfg = load_config()
        assert cfg.get("default_machine") is None

    def test_remove_non_default_machine_keeps_default(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        cfg = {
            "machines": {
                "local": make_local_machine("/tmp"),
                "other": make_local_machine("/other"),
            },
            "default_machine": "local",
        }
        save_config(cfg)
        from colette_cli.tui.screens import machine_action_items
        items = machine_action_items("other")
        with patch("colette_cli.tui.forms.confirm", return_value=True):
            next(i for i in items if i.label == "Remove").run()
        loaded = load_config()
        assert loaded["default_machine"] == "local"
        assert "other" not in loaded["machines"]

    def test_edit_machine_aborts_when_machine_missing(self, tmp_config):
        """edit action is a no-op when the machine no longer exists in config."""
        from colette_cli.utils.config import save_config, load_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        # Capture the action closure while 'local' exists, then delete it from config
        items = machine_action_items("ghost")
        original_cfg = load_config()
        with patch("colette_cli.tui.forms.ask") as mock_ask:
            next(i for i in items if i.label == "Edit").run()
        # ask should never be called — the machine was not found
        mock_ask.assert_not_called()


# ---------------------------------------------------------------------------
# machine_template_items
# ---------------------------------------------------------------------------

class TestMachineTemplateItems:
    CFG_WITH_TMPL = {
        "machines": {
            "local": {
                "type": "local",
                "projects_dir": "/tmp/projects",
                "templates": [{"name": "my-tmpl", "type": "directory", "path": "/tmp/tmpl"}],
            }
        },
        "default_machine": "local",
    }

    def test_add_template_is_first_item(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import machine_template_items
        save_config(LOCAL_CFG)
        items = machine_template_items("local")
        assert items[0].label == "Add template"
        assert items[0].is_leaf

    def test_configured_templates_appear(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import machine_template_items
        save_config(self.CFG_WITH_TMPL)
        labels = _item_labels(machine_template_items("local"))
        assert "my-tmpl" in labels

    def test_add_template_saves_to_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config, save_templates
        from colette_cli.tui.screens import machine_template_items
        save_config(LOCAL_CFG)
        save_templates({"templates": []})
        items = machine_template_items("local")
        with patch("colette_cli.tui.forms.ask", side_effect=["newtmpl", "directory", "/tmpl/path", None]), \
             patch("colette_cli.template.registry.scaffold_template_hook_files"):
            next(i for i in items if i.label == "Add template").run()
        cfg = load_config()
        tmpl_names = [t["name"] for t in cfg["machines"]["local"].get("templates", [])]
        assert "newtmpl" in tmpl_names

    def test_add_template_aborts_on_empty_name(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.tui.screens import machine_template_items
        save_config(LOCAL_CFG)
        items = machine_template_items("local")
        with patch("colette_cli.tui.forms.ask", return_value=None):
            next(i for i in items if i.label == "Add template").run()
        cfg = load_config()
        assert not cfg["machines"]["local"].get("templates")

    def test_add_template_with_git_type_uses_url(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config, save_templates
        from colette_cli.tui.screens import machine_template_items
        save_config(LOCAL_CFG)
        save_templates({"templates": []})
        items = machine_template_items("local")
        with patch("colette_cli.tui.forms.ask",
                   side_effect=["gittmpl", "git", "https://github.com/org/tmpl.git", None]), \
             patch("colette_cli.template.registry.scaffold_template_hook_files"):
            next(i for i in items if i.label == "Add template").run()
        cfg = load_config()
        tmpl = next(t for t in cfg["machines"]["local"]["templates"] if t["name"] == "gittmpl")
        assert tmpl["type"] == "git"
        assert tmpl["url"] == "https://github.com/org/tmpl.git"
        assert "path" not in tmpl

    def test_add_template_aborts_if_already_exists(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config, save_templates
        from colette_cli.tui.screens import machine_template_items
        save_config(self.CFG_WITH_TMPL)
        save_templates({"templates": [{"name": "my-tmpl"}]})
        items = machine_template_items("local")
        with patch("colette_cli.tui.forms.ask", return_value="my-tmpl"), \
             patch("colette_cli.template.registry.scaffold_template_hook_files"):
            next(i for i in items if i.label == "Add template").run()
        cfg = load_config()
        # Still only one template — duplicate was rejected
        assert len(cfg["machines"]["local"]["templates"]) == 1

    def test_remove_template_removes_from_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config, save_templates
        from colette_cli.tui.screens import machine_template_items
        save_config(self.CFG_WITH_TMPL)
        save_templates({"templates": []})
        items = machine_template_items("local")
        tmpl_item = next(i for i in items if i.label == "my-tmpl")
        children = tmpl_item.get_children()
        remove_item = next(i for i in children if i.label == "Remove")
        with patch("colette_cli.tui.forms.confirm", return_value=True):
            remove_item.run()
        cfg = load_config()
        tmpl_names = [t["name"] for t in cfg["machines"]["local"].get("templates", [])]
        assert "my-tmpl" not in tmpl_names

    def test_edit_template_updates_source(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config, save_templates
        from colette_cli.tui.screens import machine_template_items
        save_config(self.CFG_WITH_TMPL)
        save_templates({"templates": [{"name": "my-tmpl"}]})
        items = machine_template_items("local")
        tmpl_item = next(i for i in items if i.label == "my-tmpl")
        children = tmpl_item.get_children()
        edit_item = next(i for i in children if i.label == "Edit")
        with patch("colette_cli.tui.forms.ask", side_effect=["directory", "/new/path", ""]), \
             patch("colette_cli.template.registry.scaffold_template_hook_files"):
            edit_item.run()
        cfg = load_config()
        tmpl = next(t for t in cfg["machines"]["local"]["templates"] if t["name"] == "my-tmpl")
        assert tmpl["path"] == "/new/path"


# ---------------------------------------------------------------------------
# TestConfigProjectListItems
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

    def test_monitor_is_submenu(self, tmp_config):
        from colette_cli.tui.screens import main_menu_items
        monitor = next(i for i in main_menu_items() if i.label == "Monitor")
        assert not monitor.is_leaf

    def test_monitor_submenu_has_three_modes(self, tmp_config):
        from colette_cli.tui.screens import main_menu_items
        monitor = next(i for i in main_menu_items() if i.label == "Monitor")
        sub_labels = _item_labels(monitor.get_children())
        assert sub_labels == ["Standard", "Copilot", "All"]

    def test_projects_templates_config_are_submenus(self, tmp_config):
        from colette_cli.tui.screens import main_menu_items
        items = main_menu_items()
        for label in ("Projects", "Templates", "Config"):
            item = next(i for i in items if i.label == label)
            assert not item.is_leaf, f"{label} should be a submenu"


# ---------------------------------------------------------------------------
# debug_menu_items / hook_log_items
# ---------------------------------------------------------------------------

class TestDebugMenuItems:
    def test_has_hook_log(self, tmp_config):
        from colette_cli.tui.screens import debug_menu_items
        labels = _item_labels(debug_menu_items())
        assert "Hook log" in labels

    def test_hook_log_is_submenu(self, tmp_config):
        from colette_cli.tui.screens import debug_menu_items
        item = next(i for i in debug_menu_items() if i.label == "Hook log")
        assert not item.is_leaf

    def test_debug_is_in_main_menu(self, tmp_config):
        from colette_cli.tui.screens import main_menu_items
        labels = _item_labels(main_menu_items())
        assert "Debug" in labels

    def test_debug_is_submenu_in_main_menu(self, tmp_config):
        from colette_cli.tui.screens import main_menu_items
        item = next(i for i in main_menu_items() if i.label == "Debug")
        assert not item.is_leaf


class TestHookLogItems:
    def _entry(self, project="proj", hook="onstart", ts="2026-01-01T00:00:00Z", output="err msg"):
        return {"ts": ts, "project": project, "template": "t", "hook": hook, "exit_code": 1, "output": output}

    def test_shows_placeholder_when_empty(self, tmp_config):
        from colette_cli.tui.screens import hook_log_items
        labels = _item_labels(hook_log_items())
        assert "(no failures recorded)" in labels

    def test_clear_log_item_always_present(self, tmp_config):
        from colette_cli.tui.screens import hook_log_items
        items = hook_log_items()
        assert items[0].label == "Clear log"
        assert items[0].is_leaf

    def test_failure_entries_appear(self, tmp_config):
        from colette_cli.utils.config import append_hook_failure
        from colette_cli.tui.screens import hook_log_items
        append_hook_failure(self._entry(project="my-proj", hook="onstart"))
        labels = _item_labels(hook_log_items())
        assert any("my-proj" in l and "onstart" in l for l in labels)

    def test_most_recent_first(self, tmp_config):
        from colette_cli.utils.config import append_hook_failure
        from colette_cli.tui.screens import hook_log_items
        append_hook_failure(self._entry(project="first", ts="2026-01-01T00:00:00Z"))
        append_hook_failure(self._entry(project="second", ts="2026-01-02T00:00:00Z"))
        items = hook_log_items()
        # first non-clear item should be the most-recent (second)
        entry_items = [i for i in items if i.label != "Clear log" and i.selectable]
        assert "second" in entry_items[0].label

    def test_entry_has_timestamp_as_detail(self, tmp_config):
        from colette_cli.utils.config import append_hook_failure
        from colette_cli.tui.screens import hook_log_items
        append_hook_failure(self._entry(ts="2026-03-24T13:00:00Z"))
        item = next(i for i in hook_log_items() if i.selectable and i.label != "Clear log")
        assert item.detail == "2026-03-24T13:00:00Z"

    def test_entry_children_contain_output(self, tmp_config):
        from colette_cli.utils.config import append_hook_failure
        from colette_cli.tui.screens import hook_log_items
        append_hook_failure(self._entry(output="command not found"))
        item = next(i for i in hook_log_items() if i.selectable and i.label != "Clear log")
        child_labels = _item_labels(item.get_children())
        assert any("command not found" in l for l in child_labels)

    def test_clear_log_removes_entries(self, tmp_config):
        from colette_cli.utils.config import append_hook_failure, load_hook_failures
        from colette_cli.tui.screens import hook_log_items
        append_hook_failure(self._entry())
        items = hook_log_items()
        items[0].run()  # "Clear log"
        assert load_hook_failures() == []


# ---------------------------------------------------------------------------
# _async_popup
# ---------------------------------------------------------------------------

class TestAsyncPopup:
    def _run_async(self, fn, label="test-op", timeout=2.0):
        """Run _async_popup wrapper and wait for the background thread."""
        import threading
        import colette_cli.tui.state as state
        from colette_cli.tui.screens import _async_popup

        done = threading.Event()
        original_append = list.append

        # Patch notifications.append to signal when notification lands
        with patch("colette_cli.utils.notify.send_notification"), \
             patch("colette_cli.tui.forms.show_running"):
            # Wrap the action so we know when the thread finishes
            completed = threading.Event()

            def _patched_fn(*a, **kw):
                try:
                    fn(*a, **kw)
                finally:
                    completed.set()

            wrapper = _async_popup(_patched_fn, label)
            wrapper()
            completed.wait(timeout)

        return state.notifications

    def test_success_appends_notification(self, tmp_config):
        import colette_cli.tui.state as state
        state.notifications.clear()

        def ok():
            print("all good")

        notifs = self._run_async(ok, "test-success")
        assert len(notifs) == 1
        assert notifs[0].success is True
        assert notifs[0].label == "test-success"
        assert "all good" in notifs[0].output

    def test_failure_appends_notification(self, tmp_config):
        import colette_cli.tui.state as state
        state.notifications.clear()

        def fail():
            raise SystemExit(1)

        notifs = self._run_async(fail, "test-fail")
        assert len(notifs) == 1
        assert notifs[0].success is False
        assert notifs[0].label == "test-fail"

    def test_running_tasks_incremented_then_decremented(self, tmp_config):
        import colette_cli.tui.state as state
        import threading
        from colette_cli.tui.screens import _async_popup

        state.notifications.clear()
        state.running_tasks = 0

        started = threading.Event()
        finish = threading.Event()

        def slow():
            started.set()
            finish.wait()

        with patch("colette_cli.utils.notify.send_notification"), \
             patch("colette_cli.tui.forms.show_running"):
            wrapper = _async_popup(slow, "slow-op")
            wrapper()

        started.wait(2.0)
        with state.running_tasks_lock:
            count_during = state.running_tasks
        finish.set()
        # Give thread time to decrement
        import time; time.sleep(0.1)
        with state.running_tasks_lock:
            count_after = state.running_tasks

        assert count_during == 1
        assert count_after == 0

    def test_notification_seen_false_initially(self, tmp_config):
        import colette_cli.tui.state as state
        state.notifications.clear()

        notifs = self._run_async(lambda: None, "seen-test")
        assert notifs[0].seen is False

    def test_desktop_notification_fired(self, tmp_config):
        import colette_cli.tui.state as state
        import threading
        from colette_cli.tui.screens import _async_popup

        state.notifications.clear()
        completed = threading.Event()

        def ok():
            completed.set()

        with patch("colette_cli.utils.notify.send_notification") as mock_notif, \
             patch("colette_cli.tui.forms.show_running"):
            _async_popup(ok, "notif-test")()
            completed.wait(2.0)
            import time; time.sleep(0.05)

        mock_notif.assert_called_once()
        title = mock_notif.call_args[0][0]
        assert "notif-test" in title


# ---------------------------------------------------------------------------
# notifications_screen_items
# ---------------------------------------------------------------------------

class TestNotificationsScreen:
    def _push_notif(self, label="op", success=True, output=""):
        import colette_cli.tui.state as state
        state.notifications.append(
            state.Notification(label=label, success=success, output=output)
        )

    def setup_method(self):
        import colette_cli.tui.state as state
        state.notifications.clear()

    def test_clear_all_removes_notifications(self):
        import colette_cli.tui.state as state
        from colette_cli.tui.screens import notifications_screen_items
        self._push_notif("op1")
        items = notifications_screen_items()
        clear_item = next(i for i in items if i.label == "Clear all")
        clear_item.run()
        assert state.notifications == []

    def test_empty_shows_placeholder(self):
        from colette_cli.tui.screens import notifications_screen_items
        labels = [i.label for i in notifications_screen_items()]
        assert "(no notifications)" in labels

    def test_success_notification_shown(self):
        from colette_cli.tui.screens import notifications_screen_items
        self._push_notif("start-proj", success=True)
        labels = [i.label for i in notifications_screen_items()]
        assert any("start-proj" in l and "✓" in l for l in labels)

    def test_failure_notification_shown(self):
        from colette_cli.tui.screens import notifications_screen_items
        self._push_notif("bad-op", success=False, output="error text")
        labels = [i.label for i in notifications_screen_items()]
        assert any("bad-op" in l and "✗" in l for l in labels)

    def test_failed_notification_action_shows_output(self):
        from colette_cli.tui.screens import notifications_screen_items
        self._push_notif("bad-op", success=False, output="error text")
        items = notifications_screen_items()
        fail_item = next(i for i in items if "bad-op" in i.label)
        with patch("colette_cli.tui.forms.show_output") as mo:
            fail_item.run()
        mo.assert_called_once()
        assert "error text" in mo.call_args[0][0]

    def test_opening_screen_marks_notifications_seen(self):
        import colette_cli.tui.state as state
        from colette_cli.tui.screens import notifications_screen_items
        self._push_notif("op")
        assert state.notifications[0].seen is False
        notifications_screen_items()
        assert state.notifications[0].seen is True
