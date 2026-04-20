"""Tests for colette_cli.project.commands."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from tests.conftest import write_config, write_projects, make_local_machine, make_project


LOCAL_CFG = {
    "machines": {"local": make_local_machine()},
    "default_machine": "local",
}


class TestRequireProject:
    def test_returns_project_when_found(self, tmp_config):
        from colette_cli.utils.config import save_projects
        from colette_cli.project.commands import require_project
        save_projects([make_project("proj")])
        p = require_project("proj")
        assert p["name"] == "proj"

    def test_exits_when_not_found(self, tmp_config):
        from colette_cli.project.commands import require_project
        with pytest.raises(SystemExit):
            require_project("missing")


class TestCmdList:
    def test_no_projects_prints_message(self, tmp_config, capsys):
        from colette_cli.project.commands import cmd_list
        cmd_list(MagicMock())
        assert "No projects" in capsys.readouterr().out

    def test_lists_projects_by_machine(self, tmp_config, capsys):
        from colette_cli.utils.config import save_projects
        from colette_cli.project.commands import cmd_list
        save_projects([make_project("alpha"), make_project("beta")])
        cmd_list(MagicMock())
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" in out


class TestCmdLink:
    def test_links_existing_local_path(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, load_projects
        from colette_cli.project.commands import cmd_link
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "existing"
        project_dir.mkdir()
        args = MagicMock()
        args.path = str(project_dir)
        args.machine = "local"
        args.name = "my-project"
        cmd_link(args)
        projects = load_projects()
        assert any(p["name"] == "my-project" for p in projects)

    def test_link_derives_name_from_path(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, load_projects
        from colette_cli.project.commands import cmd_link
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "derived-name"
        project_dir.mkdir()
        args = MagicMock()
        args.path = str(project_dir)
        args.machine = "local"
        args.name = None
        cmd_link(args)
        projects = load_projects()
        assert any(p["name"] == "derived-name" for p in projects)

    def test_link_fails_when_path_missing(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.project.commands import cmd_link
        save_config(LOCAL_CFG)
        args = MagicMock()
        args.path = "/nonexistent/path"
        args.machine = "local"
        args.name = "proj"
        with pytest.raises(SystemExit):
            cmd_link(args)

    def test_link_fails_on_duplicate_name(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.project.commands import cmd_link
        save_config(LOCAL_CFG)
        save_projects([make_project("existing")])
        project_dir = tmp_path / "existing"
        project_dir.mkdir()
        args = MagicMock()
        args.path = str(project_dir)
        args.machine = "local"
        args.name = "existing"
        with pytest.raises(SystemExit):
            cmd_link(args)

    def test_link_fails_on_invalid_name(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config
        from colette_cli.project.commands import cmd_link
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "some-dir"
        project_dir.mkdir()
        args = MagicMock()
        args.path = str(project_dir)
        args.machine = "local"
        args.name = "Invalid_Name"
        with pytest.raises(SystemExit):
            cmd_link(args)


class TestCmdUnlink:
    def test_unlinks_project_on_confirmation(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects, load_projects
        from colette_cli.project.commands import cmd_unlink
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        args = MagicMock()
        args.name = "proj"
        with patch("builtins.input", return_value="y"):
            cmd_unlink(args)
        assert load_projects() == []

    def test_unlink_aborts_on_no(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects, load_projects
        from colette_cli.project.commands import cmd_unlink
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        args = MagicMock()
        args.name = "proj"
        with patch("builtins.input", return_value="n"):
            cmd_unlink(args)
        assert len(load_projects()) == 1

    def test_unlink_does_not_delete_files(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.project.commands import cmd_unlink
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        save_projects([make_project("proj", path=str(project_dir))])
        args = MagicMock()
        args.name = "proj"
        with patch("builtins.input", return_value="y"):
            cmd_unlink(args)
        assert project_dir.exists()

    def test_unlink_fails_on_missing_project(self, tmp_config):
        from colette_cli.project.commands import cmd_unlink
        args = MagicMock()
        args.name = "missing"
        with pytest.raises(SystemExit):
            cmd_unlink(args)


class TestCmdDelete:
    def test_delete_removes_files_and_record(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_projects, load_projects
        from colette_cli.project.commands import cmd_delete
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        save_projects([make_project("proj", path=str(project_dir))])
        args = MagicMock()
        args.name = "proj"
        with patch("builtins.input", return_value="proj"):
            cmd_delete(args)
        assert not project_dir.exists()
        assert load_projects() == []

    def test_delete_aborts_on_wrong_name(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_projects, load_projects
        from colette_cli.project.commands import cmd_delete
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        save_projects([make_project("proj", path=str(project_dir))])
        args = MagicMock()
        args.name = "proj"
        with patch("builtins.input", return_value="wrong"):
            cmd_delete(args)
        assert project_dir.exists()
        assert len(load_projects()) == 1

    def test_delete_skip_confirmation_removes_without_prompt(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_projects, load_projects
        from colette_cli.project.commands import cmd_delete
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        save_projects([make_project("proj", path=str(project_dir))])
        args = MagicMock()
        args.name = "proj"
        with patch("builtins.input") as mock_input:
            cmd_delete(args, skip_confirmation=True)
        mock_input.assert_not_called()
        assert not project_dir.exists()
        assert load_projects() == []

    def test_ondelete_hook_runs_before_delete(self, tmp_config, tmp_path):
        """The ondelete hook executes before project files are removed."""
        from colette_cli.utils.config import (
            save_config, save_projects, load_projects,
            write_machine_template_hook, save_templates,
        )
        from colette_cli.project.commands import cmd_delete

        marker = tmp_path / "marker.txt"
        write_machine_template_hook("local", "tmpl", "ondelete", f"#!/usr/bin/env bash\necho ondelete > {marker}")

        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        cfg = {
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": str(tmp_path / "projects"),
                    "templates": [{"name": "tmpl", "type": "directory", "path": str(project_dir)}],
                }
            },
            "default_machine": "local",
        }
        save_config(cfg)
        save_templates({"templates": [{"name": "tmpl", "params": {}}]})
        save_projects([make_project("proj", path=str(project_dir), template="tmpl")])

        args = MagicMock()
        args.name = "proj"
        cmd_delete(args, skip_confirmation=True)

        assert marker.exists(), "ondelete hook did not run"
        assert marker.read_text().strip() == "ondelete"
        assert not project_dir.exists()
        assert load_projects() == []


class TestCmdCreate:
    def test_oncreate_hook_runs_on_create(self, tmp_config, tmp_path):
        """The oncreate hook actually executes when cmd_create is called."""
        from colette_cli.utils.config import save_config, load_projects, write_machine_template_hook, save_templates
        from colette_cli.project.commands import cmd_create
        marker = tmp_path / "marker.txt"
        write_machine_template_hook("local", "tmpl", "oncreate", f"#!/usr/bin/env bash\necho oncreate > {marker}")
        template_dir = tmp_path / "tmpl-source"
        template_dir.mkdir()
        cfg = {
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": str(tmp_path / "projects"),
                    "templates": [{"name": "tmpl", "type": "directory", "path": str(template_dir)}],
                }
            },
            "default_machine": "local",
        }
        save_config(cfg)
        save_templates({"templates": [{"name": "tmpl", "params": {}}]})
        args = MagicMock()
        args.name = "my-project"
        args.machine = "local"
        args.template = "tmpl"
        project_dir = tmp_path / "projects" / "my-project"

        def fake_copytree(src, dst):
            Path(dst).mkdir(parents=True, exist_ok=True)

        with patch("colette_cli.project.commands.shutil.copytree", side_effect=fake_copytree):
            cmd_create(args)

        assert marker.exists(), "oncreate hook did not run"
        assert marker.read_text().strip() == "oncreate"
        projects = load_projects()
        assert any(p["name"] == "my-project" for p in projects)


class TestCmdCopilot:
    def test_copilot_local_no_existing_session_starts_copilot(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.project.commands import cmd_copilot

        project_path = str(tmp_path / "my-project")
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_projects([make_project("my-project", path=project_path)])

        args = MagicMock()
        args.name = "my-project"

        with patch("colette_cli.project.commands.get_sessions", return_value=set()), \
             patch("colette_cli.project.commands.local_tmux_session") as mock_tmux:
            cmd_copilot(args)

        mock_tmux.assert_called_once()
        call_args = mock_tmux.call_args
        assert call_args[0][0] == "my-project-copilot"
        assert call_args[0][1] == project_path
        assert call_args[0][2] == "copilot"

    def test_copilot_local_existing_session_attaches(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.project.commands import cmd_copilot

        project_path = str(tmp_path / "my-project")
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_projects([make_project("my-project", path=project_path)])

        args = MagicMock()
        args.name = "my-project"

        # Existing copilot session → should just attach (exec bash command)
        with patch("colette_cli.project.commands.get_sessions", return_value={"my-project-copilot"}), \
             patch("colette_cli.project.commands.local_tmux_session") as mock_tmux:
            cmd_copilot(args)

        mock_tmux.assert_called_once()
        call_args = mock_tmux.call_args
        assert call_args[0][0] == "my-project-copilot"
        assert call_args[0][2] == "exec bash"

    def test_copilot_session_name_is_project_copilot(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.project.commands import cmd_copilot

        project_path = str(tmp_path / "alpha")
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_projects([make_project("alpha", path=project_path)])

        args = MagicMock()
        args.name = "alpha"

        with patch("colette_cli.project.commands.get_sessions", return_value=set()), \
             patch("colette_cli.project.commands.local_tmux_session") as mock_tmux:
            cmd_copilot(args)

        session_name = mock_tmux.call_args[0][0]
        assert session_name == "alpha-copilot"

    def test_copilot_remote_machine_uses_ssh(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.project.commands import cmd_copilot

        cfg = {
            "machines": {
                "remote": {"type": "ssh", "host": "server", "projects_dir": "/home/user"}
            },
            "default_machine": "remote",
        }
        save_config(cfg)
        save_projects([make_project("my-project", machine="remote", path="/home/user/my-project")])

        args = MagicMock()
        args.name = "my-project"

        with patch("colette_cli.project.commands.get_sessions", return_value=set()), \
             patch("colette_cli.project.commands.ssh_interactive") as mock_ssh:
            cmd_copilot(args)

        mock_ssh.assert_called_once()
        # Should launch a tmux session on the remote with the picker command
        tmux_cmd = mock_ssh.call_args[0][1]
        assert "my-project-copilot" in tmux_cmd
        assert "/home/user/my-project" in tmux_cmd

    def test_copilot_missing_project_exits(self, tmp_config):
        from colette_cli.project.commands import cmd_copilot

        args = MagicMock()
        args.name = "no-such-project"

        with pytest.raises(SystemExit):
            cmd_copilot(args)


class TestCwdAutoDetect:
    """Integration tests: commands auto-detect project name from cwd."""

    def _setup(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_projects
        project_path = tmp_path / "my-project"
        project_path.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_projects([make_project("my-project", path=str(project_path))])
        return project_path

    def test_attach_resolves_from_cwd(self, tmp_config, tmp_path):
        from colette_cli.project.commands import cmd_attach
        import os
        project_path = self._setup(tmp_config, tmp_path)
        args = MagicMock()
        args.name = "my-project"
        orig = os.getcwd()
        try:
            os.chdir(str(project_path))
            with patch("colette_cli.project.commands.local_tmux_session"):
                cmd_attach(args)
        finally:
            os.chdir(orig)

    def test_code_resolves_from_cwd(self, tmp_config, tmp_path):
        from colette_cli.project.commands import cmd_code
        import os
        project_path = self._setup(tmp_config, tmp_path)
        args = MagicMock()
        args.name = "my-project"
        orig = os.getcwd()
        try:
            os.chdir(str(project_path))
            with patch("subprocess.run"):
                cmd_code(args)
        finally:
            os.chdir(orig)

    def test_main_resolves_name_from_cwd(self, tmp_config, tmp_path):
        """main() sets args.name from cwd when command is run without a name."""
        import os, sys
        from colette_cli.utils.config import save_config, save_projects
        project_path = tmp_path / "proj"
        project_path.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_projects([make_project("proj", path=str(project_path))])

        orig = os.getcwd()
        try:
            os.chdir(str(project_path))
            with patch.object(sys, "argv", ["colette", "code"]), \
                 patch("colette_cli.main.cmd_code") as mock_code:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_code.assert_called_once()
        resolved_args = mock_code.call_args[0][0]
        assert resolved_args.name == "proj"

    def test_main_prints_help_when_no_cwd_match(self, tmp_config, tmp_path):
        """main() prints subcommand help and exits 0 when cwd is not a project."""
        import os, sys
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            with patch.object(sys, "argv", ["colette", "code"]):
                from colette_cli.main import main
                with pytest.raises(SystemExit) as exc:
                    main()
        finally:
            os.chdir(orig)
        assert exc.value.code == 0

    def test_copilot_remote_uses_login_shell(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.project.commands import cmd_copilot

        cfg = {
            "machines": {
                "remote": {"type": "ssh", "host": "server", "projects_dir": "/home/user"}
            },
            "default_machine": "remote",
        }
        save_config(cfg)
        save_projects([make_project("my-project", machine="remote", path="/home/user/my-project")])

        args = MagicMock()
        args.name = "my-project"

        with patch("colette_cli.project.commands.get_sessions", return_value=set()), \
             patch("colette_cli.project.commands.ssh_interactive") as mock_ssh:
            cmd_copilot(args)

        tmux_cmd = mock_ssh.call_args[0][1]
        assert "bash -lc copilot" in tmux_cmd

    def test_copilot_remote_with_port_uses_port_in_ssh(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.project.commands import cmd_copilot

        cfg = {
            "machines": {
                "remote": {"type": "ssh", "host": "server", "port": 24, "projects_dir": "/home/user"}
            },
            "default_machine": "remote",
        }
        save_config(cfg)
        save_projects([make_project("my-project", machine="remote", path="/home/user/my-project")])

        args = MagicMock()
        args.name = "my-project"

        with patch("colette_cli.project.commands.get_sessions", return_value=set()), \
             patch("colette_cli.utils.ssh.subprocess.run") as mock_run:
            cmd_copilot(args)

        ssh_cmd = mock_run.call_args[0][0]
        assert "-p" in ssh_cmd
        assert "24" in ssh_cmd
