"""Tests for colette_cli.config.commands."""

import pytest
from pathlib import Path
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

    def test_shows_synced_templates_from_cache(self, tmp_config, capsys):
        """A machine's own config.json never carries synced templates - they
        only ever land in its read-only sync cache. The summary line must
        still surface them, not just locally-authored ones."""
        from colette_cli.utils.config import save_config, save_machine_cache
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
        save_machine_cache("remote", {
            "machine": "remote",
            "synced_at": "2026-01-01T00:00:00Z",
            "projects_dir": "/home/user/projects",
            "templates": [{"name": "synced-tmpl", "type": "directory", "path": "/tmp"}],
            "projects": [],
        })
        cmd_config_list(MagicMock())
        assert "synced-tmpl" in capsys.readouterr().out


class TestCmdConfigAddMachine:
    def test_empty_name_exits(self, tmp_config):
        from colette_cli.config.commands import cmd_config_add_machine
        with patch("builtins.input", side_effect=[""]):
            with pytest.raises(SystemExit):
                cmd_config_add_machine(MagicMock())

    def test_duplicate_name_exits(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_add_machine
        save_config(LOCAL_CFG)
        with patch("builtins.input", side_effect=["local"]):
            with pytest.raises(SystemExit):
                cmd_config_add_machine(MagicMock())

    def test_invalid_type_exits(self, tmp_config):
        from colette_cli.config.commands import cmd_config_add_machine
        with patch("builtins.input", side_effect=["newmachine", "docker"]):
            with pytest.raises(SystemExit):
                cmd_config_add_machine(MagicMock())

    def test_empty_ssh_host_exits(self, tmp_config):
        from colette_cli.config.commands import cmd_config_add_machine
        with patch("builtins.input", side_effect=["newmachine", "ssh", ""]):
            with pytest.raises(SystemExit):
                cmd_config_add_machine(MagicMock())

    def test_non_digit_port_exits(self, tmp_config):
        from colette_cli.config.commands import cmd_config_add_machine
        with patch("builtins.input", side_effect=["newmachine", "ssh", "user@host", "notanumber"]):
            with pytest.raises(SystemExit):
                cmd_config_add_machine(MagicMock())

    def test_empty_projects_dir_exits(self, tmp_config):
        from colette_cli.config.commands import cmd_config_add_machine
        with patch("builtins.input", side_effect=["newmachine", "local", "", ""]):
            with pytest.raises(SystemExit):
                cmd_config_add_machine(MagicMock())

    def test_creates_local_machine_and_becomes_default(self, tmp_config):
        from colette_cli.utils.config import load_config
        from colette_cli.config.commands import cmd_config_add_machine
        with patch("builtins.input", side_effect=[
            "newmachine", "local", "", "/home/user/projects",
        ]):
            cmd_config_add_machine(MagicMock())
        cfg = load_config()
        assert cfg["machines"]["newmachine"]["type"] == "local"
        assert cfg["machines"]["newmachine"]["projects_dir"] == "/home/user/projects"
        assert cfg["default_machine"] == "newmachine"

    def test_creates_ssh_machine_with_all_fields(self, tmp_config):
        from colette_cli.utils.config import load_config
        from colette_cli.config.commands import cmd_config_add_machine
        with patch("builtins.input", side_effect=[
            "newmachine", "ssh", "user@host", "2222", "/home/user/.ssh/id_ed25519",
            "/home/user/.local/bin/colette", "", "/home/user/projects",
        ]):
            cmd_config_add_machine(MagicMock())
        cfg = load_config()
        machine = cfg["machines"]["newmachine"]
        assert machine["type"] == "ssh"
        assert machine["host"] == "user@host"
        assert machine["port"] == 2222
        assert machine["ssh_key"].endswith("id_ed25519")
        assert machine["colette_path"] == "/home/user/.local/bin/colette"

    def test_declines_setting_as_default_when_one_already_exists(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_add_machine
        save_config(LOCAL_CFG)
        with patch("builtins.input", side_effect=[
            "newmachine", "local", "", "/home/user/projects", "n",
        ]):
            cmd_config_add_machine(MagicMock())
        assert load_config()["default_machine"] == "local"

    def test_accepts_setting_as_default_when_one_already_exists(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_add_machine
        save_config(LOCAL_CFG)
        with patch("builtins.input", side_effect=[
            "newmachine", "local", "", "/home/user/projects", "y",
        ]):
            cmd_config_add_machine(MagicMock())
        assert load_config()["default_machine"] == "newmachine"

    def test_optional_template_scaffolds_hooks(self, tmp_config):
        from colette_cli.utils.config import load_config, machine_template_hook_exists
        from colette_cli.config.commands import cmd_config_add_machine
        with patch("builtins.input", side_effect=[
            "newmachine", "local", "mytmpl", "directory", "/tmpl/path", "/home/user/projects",
        ]):
            cmd_config_add_machine(MagicMock())
        cfg = load_config()
        tmpl = cfg["machines"]["newmachine"]["templates"][0]
        assert tmpl == {"name": "mytmpl", "type": "directory", "path": "/tmpl/path"}
        assert machine_template_hook_exists("newmachine", "mytmpl", "oncreate")


class TestCmdConfigEditMachine:
    def test_missing_machine_exits(self, tmp_config):
        from colette_cli.config.commands import cmd_config_edit_machine
        args = MagicMock(machine_name="nope")
        with pytest.raises(SystemExit):
            cmd_config_edit_machine(args)

    def test_toggle_local_to_ssh(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_edit_machine
        save_config(LOCAL_CFG)
        args = MagicMock(machine_name="local")
        with patch("builtins.input", side_effect=[
            "ssh", "user@newhost", "", "", "", "", "", "",
        ]):
            cmd_config_edit_machine(args)
        machine = load_config()["machines"]["local"]
        assert machine["type"] == "ssh"
        assert machine["host"] == "user@newhost"

    def test_toggle_ssh_to_local_clears_ssh_fields(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_edit_machine
        save_config({
            "machines": {
                "remote": {
                    "type": "ssh", "host": "user@host", "ssh_key": "/k",
                    "colette_path": "/c", "projects_dir": "/p",
                }
            },
            "default_machine": "remote",
        })
        args = MagicMock(machine_name="remote")
        with patch("builtins.input", side_effect=["local", "", "", ""]):
            cmd_config_edit_machine(args)
        machine = load_config()["machines"]["remote"]
        assert machine["type"] == "local"
        assert "host" not in machine
        assert "ssh_key" not in machine
        assert "colette_path" not in machine

    def test_port_revalidation_rejects_non_digit(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_edit_machine
        save_config({
            "machines": {"remote": {"type": "ssh", "host": "h", "projects_dir": "/p"}},
            "default_machine": "remote",
        })
        args = MagicMock(machine_name="remote")
        with patch("builtins.input", side_effect=["ssh", "", "notanumber"]):
            with pytest.raises(SystemExit):
                cmd_config_edit_machine(args)

    def test_keeps_existing_port_when_left_blank(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_edit_machine
        save_config({
            "machines": {"remote": {"type": "ssh", "host": "h", "port": 2222, "projects_dir": "/p"}},
            "default_machine": "remote",
        })
        args = MagicMock(machine_name="remote")
        with patch("builtins.input", side_effect=["ssh", "", "", "", "", "", "", ""]):
            cmd_config_edit_machine(args)
        assert load_config()["machines"]["remote"]["port"] == 2222

    def test_agent_and_ide_command_overrides(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_edit_machine
        save_config(LOCAL_CFG)
        args = MagicMock(machine_name="local")
        with patch("builtins.input", side_effect=[
            "local", "/home/user/projects", "claude --resume", "zed --wait",
        ]):
            cmd_config_edit_machine(args)
        machine = load_config()["machines"]["local"]
        assert machine["agent_command"] == "claude --resume"
        assert machine["ide_command"] == "zed --wait"


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


class TestCmdConfigRenameMachine:
    def test_renames_machine_key(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_rename_machine
        save_config({"machines": {"old": make_local_machine("/p")}, "default_machine": "old"})
        cmd_config_rename_machine(MagicMock(old_name="old", new_name="new"))
        cfg = load_config()
        assert "old" not in cfg["machines"]
        assert "new" in cfg["machines"]

    def test_updates_default_machine_pointer(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_rename_machine
        save_config({"machines": {"old": make_local_machine("/p")}, "default_machine": "old"})
        cmd_config_rename_machine(MagicMock(old_name="old", new_name="new"))
        assert load_config()["default_machine"] == "new"

    def test_does_not_touch_default_when_pointing_elsewhere(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_rename_machine
        save_config({
            "machines": {"old": make_local_machine("/p"), "other": make_local_machine("/q")},
            "default_machine": "other",
        })
        cmd_config_rename_machine(MagicMock(old_name="old", new_name="new"))
        assert load_config()["default_machine"] == "other"

    def test_fails_on_unknown_machine(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_rename_machine
        save_config(LOCAL_CFG)
        with pytest.raises(SystemExit):
            cmd_config_rename_machine(MagicMock(old_name="nope", new_name="new"))

    def test_fails_when_new_name_already_exists(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_rename_machine
        save_config({
            "machines": {"a": make_local_machine("/p"), "b": make_local_machine("/q")},
            "default_machine": "a",
        })
        with pytest.raises(SystemExit):
            cmd_config_rename_machine(MagicMock(old_name="a", new_name="b"))

    def test_renames_template_hooks_directory(self, tmp_config):
        from colette_cli.utils.config import (
            save_config, write_machine_template_hook, machine_template_hook_exists,
        )
        from colette_cli.config.commands import cmd_config_rename_machine
        write_machine_template_hook("old", "tmpl", "oncreate", "#!/usr/bin/env bash\necho hi")
        save_config({"machines": {"old": make_local_machine("/p")}, "default_machine": "old"})
        cmd_config_rename_machine(MagicMock(old_name="old", new_name="new"))
        assert machine_template_hook_exists("new", "tmpl", "oncreate")
        assert not machine_template_hook_exists("old", "tmpl", "oncreate")

    def test_renames_remote_cache_file(self, tmp_config):
        from colette_cli.utils.config import save_config, save_machine_cache, load_machine_cache
        from colette_cli.config.commands import cmd_config_rename_machine
        save_config({
            "machines": {"old": {"type": "ssh", "host": "user@host"}},
            "default_machine": "old",
        })
        save_machine_cache("old", {"machine": "old", "synced_at": "x", "projects_dir": "", "templates": [], "projects": []})
        cmd_config_rename_machine(MagicMock(old_name="old", new_name="new"))
        assert load_machine_cache("new") is not None
        assert load_machine_cache("old") is None

    def test_updates_local_project_machine_field(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects, load_projects
        from colette_cli.config.commands import cmd_config_rename_machine
        save_config({"machines": {"old": make_local_machine("/p")}, "default_machine": "old"})
        save_local_projects([make_project("proj", machine="old", path="/p/proj")])
        cmd_config_rename_machine(MagicMock(old_name="old", new_name="new"))
        projects = load_projects()
        assert projects[0]["machine"] == "new"

    def test_does_not_touch_unrelated_project(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects, load_projects
        from colette_cli.config.commands import cmd_config_rename_machine
        save_config({
            "machines": {"old": make_local_machine("/p"), "other": make_local_machine("/q")},
            "default_machine": "old",
        })
        save_local_projects([make_project("proj", machine="other", path="/q/proj")])
        cmd_config_rename_machine(MagicMock(old_name="old", new_name="new"))
        projects = load_projects()
        assert projects[0]["machine"] == "other"


class TestApplyAddTemplate:
    def test_creates_directory_template(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config, machine_template_hook_exists
        from colette_cli.config.commands import apply_add_template
        save_config(LOCAL_CFG)
        cfg = load_config()
        apply_add_template(cfg, "local", "newtmpl", "directory", "/tmpl/path", "A description", {"KEY": "val"})
        entry = load_config()["machines"]["local"]["templates"][0]
        assert entry == {
            "name": "newtmpl", "type": "directory", "path": "/tmpl/path",
            "description": "A description", "params": {"KEY": "val"},
        }
        assert machine_template_hook_exists("local", "newtmpl", "oncreate")

    def test_rejects_duplicate_name(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import apply_add_template
        save_config({
            "machines": {"local": {
                "type": "local", "projects_dir": "/p",
                "templates": [{"name": "existing", "type": "directory", "path": "/p"}],
            }},
            "default_machine": "local",
        })
        cfg = load_config()
        with pytest.raises(SystemExit):
            apply_add_template(cfg, "local", "existing", "directory", "/p")

    def test_pushes_to_remote(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import apply_add_template
        save_config({
            "machines": {"remote": {"type": "ssh", "host": "user@host", "projects_dir": "/home/user"}},
            "default_machine": "remote",
        })
        cfg = load_config()
        with patch("colette_cli.utils.ssh.push_template_hooks") as mock_push:
            apply_add_template(cfg, "remote", "tmpl", "directory", "/tmpl/path")
        mock_push.assert_called_once()


class TestApplyEditTemplate:
    def test_edits_source_and_description(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import apply_edit_template
        save_config({
            "machines": {"local": {
                "type": "local", "projects_dir": "/p",
                "templates": [{"name": "tmpl", "type": "directory", "path": "/old/path"}],
            }},
            "default_machine": "local",
        })
        cfg = load_config()
        apply_edit_template(cfg, "local", "tmpl", "directory", "/new/path", "New desc")
        entry = load_config()["machines"]["local"]["templates"][0]
        assert entry["path"] == "/new/path"
        assert entry["description"] == "New desc"

    def test_missing_template_exits(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import apply_edit_template
        save_config(LOCAL_CFG)
        cfg = load_config()
        with pytest.raises(SystemExit):
            apply_edit_template(cfg, "local", "nope", "directory", "/p")

    def test_pushes_to_remote(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import apply_edit_template
        save_config({
            "machines": {"remote": {
                "type": "ssh", "host": "user@host", "projects_dir": "/home/user",
                "templates": [{"name": "tmpl", "type": "directory", "path": "/old"}],
            }},
            "default_machine": "remote",
        })
        cfg = load_config()
        with patch("colette_cli.utils.ssh.push_template_hooks") as mock_push:
            apply_edit_template(cfg, "remote", "tmpl", "directory", "/new")
        mock_push.assert_called_once()


class TestCmdConfigSetTemplateParams:
    def test_sets_params(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_set_template_params
        save_config({
            "machines": {"local": {
                "type": "local", "projects_dir": "/p",
                "templates": [{"name": "tmpl", "type": "directory", "path": "/p"}],
            }},
            "default_machine": "local",
        })
        cfg = load_config()
        cmd_config_set_template_params(cfg, "local", "tmpl", {"PORT": "8080"})
        entry = load_config()["machines"]["local"]["templates"][0]
        assert entry["params"] == {"PORT": "8080"}

    def test_removes_params_when_empty(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_set_template_params
        save_config({
            "machines": {"local": {
                "type": "local", "projects_dir": "/p",
                "templates": [{"name": "tmpl", "type": "directory", "path": "/p", "params": {"K": "v"}}],
            }},
            "default_machine": "local",
        })
        cfg = load_config()
        cmd_config_set_template_params(cfg, "local", "tmpl", {})
        entry = load_config()["machines"]["local"]["templates"][0]
        assert "params" not in entry

    def test_pushes_to_remote(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_set_template_params
        save_config({
            "machines": {"remote": {
                "type": "ssh", "host": "user@host", "projects_dir": "/home/user",
                "templates": [{"name": "tmpl", "type": "directory", "path": "/p"}],
            }},
            "default_machine": "remote",
        })
        cfg = load_config()
        with patch("colette_cli.utils.ssh.push_template_hooks") as mock_push:
            cmd_config_set_template_params(cfg, "remote", "tmpl", {"K": "v"})
        mock_push.assert_called_once()

    def test_fails_on_missing_template(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_set_template_params
        save_config(LOCAL_CFG)
        cfg = load_config()
        with pytest.raises(SystemExit):
            cmd_config_set_template_params(cfg, "local", "nope", {})


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
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.config.commands import cmd_config_edit_project_hook
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj")])
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


class TestCmdConfigListTemplates:
    def test_shows_local_template_with_hooks_dir(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_list_templates
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
        cmd_config_list_templates(MagicMock(machine_name="local"))
        out = capsys.readouterr().out
        assert "t1" in out
        assert "hooks_dir:" in out

    def test_shows_synced_only_template_without_hooks_dir(self, tmp_config, capsys):
        """A template that only exists in the sync cache (authored on the
        remote, never locally configured) must still show up here, but
        without hooks_dir/hook files/params lines that only apply to
        locally-owned templates."""
        from colette_cli.utils.config import save_config, save_machine_cache
        from colette_cli.config.commands import cmd_config_list_templates
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
        cmd_config_list_templates(MagicMock(machine_name="remote"))
        out = capsys.readouterr().out
        assert "synced-tmpl" in out
        assert "not locally editable" in out
        assert "hooks_dir:" not in out


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

    def test_resolves_template_path_for_cache_only_template(self, tmp_config, tmp_path):
        """Regression: a template known only through the sync cache (never
        explicitly configured on this machine) must still resolve a real
        template_path — previously used get_machine_template (config-only),
        which silently dropped the path for cache-only templates."""
        from colette_cli.utils.config import save_config, save_machine_cache, write_machine_template_hook
        from colette_cli.config.commands import cmd_config_run_template_update

        marker = tmp_path / "marker.txt"
        write_machine_template_hook("remote", "cached-tmpl", "onupdate", f"#!/usr/bin/env bash\necho \"path=$COLETTE_TEMPLATE_PATH\" > {marker}")
        save_config({
            "machines": {
                "remote": {"type": "ssh", "host": "user@remote", "projects_dir": "/home/user"},
            },
            "default_machine": "remote",
        })
        cached_path = tmp_path / "cached-tmpl-source"
        cached_path.mkdir()
        save_machine_cache("remote", {
            "machine": "remote", "synced_at": "x", "projects_dir": "/home/user",
            "templates": [{"name": "cached-tmpl", "type": "directory", "path": str(cached_path)}],
            "projects": [],
        })

        args = MagicMock(template_name="cached-tmpl", machine="remote")
        with patch("colette_cli.utils.helpers.is_remote_machine", return_value=False):
            cmd_config_run_template_update(args)

        assert marker.exists(), "onupdate hook did not run"
        assert marker.read_text().strip() == f"path={cached_path}"

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


class TestCmdConfigSync:
    _REMOTE_CFG = {
        "machines": {
            "myremote": {
                "type": "ssh",
                "host": "user@remotehost",
                "colette_path": "/home/user/scripts/colette",
            }
        },
        "default_machine": "myremote",
    }

    _REPORT = {
        "machine": {"projects_dir": "/home/user/projects", "templates": [{"name": "tmpl"}]},
        "projects": [{"name": "proj-a", "machine": "local", "path": "/home/user/projects/proj-a", "template": None}],
    }

    def test_skips_machine_with_no_colette_path(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_sync
        cfg = {
            "machines": {
                "myremote": {
                    "type": "ssh",
                    "host": "user@remotehost",
                }
            }
        }
        save_config(cfg)
        args = MagicMock(machine_name=None)
        with patch("colette_cli.utils.ssh.fetch_self_report") as mock_report:
            cmd_config_sync(args)
        mock_report.assert_not_called()
        captured = capsys.readouterr()
        assert "no colette_path set" in captured.err
        assert "skipped (no colette_path set): myremote" in captured.err

    def test_exits_when_named_machine_not_found(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_sync
        save_config(self._REMOTE_CFG)
        args = MagicMock(machine_name="ghost")
        with pytest.raises(SystemExit):
            cmd_config_sync(args)

    def test_no_remote_machines_prints_message(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_sync
        save_config({"machines": {"local": make_local_machine()}, "default_machine": "local"})
        args = MagicMock(machine_name=None)
        cmd_config_sync(args)
        assert "No remote machines configured" in capsys.readouterr().out

    def test_caches_fetched_projects_and_templates(self, tmp_config):
        """sync writes a read-only cache from the remote's self-report, and
        never pushes anything back."""
        from colette_cli.utils.config import save_config, load_machine_cache
        from colette_cli.config.commands import cmd_config_sync
        save_config(self._REMOTE_CFG)
        args = MagicMock(machine_name=None)
        with patch("colette_cli.utils.ssh.fetch_self_report", return_value=self._REPORT) as mock_report:
            cmd_config_sync(args)

        mock_report.assert_called_once()
        cache = load_machine_cache("myremote")
        assert cache["projects"] == self._REPORT["projects"]
        assert cache["templates"] == self._REPORT["machine"]["templates"]
        assert cache["projects_dir"] == "/home/user/projects"
        assert "synced_at" in cache

    def test_warns_when_self_report_fails(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config, load_machine_cache
        from colette_cli.config.commands import cmd_config_sync
        save_config(self._REMOTE_CFG)
        args = MagicMock(machine_name=None)
        with patch("colette_cli.utils.ssh.fetch_self_report", return_value=None):
            with pytest.raises(SystemExit):
                cmd_config_sync(args)
        assert load_machine_cache("myremote") is None
        assert "failed to fetch project/template data" in capsys.readouterr().err

    def test_exits_after_processing_all_machines_when_one_fails(self, tmp_config):
        """A failed pull on one machine shouldn't stop other machines from
        being synced and cached first — the overall failure is reported last."""
        from colette_cli.utils.config import save_config, load_machine_cache
        from colette_cli.config.commands import cmd_config_sync

        cfg = {
            "machines": {
                "good": {"type": "ssh", "host": "user@good", "colette_path": "/bin/colette"},
                "bad": {"type": "ssh", "host": "user@bad", "colette_path": "/bin/colette"},
            }
        }
        save_config(cfg)
        args = MagicMock(machine_name=None)

        def fake_fetch(machine, name):
            return self._REPORT if name == "good" else None

        with patch("colette_cli.utils.ssh.fetch_self_report", side_effect=fake_fetch):
            with pytest.raises(SystemExit):
                cmd_config_sync(args)

        assert load_machine_cache("good")["projects"] == self._REPORT["projects"]
        assert load_machine_cache("bad") is None


class TestCmdConfigAddTemplate:
    def test_creates_directory_template_with_description_and_params(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config, machine_template_hook_exists
        from colette_cli.config.commands import cmd_config_add_template
        save_config(LOCAL_CFG)
        args = MagicMock(machine_name="local", template_name="newtmpl", params=["KEY=val"])
        with patch("builtins.input", side_effect=["directory", "/tmpl/path", "A nice template"]):
            cmd_config_add_template(args)
        cfg = load_config()
        entry = cfg["machines"]["local"]["templates"][0]
        assert entry == {
            "name": "newtmpl", "type": "directory", "path": "/tmpl/path",
            "description": "A nice template", "params": {"KEY": "val"},
        }
        assert machine_template_hook_exists("local", "newtmpl", "oncreate")

    def test_creates_git_template(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_add_template
        save_config(LOCAL_CFG)
        args = MagicMock(machine_name="local", template_name="gittmpl", params=[])
        with patch("builtins.input", side_effect=["git", "https://github.com/org/tmpl.git", ""]):
            cmd_config_add_template(args)
        entry = load_config()["machines"]["local"]["templates"][0]
        assert entry["type"] == "git"
        assert entry["url"] == "https://github.com/org/tmpl.git"

    def test_pushes_to_remote_machine(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_add_template
        save_config({
            "machines": {"remote": {"type": "ssh", "host": "user@host", "projects_dir": "/home/user"}},
            "default_machine": "remote",
        })
        args = MagicMock(machine_name="remote", template_name="newtmpl", params=[])
        with patch("builtins.input", side_effect=["directory", "/tmpl/path", ""]), \
             patch("colette_cli.utils.ssh.push_template_hooks") as mock_push:
            cmd_config_add_template(args)
        mock_push.assert_called_once()
        assert mock_push.call_args[0][1] == "remote"
        assert mock_push.call_args[0][2] == "newtmpl"

    def test_rejects_duplicate_name(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_add_template
        save_config({
            "machines": {"local": {
                "type": "local", "projects_dir": "/p",
                "templates": [{"name": "existing", "type": "directory", "path": "/p"}],
            }},
            "default_machine": "local",
        })
        args = MagicMock(machine_name="local", template_name="existing", params=[])
        with pytest.raises(SystemExit):
            cmd_config_add_template(args)


class TestCmdConfigEditTemplate:
    def test_edits_source_description_and_params(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_edit_template
        save_config({
            "machines": {"local": {
                "type": "local", "projects_dir": "/p",
                "templates": [{"name": "tmpl", "type": "directory", "path": "/old/path"}],
            }},
            "default_machine": "local",
        })
        args = MagicMock(machine_name="local", template_name="tmpl", params=None)
        with patch("builtins.input", side_effect=["directory", "/new/path", "New description"]):
            cmd_config_edit_template(args)
        entry = load_config()["machines"]["local"]["templates"][0]
        assert entry["path"] == "/new/path"
        assert entry["description"] == "New description"

    def test_switching_to_git_drops_path_field(self, tmp_config):
        from colette_cli.utils.config import save_config, load_config
        from colette_cli.config.commands import cmd_config_edit_template
        save_config({
            "machines": {"local": {
                "type": "local", "projects_dir": "/p",
                "templates": [{"name": "tmpl", "type": "directory", "path": "/old/path"}],
            }},
            "default_machine": "local",
        })
        args = MagicMock(machine_name="local", template_name="tmpl", params=None)
        with patch("builtins.input", side_effect=["git", "https://example.com/repo.git", ""]):
            cmd_config_edit_template(args)
        entry = load_config()["machines"]["local"]["templates"][0]
        assert entry["type"] == "git"
        assert entry["url"] == "https://example.com/repo.git"
        assert "path" not in entry

    def test_missing_template_exits(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_edit_template
        save_config(LOCAL_CFG)
        args = MagicMock(machine_name="local", template_name="nope", params=None)
        with pytest.raises(SystemExit):
            cmd_config_edit_template(args)


class TestCmdConfigRenameTemplateRealPath:
    def test_renames_hook_dir_and_updates_linked_projects(self, tmp_config):
        from colette_cli.utils.config import (
            save_config, save_local_projects, load_config, load_projects,
            write_machine_template_hook, machine_template_hook_exists,
        )
        from colette_cli.config.commands import cmd_config_rename_template
        write_machine_template_hook("local", "old-tmpl", "oncreate", "#!/usr/bin/env bash\necho hi")
        save_config({
            "machines": {"local": {
                "type": "local", "projects_dir": "/p",
                "templates": [{"name": "old-tmpl", "type": "directory", "path": "/p"}],
            }},
            "default_machine": "local",
        })
        save_local_projects([
            {"name": "proj-a", "machine": "local", "path": "/p/proj-a", "template": "old-tmpl"},
            {"name": "proj-b", "machine": "local", "path": "/p/proj-b", "template": "other-tmpl"},
        ])
        args = MagicMock(machine_name="local", old_name="old-tmpl", new_name="new-tmpl")
        cmd_config_rename_template(args)

        cfg = load_config()
        names = [t["name"] for t in cfg["machines"]["local"]["templates"]]
        assert names == ["new-tmpl"]
        assert machine_template_hook_exists("local", "new-tmpl", "oncreate")
        assert not machine_template_hook_exists("local", "old-tmpl", "oncreate")

        projects = {p["name"]: p for p in load_projects()}
        assert projects["proj-a"]["template"] == "new-tmpl"
        assert projects["proj-b"]["template"] == "other-tmpl"


class TestCmdConfigAddTemplateProjectNameConflict:
    def test_errors_when_template_name_is_existing_project(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.config.commands import cmd_config_add_template
        save_config({
            "machines": {"local": {"type": "local", "templates": []}},
            "default_machine": "local",
        })
        save_local_projects([{"name": "my-project", "machine": "local", "path": "/tmp/my-project"}])
        args = MagicMock()
        args.machine_name = "local"
        args.template_name = "my-project"
        args.params = []
        with pytest.raises(SystemExit):
            cmd_config_add_template(args)


class TestCmdConfigRenameTemplateProjectNameConflict:
    def test_errors_when_new_name_is_existing_project(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
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
        save_local_projects([{"name": "existing-project", "machine": "local", "path": "/tmp/existing-project"}])
        args = MagicMock()
        args.machine_name = "local"
        args.old_name = "old-tmpl"
        args.new_name = "existing-project"
        with pytest.raises(SystemExit):
            cmd_config_rename_template(args)


class TestThreeWayNameUniqueness:
    """Project, template, and machine names share one global namespace —
    every creation/rename site must reject a name already claimed by
    either of the other two categories."""

    def test_add_template_errors_when_name_is_existing_machine(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_add_template
        save_config({
            "machines": {
                "local": {"type": "local", "templates": []},
                "other-machine": {"type": "local"},
            },
            "default_machine": "local",
        })
        args = MagicMock()
        args.machine_name = "local"
        args.template_name = "other-machine"
        args.params = []
        with pytest.raises(SystemExit):
            cmd_config_add_template(args)

    def test_rename_template_errors_when_new_name_is_existing_machine(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_rename_template
        save_config({
            "machines": {
                "local": {
                    "type": "local",
                    "templates": [{"name": "old-tmpl", "type": "directory", "path": "/tmp/old"}],
                },
                "other-machine": {"type": "local"},
            },
            "default_machine": "local",
        })
        args = MagicMock()
        args.machine_name = "local"
        args.old_name = "old-tmpl"
        args.new_name = "other-machine"
        with pytest.raises(SystemExit):
            cmd_config_rename_template(args)

    def test_add_machine_errors_when_name_is_existing_template(self, tmp_config, monkeypatch):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_add_machine
        save_config({
            "machines": {
                "local": {
                    "type": "local",
                    "templates": [{"name": "my-tmpl", "type": "directory", "path": "/tmp/tmpl"}],
                },
            },
            "default_machine": "local",
        })
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: "my-tmpl")
        with pytest.raises(SystemExit):
            cmd_config_add_machine(MagicMock())

    def test_add_machine_errors_when_name_is_existing_project(self, tmp_config, monkeypatch):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.config.commands import cmd_config_add_machine
        save_config({"machines": {"local": {"type": "local"}}, "default_machine": "local"})
        save_local_projects([{"name": "my-project", "machine": "local", "path": "/tmp/my-project"}])
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: "my-project")
        with pytest.raises(SystemExit):
            cmd_config_add_machine(MagicMock())

    def test_rename_machine_errors_when_new_name_is_existing_template(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.config.commands import cmd_config_rename_machine
        save_config({
            "machines": {
                "local": {
                    "type": "local",
                    "templates": [{"name": "my-tmpl", "type": "directory", "path": "/tmp/tmpl"}],
                },
                "other-machine": {"type": "local"},
            },
            "default_machine": "local",
        })
        args = MagicMock(old_name="other-machine", new_name="my-tmpl")
        with pytest.raises(SystemExit):
            cmd_config_rename_machine(args)

    def test_rename_machine_errors_when_new_name_is_existing_project(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.config.commands import cmd_config_rename_machine
        save_config({
            "machines": {
                "local": {"type": "local"},
                "other-machine": {"type": "local"},
            },
            "default_machine": "local",
        })
        save_local_projects([{"name": "my-project", "machine": "local", "path": "/tmp/my-project"}])
        args = MagicMock(old_name="other-machine", new_name="my-project")
        with pytest.raises(SystemExit):
            cmd_config_rename_machine(args)
