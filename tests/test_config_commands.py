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
