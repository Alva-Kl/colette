"""Tests for colette_cli.config.commands."""

import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import make_local_machine, make_project


LOCAL_CFG = {
    "machines": {"local": make_local_machine()},
    "default_machine": "local",
}


class TestParseParams:
    def _parse(self, raw):
        from colette_cli.config.commands import _parse_params
        return _parse_params(raw)

    def test_parses_key_value_pairs(self):
        result = self._parse(["ENV=dev", "PORT=8080"])
        assert result == {"ENV": "dev", "PORT": "8080"}

    def test_empty_list_returns_empty(self):
        assert self._parse([]) == {}

    def test_invalid_format_exits(self):
        with pytest.raises(SystemExit):
            self._parse(["NOEQUALS"])

    def test_strips_whitespace(self):
        result = self._parse([" KEY = val "])
        assert result == {"KEY": "val"}


class TestCmdConfigList:
    def test_no_machines_prints_message(self, tmp_config, capsys):
        from colette_cli.config.commands import cmd_config_list
        cmd_config_list(MagicMock())
        assert "No machines" in capsys.readouterr().out

    def test_lists_machines(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_list
        save_config(LOCAL_CFG)
        cmd_config_list(MagicMock())
        assert "local" in capsys.readouterr().out

    def test_shows_colette_path_for_ssh_machine(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_list
        cfg = {
            "machines": {
                "remote": {
                    "type": "ssh",
                    "host": "user@host",
                    "projects_dir": "/home/user/projects",
                    "colette_path": "/home/user/bin/colette",
                }
            }
        }
        save_config(cfg)
        cmd_config_list(MagicMock())
        out = capsys.readouterr().out
        assert "/home/user/bin/colette" in out

    def test_shows_not_set_when_colette_path_missing(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_list
        cfg = {
            "machines": {
                "remote": {
                    "type": "ssh",
                    "host": "user@host",
                    "projects_dir": "/home/user/projects",
                }
            }
        }
        save_config(cfg)
        cmd_config_list(MagicMock())
        assert "(not set)" in capsys.readouterr().out


class TestCmdConfigSetDefault:
    def test_sets_default_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_set_default
        save_config({
            "machines": {"a": {"type": "local"}, "b": {"type": "local"}},
            "default_machine": "a",
        })
        cmd_config_set_default(MagicMock(machine_name="b"))
        assert load_config()["default_machine"] == "b"

    def test_fails_on_unknown_machine(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_set_default
        save_config(LOCAL_CFG)
        with pytest.raises(SystemExit):
            cmd_config_set_default(MagicMock(machine_name="nope"))


class TestCmdConfigRemoveMachine:
    def test_removes_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_remove_machine
        save_config({
            "machines": {"a": {"type": "local"}, "b": {"type": "local"}},
            "default_machine": "a",
        })
        with patch("builtins.input", return_value="y"):
            cmd_config_remove_machine(MagicMock(machine_name="b"))
        assert "b" not in load_config()["machines"]

    def test_aborts_on_no(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_remove_machine
        save_config(LOCAL_CFG)
        with patch("builtins.input", return_value="n"):
            cmd_config_remove_machine(MagicMock(machine_name="local"))
        assert "local" in load_config()["machines"]

    def test_clears_default_when_removed(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_remove_machine
        save_config({"machines": {"a": {"type": "local"}}, "default_machine": "a"})
        with patch("builtins.input", return_value="y"):
            cmd_config_remove_machine(MagicMock(machine_name="a"))
        assert load_config().get("default_machine") is None

    def test_fails_on_unknown_machine(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_remove_machine
        save_config(LOCAL_CFG)
        with pytest.raises(SystemExit):
            cmd_config_remove_machine(MagicMock(machine_name="nope"))

    def test_keeps_other_machines_when_one_is_removed(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_remove_machine
        save_config({
            "machines": {
                "local": make_local_machine("/tmp"),
                "other": make_local_machine("/other"),
            },
            "default_machine": "local",
        })
        with patch("builtins.input", return_value="y"):
            cmd_config_remove_machine(MagicMock(machine_name="other"))
        cfg = load_config()
        assert "local" in cfg["machines"]
        assert "other" not in cfg["machines"]
        assert cfg["default_machine"] == "local"


class TestCmdConfigEditHook:
    def test_opens_nano_for_template_hook(self, tmp_config):
        from colette_cli.config.commands import cmd_config_edit_hook
        args = MagicMock(template_name="tmpl", hook_name="onstart")
        with patch("subprocess.run") as mock_run:
            cmd_config_edit_hook(args)
        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        assert cmd_args[0] == "nano"
        assert "onstart" in cmd_args[1] or ".onstart" in cmd_args[1]


class TestCmdConfigEditProjectHook:
    def test_opens_nano_for_project_hook(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.config.commands import cmd_config_edit_project_hook
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        args = MagicMock(project_name="proj", hook_name="onstart")
        with patch("subprocess.run") as mock_run:
            cmd_config_edit_project_hook(args)
        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        assert cmd_args[0] == "nano"

    def test_fails_when_project_not_registered(self, tmp_config):
        from colette_cli.config.commands import cmd_config_edit_project_hook
        args = MagicMock(project_name="ghost", hook_name="onstart")
        with pytest.raises(SystemExit):
            cmd_config_edit_project_hook(args)


class TestCmdConfigRemoveTemplate:
    def test_removes_template_from_machine(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_remove_template
        cfg = {
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": "/p",
                    "templates": [{"name": "t1", "type": "directory", "path": "/t"}],
                }
            },
            "default_machine": "local",
        }
        save_config(cfg)
        from colette_cli.utils.config import save_templates
        save_templates({"templates": [{"name": "t1"}]})
        args = MagicMock(machine_name="local", template_name="t1")
        cmd_config_remove_template(args)
        loaded = load_config()
        templates = loaded["machines"]["local"].get("templates", [])
        assert all(t["name"] != "t1" for t in templates)

    def test_fails_when_template_not_on_machine(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_remove_template
        save_config(LOCAL_CFG)
        with pytest.raises(SystemExit):
            cmd_config_remove_template(MagicMock(machine_name="local", template_name="nope"))


class TestCmdConfigDispatch:
    """cmd_config routing and no-subcommand behaviour."""

    def test_no_subcommand_calls_print_help(self, tmp_config):
        from colette_cli.config.commands import cmd_config
        mock_parser = MagicMock()
        args = MagicMock()
        args.config_cmd = None
        args.config_parser = mock_parser
        cmd_config(args)
        mock_parser.print_help.assert_called_once()

    def test_set_default_subcommand_dispatches(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config
        save_config(LOCAL_CFG)
        args = MagicMock()
        args.config_cmd = "set-default"
        args.machine_name = "local"
        cmd_config(args)
        from colette_cli.utils.config import load_config
        assert load_config()["default_machine"] == "local"


class TestCmdConfigRunTemplateUpdate:
    def test_runs_onupdate_for_template(self, tmp_config, tmp_path):
        """cmd_config_run_template_update executes the template onupdate hook."""
        from colette_cli.utils.config import save_config, write_machine_template_hook
        from colette_cli.config.commands import cmd_config_run_template_update
        marker = tmp_path / "marker.txt"
        write_machine_template_hook("local", "tmpl", "onupdate", f"#!/usr/bin/env bash\necho updated > {marker}")
        save_config({
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": str(tmp_path),
                    "templates": [{"name": "tmpl", "type": "directory", "path": str(tmp_path)}],
                }
            },
            "default_machine": "local",
        })
        args = MagicMock(template_name="tmpl", machine=None)
        cmd_config_run_template_update(args)
        assert marker.exists(), "onupdate hook did not run"
        assert marker.read_text().strip() == "updated"

    def test_fails_on_unknown_machine(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_run_template_update
        save_config(LOCAL_CFG)
        args = MagicMock(template_name="tmpl", machine="unknown")
        with pytest.raises(SystemExit):
            cmd_config_run_template_update(args)

    def test_dispatches_via_cmd_config(self, tmp_config, tmp_path):
        from colette_cli.config.commands import cmd_config
        with patch("colette_cli.config.commands.cmd_config_run_template_update") as mock_fn:
            args = MagicMock()
            args.config_cmd = "run-template-update"
            cmd_config(args)
        mock_fn.assert_called_once_with(args)

    def test_opens_machine_specific_hook_when_machine_flag_given(self, tmp_config):
        from colette_cli.config.commands import cmd_config_edit_hook
        args = MagicMock(template_name="tmpl", hook_name="onstart", machine="remote")
        with patch("subprocess.run") as mock_run:
            cmd_config_edit_hook(args)
        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        assert cmd_args[0] == "nano"
        assert "machines/remote/templates/tmpl" in cmd_args[1]

    def test_uses_default_machine_when_no_machine_flag(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_edit_hook
        save_config(LOCAL_CFG)
        args = MagicMock(template_name="tmpl", hook_name="onstart", machine=None)
        with patch("subprocess.run") as mock_run:
            cmd_config_edit_hook(args)
        cmd_args = mock_run.call_args[0][0]
        assert "machines/local/templates/tmpl" in cmd_args[1]


class TestCmdConfigSyncRemote:
    _REMOTE_CFG = {
        "machines": {
            "myremote": {
                "type": "ssh",
                "host": "user@remotehost",
                "colette_path": "/home/user/scripts/colette",
                "projects_dir": "/home/user/projects",
            }
        },
        "default_machine": "myremote",
    }

    def test_prints_synced_on_success(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_sync_remote
        save_config(self._REMOTE_CFG)
        args = MagicMock(machine_name=None)
        with patch("colette_cli.utils.ssh.sync_remote_colette", return_value=True):
            cmd_config_sync_remote(args)
        out = capsys.readouterr().out
        assert "synced" in out and "myremote" in out

    def test_prints_up_to_date_when_not_synced(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_sync_remote
        save_config(self._REMOTE_CFG)
        args = MagicMock(machine_name=None)
        with patch("colette_cli.utils.ssh.sync_remote_colette", return_value=False):
            cmd_config_sync_remote(args)
        out = capsys.readouterr().out
        assert "up to date" in out

    def test_silent_when_sync_returns_none(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_sync_remote
        save_config(self._REMOTE_CFG)
        args = MagicMock(machine_name=None)
        with patch("colette_cli.utils.ssh.sync_remote_colette", return_value=None):
            cmd_config_sync_remote(args)
        out = capsys.readouterr().out
        assert "synced" not in out and "up to date" not in out

    def test_skips_machine_with_no_colette_path(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_sync_remote
        cfg = {
            "machines": {
                "myremote": {
                    "type": "ssh",
                    "host": "user@remotehost",
                    "projects_dir": "/home/user/projects",
                }
            }
        }
        save_config(cfg)
        args = MagicMock(machine_name=None)
        with patch("colette_cli.utils.ssh.sync_remote_colette") as mock_sync:
            cmd_config_sync_remote(args)
        mock_sync.assert_not_called()
        assert "no colette_path set" in capsys.readouterr().out

    def test_exits_when_named_machine_not_found(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_sync_remote
        save_config(self._REMOTE_CFG)
        args = MagicMock(machine_name="ghost")
        with pytest.raises(SystemExit):
            cmd_config_sync_remote(args)

    def test_injects_project_config_for_each_project(self, tmp_config, capsys):
        """sync-remote must call inject_project_config for each project on the machine."""
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.config.commands import cmd_config_sync_remote
        save_config(self._REMOTE_CFG)
        save_projects([
            make_project("proj-a", machine="myremote"),
            make_project("proj-b", machine="myremote"),
        ])
        args = MagicMock(machine_name=None)
        with patch("colette_cli.utils.ssh.sync_remote_colette", return_value=True), \
             patch("colette_cli.utils.ssh.inject_project_config") as mock_inject:
            cmd_config_sync_remote(args)
        assert mock_inject.call_count == 2
        injected_names = {c[0][2]["name"] for c in mock_inject.call_args_list}
        assert injected_names == {"proj-a", "proj-b"}

    def test_does_not_inject_when_sync_fails(self, tmp_config):
        """inject_project_config must not be called if sync_remote_colette returns None."""
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.config.commands import cmd_config_sync_remote
        save_config(self._REMOTE_CFG)
        save_projects([make_project("proj-a", machine="myremote")])
        args = MagicMock(machine_name=None)
        with patch("colette_cli.utils.ssh.sync_remote_colette", return_value=None), \
             patch("colette_cli.utils.ssh.inject_project_config") as mock_inject:
            cmd_config_sync_remote(args)
        mock_inject.assert_not_called()


class TestCmdConfigAddTemplateProjectNameConflict:
    def test_errors_when_template_name_is_existing_project(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.config.commands import cmd_config_add_template
        save_config({
            "machines": {"local": {"type": "local", "templates": []}},
            "default_machine": "local",
        })
        save_projects([{"name": "my-project", "machine": "local", "path": "/tmp/my-project"}])
        args = MagicMock()
        args.machine_name = "local"
        args.template_name = "my-project"
        args.params = []
        with pytest.raises(SystemExit):
            cmd_config_add_template(args)


class TestCmdConfigRenameTemplateProjectNameConflict:
    def test_errors_when_new_name_is_existing_project(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.config.commands import cmd_config_rename_template
        save_config({
            "machines": {
                "local": {
                    "type": "local",
                    "templates": [{"name": "old-tmpl", "type": "directory", "path": "/tmp/old"}],
                }
            },
            "default_machine": "local",
        })
        save_projects([{"name": "existing-project", "machine": "local", "path": "/tmp/existing-project"}])
        args = MagicMock()
        args.machine_name = "local"
        args.old_name = "old-tmpl"
        args.new_name = "existing-project"
        with pytest.raises(SystemExit):
            cmd_config_rename_template(args)
