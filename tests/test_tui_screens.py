"""Tests for colette_cli.tui.screens — screen builders and actions."""

import pytest
from argparse import Namespace
from unittest.mock import patch, MagicMock

from tests.conftest import (
    write_config,
    write_projects,
    make_local_machine,
    make_project,
)

LOCAL_CFG = {
    "machines": {"local": make_local_machine("/tmp/projects")},
    "default_machine": "local",
}


class _SyncThread:
    """Stand-in for threading.Thread that runs its target synchronously,
    so async TUI actions (Create/Delete/Sync) can be asserted on without
    racing a real background thread."""
    def __init__(self, target, daemon=False):
        self._target = target

    def start(self):
        self._target()


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
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.tui.screens import project_list_items
        save_config(LOCAL_CFG)
        save_local_projects([make_project("my-proj")])
        items = project_list_items()
        labels = _item_labels(items)
        proj_idx = labels.index("my-proj")
        start_idx = labels.index("Start All")
        assert proj_idx < start_idx

    def test_projects_listed_under_machine_title(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.tui.screens import project_list_items
        save_config(LOCAL_CFG)
        save_local_projects([make_project("my-proj")])
        labels = _item_labels(project_list_items())
        assert "my-proj" in labels

    def test_no_projects_placeholder_present(self, tmp_config):
        from colette_cli.tui.screens import project_list_items
        labels = _item_labels(project_list_items())
        assert "(no projects)" in labels

    def test_start_all_calls_cmd_start(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj")])
        with patch("colette_cli.session.cmd_start") as mock_start, \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Start All").run()
        mock_start.assert_called_once()
        assert mock_start.call_args[0][0].projects == []
        assert mock_start.call_args[0][0].machine is None

    def test_per_machine_start_all_calls_cmd_start_with_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj")])
        with patch("colette_cli.session.cmd_start") as mock_start, \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Start All — local").run()
        mock_start.assert_called_once()
        assert mock_start.call_args[0][0].machine == "local"
        assert mock_start.call_args[0][0].projects == []

    def test_per_machine_stop_all_calls_cmd_stop_with_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj")])
        with patch("colette_cli.session.cmd_stop") as mock_stop, \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Stop All — local").run()
        mock_stop.assert_called_once()
        assert mock_stop.call_args[0][0].machine == "local"
        assert mock_stop.call_args[0][0].projects == []

    def test_stop_all_calls_cmd_stop(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj")])
        with patch("colette_cli.session.cmd_stop") as mock_stop, \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Stop All").run()
        mock_stop.assert_called_once()
        assert mock_stop.call_args[0][0].projects == []

    def test_update_all_calls_cmd_update(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj")])
        with patch("colette_cli.session.cmd_update") as mock_update, \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Update All").run()
        mock_update.assert_called_once()
        assert mock_update.call_args[0][0].projects == []
        assert mock_update.call_args[0][0].machine is None

    def test_per_machine_update_all_calls_cmd_update_with_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj")])
        with patch("colette_cli.session.cmd_update") as mock_update, \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Update All — local").run()
        mock_update.assert_called_once()
        assert mock_update.call_args[0][0].machine == "local"
        assert mock_update.call_args[0][0].projects == []

    def test_per_machine_terminal_calls_cmd_attach(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj")])
        with patch("colette_cli.project.cmd_attach") as mock_attach, \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Terminal — local").run()
        mock_attach.assert_called_once()
        assert mock_attach.call_args[0][0].name == "local"

    def test_per_machine_sync_shown_only_for_remote(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        cfg = {
            "machines": {
                "local": make_local_machine("/tmp/projects"),
                "remote": {"type": "ssh", "host": "user@host", "templates": []},
            },
            "default_machine": "local",
        }
        save_config(cfg)
        save_local_projects([
            make_project("local-proj", machine="local"),
            make_project("remote-proj", machine="remote", path="/tmp/projects/remote-proj"),
        ])
        from colette_cli.tui.screens import project_list_items
        labels = _item_labels(project_list_items())
        assert "Terminal — local" in labels
        assert "Terminal — remote" in labels
        assert "Sync — remote" in labels
        assert "Sync — local" not in labels

    def test_per_machine_sync_calls_cmd_config_sync(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        cfg = {
            "machines": {
                "remote": {"type": "ssh", "host": "user@host", "templates": []},
            },
            "default_machine": "remote",
        }
        save_config(cfg)
        save_local_projects([make_project("proj", machine="remote", path="/tmp/projects/proj")])
        with patch("colette_cli.config.cmd_config_sync") as mock_sync, \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Sync — remote").run()
        mock_sync.assert_called_once()
        assert mock_sync.call_args[0][0].machine_name == "remote"

    def test_per_machine_separator_present(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj")])
        from colette_cli.tui.screens import project_list_items
        items = project_list_items()
        separator_label = "    " + "─" * 12
        sep_items = [i for i in items if i.label == separator_label]
        assert len(sep_items) == 1
        assert sep_items[0].selectable is False
        labels = _item_labels(items)
        proj_idx = labels.index("proj")
        sep_idx = labels.index(separator_label)
        terminal_idx = labels.index("Terminal — local")
        assert proj_idx < sep_idx < terminal_idx

    def test_create_project_calls_cmd_create(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        with patch("colette_cli.project.cmd_create") as mock_create, \
             patch("colette_cli.tui.forms.form",
                   return_value={"name": "new-proj", "machine": "local", "template": "(none)"}), \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Create project").run()
        mock_create.assert_called_once()
        args = mock_create.call_args[0][0]
        assert args.name == "new-proj"
        assert args.machine == "local"
        assert args.template is None

    def test_create_project_uses_selected_template(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        with patch("colette_cli.project.cmd_create") as mock_create, \
             patch("colette_cli.tui.forms.form",
                   return_value={"name": "new-proj", "machine": "local", "template": "my-tmpl"}), \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Create project").run()
        assert mock_create.call_args[0][0].template == "my-tmpl"

    def test_create_project_aborts_on_form_cancel(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        with patch("colette_cli.project.cmd_create") as mock_create, \
             patch("colette_cli.tui.forms.form", return_value=None):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Create project").run()
        mock_create.assert_not_called()

    def test_create_project_name_validator_rejects_existing_machine_name(self, tmp_config):
        from colette_cli.utils.config import save_config
        cfg = {
            "machines": {
                "local": {"type": "local", "projects_dir": "/tmp/projects"},
                "other-machine": {"type": "local"},
            },
            "default_machine": "local",
        }
        save_config(cfg)
        from colette_cli.tui.screens import project_list_items
        items = project_list_items()
        captured = {}

        def _fake_form(fields, title=""):
            captured["fields"] = fields
            return None

        with patch("colette_cli.tui.forms.form", side_effect=_fake_form):
            next(i for i in items if i.label == "Create project").run()
        name_field = next(f for f in captured["fields"] if f.name == "name")
        ok, _ = name_field.validator("other-machine")
        assert ok is False

    def test_link_project_calls_cmd_link(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "mydir"
        project_dir.mkdir()
        with patch("colette_cli.project.cmd_link") as mock_link, \
             patch("colette_cli.tui.forms.form",
                   return_value={"path": str(project_dir), "machine": "local", "name": "", "template": "(none)"}):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Link project").run()
        mock_link.assert_called_once()
        args = mock_link.call_args[0][0]
        assert args.path == str(project_dir)
        assert args.machine == "local"
        assert args.name is None
        assert args.template is None

    def test_link_project_aborts_on_form_cancel(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        with patch("colette_cli.project.cmd_link") as mock_link, \
             patch("colette_cli.tui.forms.form", return_value=None):
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
        for expected in ("Open session", "Start", "Stop", "Update", "IDE", "Agent", "Logs", "Monitor", "Edit hooks", "Delete", "Unlink"):
            assert expected in labels, f"missing: {expected}"

    def test_action_order(self, tmp_config):
        write_config(tmp_config, LOCAL_CFG)
        labels = _item_labels(self._get_items())
        assert labels == ["Open session", "IDE", "Agent", "Logs", "Monitor", "Start", "Stop", "Update", "Edit hooks", "Unlink", "Delete"]

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
        """Delete runs cmd_delete in a background thread (_async_popup) — run it
        synchronously so the assertion below isn't racing a real thread."""
        write_config(tmp_config, LOCAL_CFG)
        project = make_project("my-proj")
        with patch("colette_cli.project.cmd_delete") as mock_delete, \
             patch("colette_cli.tui.forms.type_to_confirm", return_value=True), \
             patch("colette_cli.tui.forms.confirm", return_value=True), \
             patch("threading.Thread", _SyncThread), \
             patch("colette_cli.utils.notify.send_notification"), \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            items = self._get_items(project)
            next(i for i in items if i.label == "Delete").run()
        mock_delete.assert_called_once()
        assert mock_delete.call_args[0][0].name == "my-proj"

    def test_unlink_removes_project_from_config(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects, load_projects
        write_config(tmp_config, LOCAL_CFG)
        project = make_project("my-proj")
        save_local_projects([project])
        with patch("colette_cli.tui.forms.confirm", return_value=True):
            items = self._get_items(project)
            next(i for i in items if i.label == "Unlink").run()
        assert not any(p["name"] == "my-proj" for p in load_projects())

    def test_unlink_aborts_on_cancel(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects, load_projects
        write_config(tmp_config, LOCAL_CFG)
        project = make_project("my-proj")
        save_local_projects([project])
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

    def test_open_session_fetches_hooks_over_ssh_not_local_push(self, tmp_config):
        """Opening a session on a remote machine fetches hook content live over
        SSH (ssh_read_hook_files) — it must never push/write anything back."""
        from colette_cli.utils.config import save_config, save_local_projects
        remote_cfg = {
            "machines": {"remote": {"type": "ssh", "host": "myhost"}},
            "default_machine": "remote",
        }
        save_config(remote_cfg)
        project = make_project("my-proj", machine="remote")
        save_local_projects([project])

        items = self._get_items(project)
        open_item = next(i for i in items if i.label == "Open session")

        with patch("colette_cli.utils.ssh.ssh_read_hook_files", return_value={}) as mock_fetch, \
             patch("colette_cli.utils.ssh.push_project_entry") as mock_push, \
             patch("colette_cli.utils.ssh.ssh_interactive"), \
             patch("curses.endwin"), patch("curses.doupdate"):
            open_item.run()

        mock_fetch.assert_called_once()
        mock_push.assert_not_called()


# ---------------------------------------------------------------------------
# machine_template_action_items (unified per-template action set)
# ---------------------------------------------------------------------------

class TestMachineTemplateActionItems:
    def test_returns_unified_action_set(self, tmp_config):
        from colette_cli.tui.screens import machine_template_action_items
        labels = _item_labels(machine_template_action_items("local", "my-tmpl"))
        assert labels == [
            "Create project", "Run update", "Edit hooks", "Edit parameters",
            "Edit", "Rename", "Remove",
        ]

    def test_run_update_resolves_cache_only_template_path(self, tmp_config):
        """Regression: 'Run update' on a template known only via the sync
        cache (never explicitly configured on this machine) must still
        resolve a real template_path — previously used get_machine_template
        (config-only), which silently dropped the path for cache-only
        templates."""
        from colette_cli.utils.config import save_config, save_machine_cache
        from colette_cli.tui.screens import machine_template_action_items
        save_config({
            "machines": {"remote": {"type": "ssh", "host": "user@remote", "projects_dir": "/home/user"}},
            "default_machine": "remote",
        })
        save_machine_cache("remote", {
            "machine": "remote", "synced_at": "x", "projects_dir": "/home/user",
            "templates": [{"name": "cached-tmpl", "type": "directory", "path": "/remote/tmpl/path"}],
            "projects": [],
        })
        items = machine_template_action_items("remote", "cached-tmpl")
        run_update = next(i for i in items if i.label == "Run update")
        with patch("colette_cli.template.run_onupdate_for_template") as mock_run, \
             patch("threading.Thread", _SyncThread), \
             patch("colette_cli.utils.notify.send_notification"), \
             patch("colette_cli.tui.forms.show_running"):
            run_update.run()
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["template_path"] == "/remote/tmpl/path"

    def test_edit_hooks_is_submenu(self, tmp_config):
        from colette_cli.tui.screens import machine_template_action_items
        edit_hooks = next(i for i in machine_template_action_items("local", "my-tmpl") if i.label == "Edit hooks")
        assert not edit_hooks.is_leaf

    def test_edit_parameters_is_submenu(self, tmp_config):
        from colette_cli.tui.screens import machine_template_action_items
        edit_params = next(i for i in machine_template_action_items("local", "my-tmpl") if i.label == "Edit parameters")
        assert not edit_params.is_leaf

    def test_create_project_calls_cmd_create_with_correct_machine(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import machine_template_action_items
        save_config(LOCAL_CFG)
        items = machine_template_action_items("local", "my-tmpl")
        create = next(i for i in items if i.label == "Create project")
        with patch("colette_cli.project.cmd_create") as mock_create, \
             patch("colette_cli.tui.forms.ask", return_value="new-proj"), \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            create.run()
        mock_create.assert_called_once()
        args = mock_create.call_args[0][0]
        assert args.name == "new-proj"
        assert args.template == "my-tmpl"
        assert args.machine == "local"

    def test_create_project_aborts_on_empty_name(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import machine_template_action_items
        save_config(LOCAL_CFG)
        items = machine_template_action_items("local", "my-tmpl")
        create = next(i for i in items if i.label == "Create project")
        with patch("colette_cli.project.cmd_create") as mock_create, \
             patch("colette_cli.tui.forms.ask", return_value=None):
            create.run()
        mock_create.assert_not_called()

    def test_edit_updates_template_source(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.tui.screens import machine_template_action_items
        save_config({
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": "/tmp/projects",
                    "templates": [{"name": "my-tmpl", "type": "directory", "path": "/old/path"}],
                }
            },
            "default_machine": "local",
        })
        items = machine_template_action_items("local", "my-tmpl")
        edit = next(i for i in items if i.label == "Edit")
        with patch("colette_cli.tui.forms.form",
                   return_value={"type": "directory", "source": "/new/path", "description": ""}):
            edit.run()
        cfg = load_config()
        tmpl = next(t for t in cfg["machines"]["local"]["templates"] if t["name"] == "my-tmpl")
        assert tmpl["path"] == "/new/path"

    def test_edit_aborts_on_form_cancel(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.tui.screens import machine_template_action_items
        save_config({
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": "/tmp/projects",
                    "templates": [{"name": "my-tmpl", "type": "directory", "path": "/old/path"}],
                }
            },
            "default_machine": "local",
        })
        items = machine_template_action_items("local", "my-tmpl")
        edit = next(i for i in items if i.label == "Edit")
        with patch("colette_cli.tui.forms.form", return_value=None):
            edit.run()
        cfg = load_config()
        tmpl = next(t for t in cfg["machines"]["local"]["templates"] if t["name"] == "my-tmpl")
        assert tmpl["path"] == "/old/path"

    def test_rename_renames_template(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.tui.screens import machine_template_action_items
        save_config({
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": "/tmp/projects",
                    "templates": [{"name": "my-tmpl", "type": "directory", "path": "/tmp/path"}],
                }
            },
            "default_machine": "local",
        })
        items = machine_template_action_items("local", "my-tmpl")
        rename = next(i for i in items if i.label == "Rename")
        with patch("colette_cli.tui.forms.ask", return_value="renamed-tmpl"):
            rename.run()
        cfg = load_config()
        names = [t["name"] for t in cfg["machines"]["local"]["templates"]]
        assert "renamed-tmpl" in names
        assert "my-tmpl" not in names

    def test_remove_removes_template(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.tui.screens import machine_template_action_items
        save_config({
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": "/tmp/projects",
                    "templates": [{"name": "my-tmpl", "type": "directory", "path": "/tmp/path"}],
                }
            },
            "default_machine": "local",
        })
        items = machine_template_action_items("local", "my-tmpl")
        remove = next(i for i in items if i.label == "Remove")
        with patch("colette_cli.tui.forms.confirm", return_value=True):
            remove.run()
        cfg = load_config()
        assert not any(t["name"] == "my-tmpl" for t in cfg["machines"]["local"].get("templates", []))

    def test_remove_aborts_on_cancel(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.tui.screens import machine_template_action_items
        save_config({
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": "/tmp/projects",
                    "templates": [{"name": "my-tmpl", "type": "directory", "path": "/tmp/path"}],
                }
            },
            "default_machine": "local",
        })
        items = machine_template_action_items("local", "my-tmpl")
        remove = next(i for i in items if i.label == "Remove")
        with patch("colette_cli.tui.forms.confirm", return_value=False):
            remove.run()
        cfg = load_config()
        assert any(t["name"] == "my-tmpl" for t in cfg["machines"]["local"].get("templates", []))


# ---------------------------------------------------------------------------
# template_param_items
# ---------------------------------------------------------------------------

class TestTemplateParamItems:
    """Tests for template_param_items using machine-specific storage."""

    MACHINE_CFG = {
        "machines": {
            "local": {
                "type": "local",
                "projects_dir": "/tmp/projects",
                "templates": [{"name": "tmpl", "type": "directory", "path": "/tmpl"}],
            }
        },
        "default_machine": "local",
    }

    def _setup(self, tmp_config, params=None):
        import copy
        from colette_cli.utils.config import save_config
        cfg = copy.deepcopy(self.MACHINE_CFG)
        if params:
            cfg["machines"]["local"]["templates"][0]["params"] = params
        save_config(cfg)

    def test_add_parameter_item_always_present(self, tmp_config):
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config)
        items = template_param_items("tmpl", "local")
        assert items[0].label == "Add parameter"
        assert items[0].is_leaf

    def test_no_params_shows_placeholder(self, tmp_config):
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config)
        labels = _item_labels(template_param_items("tmpl", "local"))
        assert "(no parameters)" in labels

    def test_existing_params_appear(self, tmp_config):
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config, params={"PORT": "8080", "ENV": "dev"})
        labels = _item_labels(template_param_items("tmpl", "local"))
        assert "PORT" in labels
        assert "ENV" in labels

    def test_param_item_shows_value_as_detail(self, tmp_config):
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config, params={"PORT": "8080"})
        port_item = next(i for i in template_param_items("tmpl", "local") if i.label == "PORT")
        assert port_item.detail == "8080"

    def test_param_item_has_edit_and_remove_children(self, tmp_config):
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config, params={"PORT": "8080"})
        port_item = next(i for i in template_param_items("tmpl", "local") if i.label == "PORT")
        assert not port_item.is_leaf
        child_labels = _item_labels(port_item.get_children())
        assert "Edit value" in child_labels
        assert "Remove" in child_labels

    def test_add_parameter_saves_to_machine_config(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config)
        items = template_param_items("tmpl", "local")
        with patch("colette_cli.tui.forms.ask", side_effect=["MYKEY", "myval"]):
            items[0].run()  # Add parameter
        cfg = load_config()
        tmpl = next(t for t in cfg["machines"]["local"]["templates"] if t["name"] == "tmpl")
        assert tmpl.get("params", {}).get("MYKEY") == "myval"

    def test_add_parameter_aborts_on_empty_key(self, tmp_config):
        from colette_cli.utils.config import load_config
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config)
        items = template_param_items("tmpl", "local")
        with patch("colette_cli.tui.forms.ask", return_value=None):
            items[0].run()
        cfg = load_config()
        tmpl = next(t for t in cfg["machines"]["local"]["templates"] if t["name"] == "tmpl")
        assert not tmpl.get("params")

    def test_remove_parameter_deletes_from_machine_config(self, tmp_config):
        from colette_cli.utils.config import load_config
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config, params={"PORT": "8080"})
        items = template_param_items("tmpl", "local")
        port_item = next(i for i in items if i.label == "PORT")
        remove_item = next(i for i in port_item.get_children() if i.label == "Remove")
        with patch("colette_cli.tui.forms.confirm", return_value=True):
            remove_item.run()
        cfg = load_config()
        tmpl = next(t for t in cfg["machines"]["local"]["templates"] if t["name"] == "tmpl")
        assert "PORT" not in (tmpl.get("params") or {})

    def test_edit_parameter_updates_machine_config(self, tmp_config):
        from colette_cli.utils.config import load_config
        from colette_cli.tui.screens import template_param_items
        self._setup(tmp_config, params={"PORT": "8080"})
        items = template_param_items("tmpl", "local")
        port_item = next(i for i in items if i.label == "PORT")
        edit_item = next(i for i in port_item.get_children() if i.label == "Edit value")
        with patch("colette_cli.tui.forms.ask", return_value="9090"):
            edit_item.run()
        cfg = load_config()
        tmpl = next(t for t in cfg["machines"]["local"]["templates"] if t["name"] == "tmpl")
        assert tmpl["params"]["PORT"] == "9090"


# ---------------------------------------------------------------------------
# machine_list_items / machine_action_items
# ---------------------------------------------------------------------------

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
        with patch("colette_cli.tui.forms.form", return_value={
            "name": "newmachine", "type": "local", "projects_dir": "/projects",
            "add_template": "no",
        }):
            next(i for i in items if i.label == "Add machine").run()
        cfg = load_config()
        assert "newmachine" in cfg["machines"]
        assert cfg["machines"]["newmachine"]["projects_dir"] == "/projects"
        assert cfg["machines"]["newmachine"]["type"] == "local"

    def test_add_machine_aborts_on_form_cancel(self, tmp_config):
        from colette_cli.utils.config import load_config
        from colette_cli.tui.screens import machine_list_items
        items = machine_list_items()
        with patch("colette_cli.tui.forms.form", return_value=None):
            next(i for i in items if i.label == "Add machine").run()
        assert not load_config().get("machines")

    def test_add_machine_creates_ssh_machine(self, tmp_config):
        from colette_cli.utils.config import load_config
        from colette_cli.tui.screens import machine_list_items
        items = machine_list_items()
        with patch("colette_cli.tui.forms.form", return_value={
            "name": "sshm", "type": "ssh", "host": "dev@myhost",
            "port": "", "ssh_key": "", "colette_path": "",
            "projects_dir": "/projects", "add_template": "no",
        }):
            next(i for i in items if i.label == "Add machine").run()
        cfg = load_config()
        assert "sshm" in cfg["machines"]
        m = cfg["machines"]["sshm"]
        assert m["type"] == "ssh"
        assert m["host"] == "dev@myhost"
        assert "ssh_key" not in m
        assert "port" not in m
        assert m["projects_dir"] == "/projects"

    def test_add_machine_creates_ssh_machine_with_port(self, tmp_config):
        from colette_cli.utils.config import load_config
        from colette_cli.tui.screens import machine_list_items
        items = machine_list_items()
        with patch("colette_cli.tui.forms.form", return_value={
            "name": "sshm", "type": "ssh", "host": "dev@myhost",
            "port": "24", "ssh_key": "", "colette_path": "",
            "projects_dir": "/projects", "add_template": "no",
        }):
            next(i for i in items if i.label == "Add machine").run()
        cfg = load_config()
        m = cfg["machines"]["sshm"]
        assert m["port"] == 24

    def test_add_machine_with_initial_template(self, tmp_config):
        from colette_cli.utils.config import load_config
        from colette_cli.tui.screens import machine_list_items
        items = machine_list_items()
        with patch("colette_cli.tui.forms.form", return_value={
            "name": "newmachine", "type": "local", "projects_dir": "/projects",
            "add_template": "yes", "template_name": "web", "template_type": "directory",
            "template_source": "/tmpl/web",
        }):
            next(i for i in items if i.label == "Add machine").run()
        cfg = load_config()
        tmpl = cfg["machines"]["newmachine"]["templates"][0]
        assert tmpl["name"] == "web"
        assert tmpl["path"] == "/tmpl/web"

    def test_add_machine_name_validator_rejects_existing_template_name(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import machine_list_items
        save_config({
            "machines": {
                "local": {
                    "type": "local",
                    "templates": [{"name": "my-tmpl", "type": "directory", "path": "/tmp/tmpl"}],
                }
            },
            "default_machine": "local",
        })
        items = machine_list_items()
        captured = {}

        def _fake_form(fields, title=""):
            captured["fields"] = fields
            return None

        with patch("colette_cli.tui.forms.form", side_effect=_fake_form):
            next(i for i in items if i.label == "Add machine").run()
        name_field = next(f for f in captured["fields"] if f.name == "name")
        ok, _ = name_field.validator("my-tmpl")
        assert ok is False

    def test_add_machine_name_validator_rejects_existing_project_name(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.tui.screens import machine_list_items
        save_config(LOCAL_CFG)
        save_local_projects([{"name": "my-project", "machine": "local", "path": "/tmp/my-project"}])
        items = machine_list_items()
        captured = {}

        def _fake_form(fields, title=""):
            captured["fields"] = fields
            return None

        with patch("colette_cli.tui.forms.form", side_effect=_fake_form):
            next(i for i in items if i.label == "Add machine").run()
        name_field = next(f for f in captured["fields"] if f.name == "name")
        ok, _ = name_field.validator("my-project")
        assert ok is False


class TestMachineActionItems:
    def test_returns_edit_set_default_rename_templates_projects_remove(self, tmp_config):
        from colette_cli.tui.screens import machine_action_items
        labels = _item_labels(machine_action_items("local"))
        assert "Edit" in labels
        assert "Set as default" in labels
        assert "Rename" in labels
        assert "Templates" in labels
        assert "Projects" in labels
        assert "Remove" in labels

    def test_terminal_is_first_action_for_local_machine(self, tmp_config):
        from colette_cli.tui.screens import machine_action_items
        labels = _item_labels(machine_action_items("local"))
        assert labels[0] == "Terminal"

    def test_terminal_is_first_action_after_status_line_for_ssh_machine(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config({
            "machines": {"remote": {"type": "ssh", "host": "user@server", "projects_dir": "/projects"}},
            "default_machine": "remote",
        })
        from colette_cli.tui.screens import machine_action_items
        labels = _item_labels(machine_action_items("remote"))
        assert labels[0].startswith("Last synced")
        assert labels[1] == "Terminal"

    def test_terminal_calls_cmd_attach_with_correct_machine_name(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        with patch("colette_cli.project.cmd_attach") as mock_attach, \
             patch("curses.endwin"), patch("curses.doupdate"):
            items = machine_action_items("local")
            next(i for i in items if i.label == "Terminal").run()
        mock_attach.assert_called_once()
        assert mock_attach.call_args[0][0].name == "local"

    def test_terminal_system_exit_does_not_propagate(self, tmp_config):
        """Terminal is wrapped in _suspend, so an err()-raised SystemExit from
        the backend (e.g. unknown machine) must not crash the TUI."""
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        with patch("colette_cli.project.cmd_attach", side_effect=SystemExit(1)), \
             patch("curses.endwin"), patch("curses.doupdate"), patch("builtins.input"):
            items = machine_action_items("local")
            next(i for i in items if i.label == "Terminal").run()  # must not raise

    def test_templates_is_submenu(self, tmp_config):
        from colette_cli.tui.screens import machine_action_items
        templates = next(i for i in machine_action_items("local") if i.label == "Templates")
        assert not templates.is_leaf

    def test_projects_is_submenu(self, tmp_config):
        from colette_cli.tui.screens import machine_action_items
        projects = next(i for i in machine_action_items("local") if i.label == "Projects")
        assert not projects.is_leaf

    def test_edit_updates_machine_config(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        items = machine_action_items("local")
        with patch("colette_cli.tui.forms.form", return_value={
            "type": "local", "projects_dir": "/new/projects",
            "agent_command": "", "ide_command": "",
        }):
            next(i for i in items if i.label == "Edit").run()
        cfg = load_config()
        assert cfg["machines"]["local"]["projects_dir"] == "/new/projects"

    def test_edit_aborts_on_form_cancel(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        items = machine_action_items("local")
        with patch("colette_cli.tui.forms.form", return_value=None):
            next(i for i in items if i.label == "Edit").run()
        assert load_config()["machines"]["local"]["projects_dir"] == "/tmp/projects"

    def test_edit_machine_aborts_when_machine_missing(self, tmp_config):
        """edit action is a no-op when the machine no longer exists in config."""
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        items = machine_action_items("ghost")
        with patch("colette_cli.tui.forms.form") as mock_form:
            next(i for i in items if i.label == "Edit").run()
        mock_form.assert_not_called()

    def test_edit_ssh_fields_saved(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        save_config({
            "machines": {"remote": {"type": "ssh", "host": "old@host", "projects_dir": "/projects"}},
            "default_machine": "remote",
        })
        from colette_cli.tui.screens import machine_action_items
        items = machine_action_items("remote")
        with patch("colette_cli.tui.forms.form", return_value={
            "type": "ssh", "host": "new@host", "port": "24",
            "ssh_key": "/key/path", "colette_path": "/usr/local/bin/colette",
            "projects_dir": "/projects", "agent_command": "", "ide_command": "",
        }):
            next(i for i in items if i.label == "Edit").run()
        m = load_config()["machines"]["remote"]
        assert m["host"] == "new@host"
        assert m["port"] == 24
        assert m["ssh_key"] == "/key/path"
        assert m["colette_path"] == "/usr/local/bin/colette"

    def test_edit_switching_to_local_clears_ssh_fields(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        save_config({
            "machines": {"remote": {
                "type": "ssh", "host": "old@host", "port": 22,
                "ssh_key": "/key", "colette_path": "/bin/colette",
                "projects_dir": "/projects",
            }},
            "default_machine": "remote",
        })
        from colette_cli.tui.screens import machine_action_items
        items = machine_action_items("remote")
        with patch("colette_cli.tui.forms.form", return_value={
            "type": "local", "projects_dir": "/projects",
            "agent_command": "", "ide_command": "",
        }):
            next(i for i in items if i.label == "Edit").run()
        m = load_config()["machines"]["remote"]
        assert "host" not in m
        assert "port" not in m
        assert "ssh_key" not in m
        assert "colette_path" not in m

    def test_edit_folds_in_agent_and_ide_command(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        items = machine_action_items("local")
        with patch("colette_cli.tui.forms.form", return_value={
            "type": "local", "projects_dir": "/tmp/projects",
            "agent_command": "claude --resume", "ide_command": "code-insiders",
        }):
            next(i for i in items if i.label == "Edit").run()
        m = load_config()["machines"]["local"]
        assert m["agent_command"] == "claude --resume"
        assert m["ide_command"] == "code-insiders"

    def test_edit_clears_agent_and_ide_command_when_blank(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        cfg = dict(LOCAL_CFG["machines"]["local"])
        cfg["agent_command"] = "old --agent"
        cfg["ide_command"] = "old-ide"
        save_config({"machines": {"local": cfg}, "default_machine": "local"})
        from colette_cli.tui.screens import machine_action_items
        items = machine_action_items("local")
        with patch("colette_cli.tui.forms.form", return_value={
            "type": "local", "projects_dir": "/tmp/projects",
            "agent_command": "", "ide_command": "",
        }):
            next(i for i in items if i.label == "Edit").run()
        m = load_config()["machines"]["local"]
        assert "agent_command" not in m
        assert "ide_command" not in m

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

    def test_last_synced_shown_for_ssh_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, save_machine_cache
        save_config({
            "machines": {"remote": {"type": "ssh", "host": "user@server", "projects_dir": "/projects"}},
            "default_machine": "remote",
        })
        save_machine_cache("remote", {"synced_at": "2026-01-01T00:00:00Z", "projects": [], "templates": []})
        from colette_cli.tui.screens import machine_action_items
        labels = _item_labels(machine_action_items("remote"))
        assert "Last synced: 2026-01-01T00:00:00Z" in labels

    def test_last_synced_never_when_no_cache(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config({
            "machines": {"remote": {"type": "ssh", "host": "user@server", "projects_dir": "/projects"}},
            "default_machine": "remote",
        })
        from colette_cli.tui.screens import machine_action_items
        labels = _item_labels(machine_action_items("remote"))
        assert "Last synced: never" in labels

    def test_last_synced_not_shown_for_local_machine(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        labels = _item_labels(machine_action_items("local"))
        assert not any(l.startswith("Last synced") for l in labels)

    def test_sync_action_shown_only_for_ssh_machine(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config({
            "machines": {"remote": {"type": "ssh", "host": "user@server", "projects_dir": "/projects"}},
            "default_machine": "remote",
        })
        from colette_cli.tui.screens import machine_action_items
        labels = _item_labels(machine_action_items("remote"))
        assert "Sync" in labels

    def test_sync_not_shown_for_local_machine(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        labels = _item_labels(machine_action_items("local"))
        assert "Sync" not in labels

    def test_sync_calls_cmd_config_sync_with_machine_name(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config({
            "machines": {"remote": {"type": "ssh", "host": "user@server", "projects_dir": "/projects"}},
            "default_machine": "remote",
        })
        from colette_cli.tui.screens import machine_action_items
        with patch("colette_cli.config.cmd_config_sync") as mock_sync, \
             patch("threading.Thread", _SyncThread), \
             patch("colette_cli.utils.notify.send_notification"), \
             patch("colette_cli.tui.forms.show_running"):
            items = machine_action_items("remote")
            next(i for i in items if i.label == "Sync").run()
        mock_sync.assert_called_once()
        assert mock_sync.call_args[0][0].machine_name == "remote"

    def test_has_rename_action(self, tmp_config):
        from colette_cli.utils.config import save_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        labels = _item_labels(machine_action_items("local"))
        assert "Rename" in labels

    def test_rename_calls_cmd_config_rename_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        items = machine_action_items("local")
        rename = next(i for i in items if i.label == "Rename")
        with patch("colette_cli.tui.forms.ask", return_value="renamed"):
            rename.run()
        cfg = load_config()
        assert "renamed" in cfg["machines"]
        assert "local" not in cfg["machines"]

    def test_rename_aborts_on_empty(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        save_config(LOCAL_CFG)
        from colette_cli.tui.screens import machine_action_items
        items = machine_action_items("local")
        rename = next(i for i in items if i.label == "Rename")
        with patch("colette_cli.tui.forms.ask", return_value=None):
            rename.run()
        assert "local" in load_config()["machines"]


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

    def test_synced_templates_from_cache_appear(self, tmp_config):
        """Templates authored on a remote and pulled by `colette config sync`
        live only in the machine's read-only cache, never in its own
        config.json - the browse screen must still surface them."""
        from colette_cli.utils.config import save_config, save_machine_cache
        from colette_cli.tui.screens import machine_template_items
        cfg = {
            "machines": {
                "remote": {
                    "type": "ssh",
                    "host": "user@host",
                    "projects_dir": "/home/user/projects",
                    "colette_path": "/home/user/bin/colette",
                }
            },
            "default_machine": "remote",
        }
        save_config(cfg)
        save_machine_cache("remote", {
            "machine": "remote",
            "synced_at": "2026-01-01T00:00:00Z",
            "projects_dir": "/home/user/projects",
            "templates": [{"name": "synced-tmpl", "type": "directory", "path": "/tmp"}],
            "projects": [],
        })
        labels = _item_labels(machine_template_items("remote"))
        assert "synced-tmpl" in labels

    def test_add_template_saves_to_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.tui.screens import machine_template_items
        save_config(LOCAL_CFG)
        items = machine_template_items("local")
        with patch("colette_cli.tui.forms.form", return_value={
            "name": "newtmpl", "type": "directory", "source": "/tmpl/path", "description": "",
        }), patch("colette_cli.template.registry.scaffold_template_hook_files"):
            next(i for i in items if i.label == "Add template").run()
        cfg = load_config()
        tmpl_names = [t["name"] for t in cfg["machines"]["local"].get("templates", [])]
        assert "newtmpl" in tmpl_names

    def test_add_template_aborts_on_form_cancel(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.tui.screens import machine_template_items
        save_config(LOCAL_CFG)
        items = machine_template_items("local")
        with patch("colette_cli.tui.forms.form", return_value=None):
            next(i for i in items if i.label == "Add template").run()
        cfg = load_config()
        assert not cfg["machines"]["local"].get("templates")

    def test_add_template_with_git_type_uses_url(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.tui.screens import machine_template_items
        save_config(LOCAL_CFG)
        items = machine_template_items("local")
        with patch("colette_cli.tui.forms.form", return_value={
            "name": "gittmpl", "type": "git",
            "source": "https://github.com/org/tmpl.git", "description": "",
        }), patch("colette_cli.template.registry.scaffold_template_hook_files"):
            next(i for i in items if i.label == "Add template").run()
        cfg = load_config()
        tmpl = next(t for t in cfg["machines"]["local"]["templates"] if t["name"] == "gittmpl")
        assert tmpl["type"] == "git"
        assert tmpl["url"] == "https://github.com/org/tmpl.git"
        assert "path" not in tmpl

    def test_add_template_name_validator_rejects_duplicate(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import machine_template_items
        save_config(self.CFG_WITH_TMPL)
        items = machine_template_items("local")
        captured = {}

        def _fake_form(fields, title=""):
            captured["fields"] = fields
            return None

        with patch("colette_cli.tui.forms.form", side_effect=_fake_form):
            next(i for i in items if i.label == "Add template").run()
        name_field = next(f for f in captured["fields"] if f.name == "name")
        ok, _ = name_field.validator("my-tmpl")
        assert ok is False

    def test_add_template_name_validator_rejects_existing_machine_name(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import machine_template_items
        cfg = dict(self.CFG_WITH_TMPL)
        cfg["machines"] = dict(cfg["machines"])
        cfg["machines"]["other-machine"] = {"type": "local"}
        save_config(cfg)
        items = machine_template_items("local")
        captured = {}

        def _fake_form(fields, title=""):
            captured["fields"] = fields
            return None

        with patch("colette_cli.tui.forms.form", side_effect=_fake_form):
            next(i for i in items if i.label == "Add template").run()
        name_field = next(f for f in captured["fields"] if f.name == "name")
        ok, _ = name_field.validator("other-machine")
        assert ok is False

    def test_remove_template_removes_from_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.tui.screens import machine_template_items
        save_config(self.CFG_WITH_TMPL)
        items = machine_template_items("local")
        tmpl_item = next(i for i in items if i.label == "my-tmpl")
        children = tmpl_item.get_children()
        remove_item = next(i for i in children if i.label == "Remove")
        with patch("colette_cli.tui.forms.confirm", return_value=True):
            remove_item.run()
        cfg = load_config()
        tmpl_names = [t["name"] for t in cfg["machines"]["local"].get("templates", [])]
        assert "my-tmpl" not in tmpl_names


# ---------------------------------------------------------------------------
# machine_project_items
# ---------------------------------------------------------------------------

class TestMachineProjectItems:
    def test_lists_only_this_machines_projects(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.tui.screens import machine_project_items
        cfg = {
            "machines": {
                "local": make_local_machine("/tmp"),
                "other": make_local_machine("/other"),
            },
            "default_machine": "local",
        }
        save_config(cfg)
        save_local_projects([make_project("a", machine="local"), make_project("b", machine="other")])
        labels = _item_labels(machine_project_items("local"))
        assert "a" in labels
        assert "b" not in labels

    def test_no_projects_placeholder(self, tmp_config):
        from colette_cli.tui.screens import machine_project_items
        items = machine_project_items("local")
        assert items[0].label == "(no projects)"

    def test_project_items_are_full_action_submenus(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.tui.screens import machine_project_items
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj")])
        proj_item = next(i for i in machine_project_items("local") if i.label == "proj")
        assert not proj_item.is_leaf
        child_labels = _item_labels(proj_item.get_children())
        assert "Delete" in child_labels
        assert "Unlink" in child_labels

    def test_project_detail_shows_template(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.tui.screens import machine_project_items
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj", template="my-tmpl")])
        proj_item = next(i for i in machine_project_items("local") if i.label == "proj")
        assert proj_item.detail == "my-tmpl"


# ---------------------------------------------------------------------------
# main_menu_items
# ---------------------------------------------------------------------------

class TestMainMenuItems:
    def test_has_all_top_level_entries(self, tmp_config):
        from colette_cli.tui.screens import main_menu_items
        labels = _item_labels(main_menu_items())
        for label in ("Projects", "Machines", "Debug", "Monitor"):
            assert label in labels

    def test_monitor_is_submenu(self, tmp_config):
        from colette_cli.tui.screens import main_menu_items
        monitor = next(i for i in main_menu_items() if i.label == "Monitor")
        assert not monitor.is_leaf

    def test_monitor_submenu_has_three_modes(self, tmp_config):
        from colette_cli.tui.screens import main_menu_items
        monitor = next(i for i in main_menu_items() if i.label == "Monitor")
        sub_labels = _item_labels(monitor.get_children())
        assert sub_labels == ["Standard", "Agent", "All"]

    def test_projects_machines_debug_are_submenus(self, tmp_config):
        from colette_cli.tui.screens import main_menu_items
        items = main_menu_items()
        for label in ("Projects", "Machines", "Debug"):
            item = next(i for i in items if i.label == label)
            assert not item.is_leaf, f"{label} should be a submenu"

    def test_no_templates_or_config_top_level_entries(self, tmp_config):
        """Templates and Config were retired — Machines is now the single
        home for machine-scoped things (§1 of the TUI redesign plan)."""
        from colette_cli.tui.screens import main_menu_items
        labels = _item_labels(main_menu_items())
        assert "Templates" not in labels
        assert "Config" not in labels


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


# ---------------------------------------------------------------------------
# template_hook_items — machine-specific paths
# ---------------------------------------------------------------------------

class TestTemplateHookItemsMachineSpecific:
    CFG = {
        "machines": {
            "remote": {
                "type": "ssh",
                "host": "10.0.0.1",
                "projects_dir": "/projects",
                "templates": [{"name": "dev", "type": "directory", "path": "/tmpl"}],
            }
        },
        "default_machine": "remote",
    }

    def test_uses_machine_specific_paths(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import template_hook_items
        save_config(self.CFG)
        items = template_hook_items("dev", "remote")
        for item in items:
            assert "machines/remote/templates/dev" in item.detail

    def test_template_action_items_passes_machine_to_hooks(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import machine_template_action_items
        save_config(self.CFG)
        items = machine_template_action_items("remote", "dev")
        edit_hooks = next(i for i in items if i.label == "Edit hooks")
        hook_items = edit_hooks.get_children()
        for hi in hook_items:
            assert "machines/remote/templates/dev" in hi.detail

    def test_template_action_items_passes_machine_to_params(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import machine_template_action_items
        save_config(self.CFG)
        items = machine_template_action_items("remote", "dev")
        edit_params = next(i for i in items if i.label == "Edit parameters")
        # Just verify it resolves without error
        param_items = edit_params.get_children()
        assert any(i.label == "Add parameter" for i in param_items)


# ---------------------------------------------------------------------------
# template_param_items — machine-specific params
# ---------------------------------------------------------------------------

class TestTemplateParamItemsMachineSpecific:
    CFG = {
        "machines": {
            "remote": {
                "type": "ssh",
                "host": "10.0.0.1",
                "projects_dir": "/projects",
                "templates": [{"name": "dev", "type": "directory", "path": "/tmpl", "params": {"PORT": "8080"}}],
            }
        },
        "default_machine": "remote",
    }

    def test_reads_machine_params(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import template_param_items
        save_config(self.CFG)
        items = template_param_items("dev", "remote")
        labels = [i.label for i in items]
        assert "PORT" in labels

    def test_does_not_show_shared_params(self, tmp_config):
        """Machine-specific view does not show shared template params."""
        from colette_cli.utils.config import save_config
        from colette_cli.tui.screens import template_param_items
        save_config(self.CFG)
        items = template_param_items("dev", "remote")
        labels = [i.label for i in items]
        assert "SHARED" not in labels
        assert "PORT" in labels

    def test_saves_to_machine_config(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.tui.screens import template_param_items
        save_config(self.CFG)
        items = template_param_items("dev", "remote")
        port_item = next(i for i in items if i.label == "PORT")
        edit_item = next(i for i in port_item.get_children() if i.label == "Edit value")
        with patch("colette_cli.tui.forms.ask", return_value="9090"), \
             patch("colette_cli.utils.ssh.push_template_hooks"):
            edit_item.run()
        cfg = load_config()
        tmpl = next(t for t in cfg["machines"]["remote"]["templates"] if t["name"] == "dev")
        assert tmpl["params"]["PORT"] == "9090"

    def test_saves_new_param_to_machine_config(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.tui.screens import template_param_items
        cfg = {
            "machines": {
                "remote": {
                    "type": "ssh", "host": "10.0.0.1", "projects_dir": "/projects",
                    "templates": [{"name": "dev", "type": "directory", "path": "/tmpl"}],
                }
            },
            "default_machine": "remote",
        }
        save_config(cfg)
        items = template_param_items("dev", "remote")
        add_item = next(i for i in items if i.label == "Add parameter")
        with patch("colette_cli.tui.forms.ask", side_effect=["HOST", "myhost"]), \
             patch("colette_cli.utils.ssh.push_template_hooks"):
            add_item.run()
        cfg = load_config()
        tmpl = next(t for t in cfg["machines"]["remote"]["templates"] if t["name"] == "dev")
        assert tmpl["params"]["HOST"] == "myhost"


class TestAddTemplateProjectNameConflict:
    CFG_WITH_PROJECT = {
        "machines": {"local": {"type": "local", "projects_dir": "/tmp/projects", "templates": []}},
        "default_machine": "local",
    }

    def test_add_template_name_validator_rejects_existing_project_name(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.tui.screens import machine_template_items
        save_config(self.CFG_WITH_PROJECT)
        save_local_projects([{"name": "existing-project", "machine": "local", "path": "/tmp/existing-project"}])
        items = machine_template_items("local")
        captured = {}

        def _fake_form(fields, title=""):
            captured["fields"] = fields
            return None

        with patch("colette_cli.tui.forms.form", side_effect=_fake_form):
            next(i for i in items if i.label == "Add template").run()
        name_field = next(f for f in captured["fields"] if f.name == "name")
        ok, _ = name_field.validator("existing-project")
        assert ok is False


class TestCreateProjectTemplateNameConflict:
    def test_create_project_name_validator_rejects_existing_template_name(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        cfg = {
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": "/tmp/projects",
                    "templates": [{"name": "my-tmpl", "type": "directory", "path": "/tmp/my-tmpl"}],
                }
            },
            "default_machine": "local",
        }
        save_config(cfg)
        save_local_projects([])
        captured = {}

        def _fake_form(fields, title=""):
            captured["fields"] = fields
            return None

        with patch("colette_cli.project.cmd_create") as mock_create, \
             patch("colette_cli.tui.forms.form", side_effect=_fake_form):
            from colette_cli.tui.screens import project_list_items
            items = project_list_items()
            next(i for i in items if i.label == "Create project").run()
        mock_create.assert_not_called()
        name_field = next(f for f in captured["fields"] if f.name == "name")
        ok, _ = name_field.validator("my-tmpl")
        assert ok is False
