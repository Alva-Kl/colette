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
        from colette_cli.utils.config import save_local_projects
        from colette_cli.project.commands import require_project
        save_local_projects([make_project("proj")])
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
        from colette_cli.utils.config import save_local_projects
        from colette_cli.project.commands import cmd_list
        save_local_projects([make_project("alpha"), make_project("beta")])
        cmd_list(MagicMock())
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" in out

    def test_marks_cached_remote_projects(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config, save_local_projects, save_machine_cache
        from colette_cli.project.commands import cmd_list
        save_config({
            "machines": {
                "local": make_local_machine(),
                "myserver": {"type": "ssh", "host": "server", "colette_path": "/bin/colette"},
            },
            "default_machine": "local",
        })
        save_local_projects([make_project("local-proj")])
        save_machine_cache("myserver", {
            "machine": "myserver",
            "synced_at": "2026-01-01T00:00:00Z",
            "projects_dir": "/home/user",
            "templates": [],
            "projects": [{"name": "remote-proj", "machine": "local", "path": "/home/user/remote-proj", "template": None}],
        })
        cmd_list(MagicMock())
        out = capsys.readouterr().out
        assert "local-proj" in out
        assert "remote-proj" in out
        assert "cached" in out


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
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_link
        save_config(LOCAL_CFG)
        save_local_projects([make_project("existing")])
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
        from colette_cli.utils.config import save_config, save_local_projects, load_projects
        from colette_cli.project.commands import cmd_unlink
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj")])
        args = MagicMock()
        args.name = "proj"
        with patch("builtins.input", return_value="y"):
            cmd_unlink(args)
        assert load_projects() == []

    def test_unlink_aborts_on_no(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects, load_projects
        from colette_cli.project.commands import cmd_unlink
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj")])
        args = MagicMock()
        args.name = "proj"
        with patch("builtins.input", return_value="n"):
            cmd_unlink(args)
        assert len(load_projects()) == 1

    def test_unlink_does_not_delete_files(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_unlink
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        save_local_projects([make_project("proj", path=str(project_dir))])
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
        from colette_cli.utils.config import save_config, save_local_projects, load_projects
        from colette_cli.project.commands import cmd_delete
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        save_local_projects([make_project("proj", path=str(project_dir))])
        args = MagicMock()
        args.name = "proj"
        with patch("builtins.input", return_value="proj"):
            cmd_delete(args)
        assert not project_dir.exists()
        assert load_projects() == []

    def test_delete_aborts_on_wrong_name(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects, load_projects
        from colette_cli.project.commands import cmd_delete
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        save_local_projects([make_project("proj", path=str(project_dir))])
        args = MagicMock()
        args.name = "proj"
        with patch("builtins.input", return_value="wrong"):
            cmd_delete(args)
        assert project_dir.exists()
        assert len(load_projects()) == 1

    def test_delete_skip_confirmation_removes_without_prompt(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects, load_projects
        from colette_cli.project.commands import cmd_delete
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        save_local_projects([make_project("proj", path=str(project_dir))])
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
            save_config, save_local_projects, load_projects,
            write_machine_template_hook,
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
        save_local_projects([make_project("proj", path=str(project_dir), template="tmpl")])

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
        from colette_cli.utils.config import save_config, load_projects, write_machine_template_hook
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

    def test_create_local_no_template(self, tmp_config, tmp_path):
        """Creates an empty directory when no template is given (local machine)."""
        from colette_cli.utils.config import save_config, load_projects
        from colette_cli.project.commands import cmd_create

        projects_dir = tmp_path / "projects"
        cfg = {
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": str(projects_dir),
                    "templates": [],
                }
            },
            "default_machine": "local",
        }
        save_config(cfg)
        args = MagicMock()
        args.name = "bare-project"
        args.machine = "local"
        args.template = None

        cmd_create(args)

        assert (projects_dir / "bare-project").is_dir()
        projects = load_projects()
        assert any(p["name"] == "bare-project" and p["template"] is None for p in projects)

    def test_create_remote_no_template(self, tmp_config, tmp_path):
        """Creates a directory via ssh mkdir when no template is given (remote machine),
        then pushes the new project's record to the remote's own projects.json."""
        from colette_cli.utils.config import save_config
        from colette_cli.project.commands import cmd_create

        cfg = {
            "machines": {
                "remote": {
                    "type": "ssh",
                    "host": "myhost",
                    "projects_dir": "/home/user/projects",
                    "templates": [],
                }
            },
            "default_machine": "remote",
        }
        save_config(cfg)
        args = MagicMock()
        args.name = "bare-remote"
        args.machine = "remote"
        args.template = None

        no_exists = MagicMock(stdout="", returncode=0)
        mkdir_ok = MagicMock(stdout="", returncode=0)

        with patch("colette_cli.project.commands.ssh_run", side_effect=[no_exists, mkdir_ok]) as mock_ssh, \
             patch("colette_cli.project.commands.write_project_record") as mock_write:
            cmd_create(args)

        calls = [c[0][1] for c in mock_ssh.call_args_list]
        assert any("mkdir" in c for c in calls)
        mock_write.assert_called_once()
        pushed_project = mock_write.call_args[0][2]
        assert pushed_project["name"] == "bare-remote"
        assert pushed_project["template"] is None

    def test_create_local_skips_template_when_blank_input(self, tmp_config, tmp_path):
        """Pressing Enter at the template prompt creates an empty project."""
        from colette_cli.utils.config import save_config, load_projects
        from colette_cli.project.commands import cmd_create

        projects_dir = tmp_path / "projects"
        template_dir = tmp_path / "tmpl-source"
        template_dir.mkdir()
        cfg = {
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": str(projects_dir),
                    "templates": [{"name": "tmpl", "type": "directory", "path": str(template_dir)}],
                }
            },
            "default_machine": "local",
        }
        save_config(cfg)
        args = MagicMock()
        args.name = "scratch-project"
        args.machine = "local"
        args.template = None

        with patch("builtins.input", return_value=""):
            cmd_create(args)

        assert (projects_dir / "scratch-project").is_dir()
        projects = load_projects()
        assert any(p["name"] == "scratch-project" and p["template"] is None for p in projects)

    def test_create_remote_with_cache_only_template(self, tmp_config):
        """A template never configured on this controller, only known via the
        remote's own sync cache, can still be used to create a new project —
        its type/path is resolved on the remote itself."""
        from colette_cli.utils.config import save_config, save_machine_cache
        from colette_cli.project.commands import cmd_create

        save_config({
            "machines": {
                "remote": {
                    "type": "ssh",
                    "host": "myhost",
                    "projects_dir": "/home/user/projects",
                    "templates": [],
                }
            },
            "default_machine": "remote",
        })
        save_machine_cache("remote", {
            "machine": "remote",
            "synced_at": "2026-01-01T00:00:00Z",
            "projects_dir": "/home/user",
            "templates": [{"name": "docker-deployed", "type": "directory", "path": "~/tmpl-source"}],
            "projects": [],
        })
        args = MagicMock()
        args.name = "new-remote-project"
        args.machine = "remote"
        args.template = "docker-deployed"

        no_exists = MagicMock(stdout="", returncode=0)
        source_ok = MagicMock(stdout="ok", returncode=0)
        cp_ok = MagicMock(stdout="", returncode=0)

        with patch("colette_cli.project.commands.ssh_run", side_effect=[no_exists, source_ok, cp_ok]) as mock_ssh, \
             patch("colette_cli.project.commands.run_template_hook", return_value=True), \
             patch("colette_cli.project.commands.write_project_record") as mock_write:
            cmd_create(args)

        cp_call = mock_ssh.call_args_list[2][0][1]
        assert "~/tmpl-source" in cp_call
        pushed_project = mock_write.call_args[0][2]
        assert pushed_project["template"] == "docker-deployed"


class TestCmdAgent:
    def test_agent_local_no_existing_session_starts_agent(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_agent

        project_path = str(tmp_path / "my-project")
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([make_project("my-project", path=project_path)])

        args = MagicMock()
        args.name = "my-project"

        with patch("colette_cli.project.commands.get_sessions", return_value=set()), \
             patch("colette_cli.project.commands.local_tmux_session") as mock_tmux:
            cmd_agent(args)

        mock_tmux.assert_called_once()
        call_args = mock_tmux.call_args
        assert call_args[0][0] == "my-project-agent"
        assert call_args[0][1] == project_path
        assert call_args[0][2] == "copilot --resume"

    def test_agent_local_existing_session_attaches(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_agent

        project_path = str(tmp_path / "my-project")
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([make_project("my-project", path=project_path)])

        args = MagicMock()
        args.name = "my-project"

        # Existing agent session → should just attach (exec bash command)
        with patch("colette_cli.project.commands.get_sessions", return_value={"my-project-agent"}), \
             patch("colette_cli.project.commands.local_tmux_session") as mock_tmux:
            cmd_agent(args)

        mock_tmux.assert_called_once()
        call_args = mock_tmux.call_args
        assert call_args[0][0] == "my-project-agent"
        assert call_args[0][2] == "exec bash"

    def test_agent_session_name_is_project_agent(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_agent

        project_path = str(tmp_path / "alpha")
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([make_project("alpha", path=project_path)])

        args = MagicMock()
        args.name = "alpha"

        with patch("colette_cli.project.commands.get_sessions", return_value=set()), \
             patch("colette_cli.project.commands.local_tmux_session") as mock_tmux:
            cmd_agent(args)

        session_name = mock_tmux.call_args[0][0]
        assert session_name == "alpha-agent"

    def test_agent_local_custom_agent_command(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_agent

        project_path = str(tmp_path / "my-project")
        machine = make_local_machine()
        machine["agent_command"] = "claude"
        cfg = {"machines": {"local": machine}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([make_project("my-project", path=project_path)])

        args = MagicMock()
        args.name = "my-project"

        with patch("colette_cli.project.commands.get_sessions", return_value=set()), \
             patch("colette_cli.project.commands.local_tmux_session") as mock_tmux:
            cmd_agent(args)

        assert mock_tmux.call_args[0][2] == "claude"

    def test_agent_remote_machine_uses_ssh(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_agent

        cfg = {
            "machines": {
                "remote": {"type": "ssh", "host": "server", "projects_dir": "/home/user"}
            },
            "default_machine": "remote",
        }
        save_config(cfg)
        save_local_projects([make_project("my-project", machine="remote", path="/home/user/my-project")])

        args = MagicMock()
        args.name = "my-project"

        with patch("colette_cli.project.commands.get_sessions", return_value=set()), \
             patch("colette_cli.project.commands.ssh_interactive") as mock_ssh:
            cmd_agent(args)

        mock_ssh.assert_called_once()
        tmux_cmd = mock_ssh.call_args[0][1]
        assert "my-project-agent" in tmux_cmd
        assert "/home/user/my-project" in tmux_cmd

    def test_agent_missing_project_exits(self, tmp_config):
        from colette_cli.project.commands import cmd_agent

        args = MagicMock()
        args.name = "no-such-project"

        with pytest.raises(SystemExit):
            cmd_agent(args)


class TestCmdIde:
    def test_ide_local_default_command(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_ide

        project_path = tmp_path / "my-project"
        project_path.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([make_project("my-project", path=str(project_path))])

        args = MagicMock()
        args.name = "my-project"

        with patch("colette_cli.project.commands.subprocess.run") as mock_run:
            cmd_ide(args)

        mock_run.assert_called_once_with(["code", str(project_path)])

    def test_ide_remote_default_command(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_ide

        cfg = {
            "machines": {
                "remote": {"type": "ssh", "host": "server", "projects_dir": "/home/user"}
            },
            "default_machine": "remote",
        }
        save_config(cfg)
        save_local_projects([make_project("my-project", machine="remote", path="/home/user/my-project")])

        args = MagicMock()
        args.name = "my-project"

        with patch("colette_cli.project.commands.subprocess.run") as mock_run:
            cmd_ide(args)

        mock_run.assert_called_once_with(
            ["code", "--folder-uri", "vscode-remote://ssh-remote+server/home/user/my-project"]
        )

    def test_ide_custom_command_with_path_placeholder(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_ide

        cfg = {
            "machines": {
                "remote": {
                    "type": "ssh",
                    "host": "server",
                    "projects_dir": "/home/user",
                    "ide_command": "zed ssh://{host}{path}",
                }
            },
            "default_machine": "remote",
        }
        save_config(cfg)
        save_local_projects([make_project("my-project", machine="remote", path="/home/user/my-project")])

        args = MagicMock()
        args.name = "my-project"

        with patch("colette_cli.project.commands.subprocess.run") as mock_run:
            cmd_ide(args)

        mock_run.assert_called_once_with(["zed", "ssh://server/home/user/my-project"])

    def test_ide_custom_bare_command_appends_path(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_ide

        project_path = tmp_path / "my-project"
        project_path.mkdir()
        machine = make_local_machine()
        machine["ide_command"] = "zed"
        cfg = {"machines": {"local": machine}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([make_project("my-project", path=str(project_path))])

        args = MagicMock()
        args.name = "my-project"

        with patch("colette_cli.project.commands.subprocess.run") as mock_run:
            cmd_ide(args)

        mock_run.assert_called_once_with(["zed", str(project_path)])


class TestCmdAttach:
    def test_local_project_opens_local_tmux_session(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_attach
        project_path = tmp_path / "my-project"
        project_path.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([make_project("my-project", path=str(project_path))])
        args = MagicMock()
        args.name = "my-project"

        with patch("colette_cli.project.commands.local_tmux_session") as mock_tmux:
            cmd_attach(args)

        mock_tmux.assert_called_once()
        assert mock_tmux.call_args[0][0] == "my-project"
        assert mock_tmux.call_args[0][1] == str(project_path)

    def test_remote_project_uses_ssh_interactive(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_attach
        cfg = {
            "machines": {"remote": {"type": "ssh", "host": "user@host", "projects_dir": "/home/user"}},
            "default_machine": "remote",
        }
        save_config(cfg)
        save_local_projects([make_project("my-project", machine="remote", path="/home/user/my-project")])
        args = MagicMock()
        args.name = "my-project"

        with patch("colette_cli.project.commands.ssh_interactive") as mock_ssh:
            cmd_attach(args)

        mock_ssh.assert_called_once()
        machine_arg, tmux_cmd = mock_ssh.call_args[0]
        assert machine_arg["host"] == "user@host"
        assert "my-project" in tmux_cmd
        assert "/home/user/my-project" in tmux_cmd

    def test_project_name_takes_precedence_over_a_same_named_machine(self, tmp_config, tmp_path):
        """Project/template/machine names share one namespace enforced at
        creation time, but for a pre-existing config that predates the
        check, attach must resolve project-first (never a regression for
        the (rare) existing collision case)."""
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_attach
        project_path = tmp_path / "dupe-name"
        project_path.mkdir()
        cfg = {
            "machines": {
                "local": make_local_machine(),
                "dupe-name": {"type": "local", "projects_dir": "/tmp"},
            },
            "default_machine": "local",
        }
        save_config(cfg)
        save_local_projects([make_project("dupe-name", path=str(project_path))])
        args = MagicMock()
        args.name = "dupe-name"

        with patch("colette_cli.project.commands.local_tmux_session") as mock_tmux, \
             patch("colette_cli.project.commands.get_sessions") as mock_sessions:
            cmd_attach(args)

        mock_tmux.assert_called_once()
        assert mock_tmux.call_args[0][1] == str(project_path)
        mock_sessions.assert_not_called()  # machine branch never entered

    def test_errors_when_name_matches_neither_project_nor_machine(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.project.commands import cmd_attach
        save_config({"machines": {"local": make_local_machine()}, "default_machine": "local"})
        args = MagicMock()
        args.name = "ghost"
        with pytest.raises(SystemExit):
            cmd_attach(args)


class TestCmdAttachMachine:
    _LOCAL_CFG = {
        "machines": {"local": {"type": "local", "projects_dir": "/tmp/projects"}},
        "default_machine": "local",
    }
    _REMOTE_CFG = {
        "machines": {
            "myremote": {
                "type": "ssh",
                "host": "user@remotehost",
                "projects_dir": "/home/user/projects",
            }
        },
        "default_machine": "myremote",
    }

    def test_local_no_existing_session_creates_with_expanded_cwd(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.project.commands import cmd_attach
        save_config(self._LOCAL_CFG)
        args = MagicMock()
        args.name = "local"
        with patch("colette_cli.project.commands.get_sessions", return_value=set()), \
             patch("colette_cli.project.commands.local_tmux_session") as mock_local:
            cmd_attach(args)
        mock_local.assert_called_once_with("local-shell", "/tmp/projects", "exec bash")

    def test_local_existing_session_still_attaches(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.project.commands import cmd_attach
        save_config(self._LOCAL_CFG)
        args = MagicMock()
        args.name = "local"
        with patch("colette_cli.project.commands.get_sessions", return_value={"local-shell"}), \
             patch("colette_cli.project.commands.local_tmux_session") as mock_local:
            cmd_attach(args)
        mock_local.assert_called_once_with("local-shell", "/tmp/projects", "exec bash")

    def test_local_falls_back_to_home_when_no_projects_dir(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.project.commands import cmd_attach
        save_config({"machines": {"local": {"type": "local"}}, "default_machine": "local"})
        args = MagicMock()
        args.name = "local"
        with patch("colette_cli.project.commands.get_sessions", return_value=set()), \
             patch("colette_cli.project.commands.local_tmux_session") as mock_local:
            cmd_attach(args)
        cwd = mock_local.call_args[0][1]
        assert cwd == str(Path("~").expanduser())

    def test_remote_no_existing_session_creates_over_ssh(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.project.commands import cmd_attach
        save_config(self._REMOTE_CFG)
        args = MagicMock()
        args.name = "myremote"
        with patch("colette_cli.project.commands.get_sessions", return_value=set()), \
             patch("colette_cli.project.commands.ssh_interactive") as mock_ssh:
            cmd_attach(args)
        mock_ssh.assert_called_once()
        machine_arg, cmd_arg = mock_ssh.call_args[0]
        assert machine_arg["host"] == "user@remotehost"
        assert "new-session -A -s myremote-shell" in cmd_arg
        assert "/home/user/projects" in cmd_arg

    def test_remote_existing_session_attaches(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.project.commands import cmd_attach
        save_config(self._REMOTE_CFG)
        args = MagicMock()
        args.name = "myremote"
        with patch("colette_cli.project.commands.get_sessions", return_value={"myremote-shell"}), \
             patch("colette_cli.project.commands.ssh_interactive") as mock_ssh:
            cmd_attach(args)
        mock_ssh.assert_called_once()
        _machine_arg, cmd_arg = mock_ssh.call_args[0]
        assert "attach-session -t myremote-shell" in cmd_arg
        assert "new-session" not in cmd_arg


class TestCwdAutoDetect:
    """Integration tests: commands auto-detect project name from cwd."""

    def _setup(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        project_path = tmp_path / "my-project"
        project_path.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([make_project("my-project", path=str(project_path))])
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
            with patch("colette_cli.project.commands.local_tmux_session") as mock_tmux:
                cmd_attach(args)
        finally:
            os.chdir(orig)

        mock_tmux.assert_called_once()
        call_args = mock_tmux.call_args
        assert call_args[0][0] == "my-project"
        assert call_args[0][1] == str(project_path)
        assert "exec bash" in call_args[0][2]

    def test_ide_resolves_from_cwd(self, tmp_config, tmp_path):
        from colette_cli.project.commands import cmd_ide
        import os
        project_path = self._setup(tmp_config, tmp_path)
        args = MagicMock()
        args.name = "my-project"
        orig = os.getcwd()
        try:
            os.chdir(str(project_path))
            with patch("subprocess.run"):
                cmd_ide(args)
        finally:
            os.chdir(orig)

    def test_main_resolves_name_from_cwd(self, tmp_config, tmp_path):
        """main() sets args.name from cwd when command is run without a name."""
        import os, sys
        from colette_cli.utils.config import save_config, save_local_projects
        project_path = tmp_path / "proj"
        project_path.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([make_project("proj", path=str(project_path))])

        orig = os.getcwd()
        try:
            os.chdir(str(project_path))
            with patch.object(sys, "argv", ["colette", "ide"]), \
                 patch("colette_cli.main.cmd_ide") as mock_ide:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_ide.assert_called_once()
        resolved_args = mock_ide.call_args[0][0]
        assert resolved_args.name == "proj"

    def test_main_prints_help_when_no_cwd_match(self, tmp_config, tmp_path):
        """main() prints subcommand help and exits 0 when cwd is not a project."""
        import os, sys
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            with patch.object(sys, "argv", ["colette", "ide"]):
                from colette_cli.main import main
                with pytest.raises(SystemExit) as exc:
                    main()
        finally:
            os.chdir(orig)
        assert exc.value.code == 0

    def test_agent_remote_uses_login_shell(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_agent

        cfg = {
            "machines": {
                "remote": {"type": "ssh", "host": "server", "projects_dir": "/home/user"}
            },
            "default_machine": "remote",
        }
        save_config(cfg)
        save_local_projects([make_project("my-project", machine="remote", path="/home/user/my-project")])

        args = MagicMock()
        args.name = "my-project"

        with patch("colette_cli.project.commands.get_sessions", return_value=set()), \
             patch("colette_cli.project.commands.ssh_interactive") as mock_ssh:
            cmd_agent(args)

        tmux_cmd = mock_ssh.call_args[0][1]
        assert "bash -lc 'copilot --resume'" in tmux_cmd

    def test_agent_remote_with_port_uses_port_in_ssh(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_agent

        cfg = {
            "machines": {
                "remote": {"type": "ssh", "host": "server", "port": 24, "projects_dir": "/home/user"}
            },
            "default_machine": "remote",
        }
        save_config(cfg)
        save_local_projects([make_project("my-project", machine="remote", path="/home/user/my-project")])

        args = MagicMock()
        args.name = "my-project"

        with patch("colette_cli.project.commands.get_sessions", return_value=set()), \
             patch("colette_cli.utils.ssh.subprocess.run") as mock_run:
            cmd_agent(args)

        ssh_calls = [c.args[0] for c in mock_run.call_args_list if c.args and c.args[0][0] == "ssh"]
        assert ssh_calls, "expected an SSH call"
        ssh_cmd = ssh_calls[0]
        assert "-p" in ssh_cmd
        assert "24" in ssh_cmd


class TestRequireProjectTemplateFallback:
    def test_returns_template_as_project_when_no_project_found(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import require_project
        cfg = {
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": "/tmp/projects",
                    "templates": [{"name": "my-tmpl", "type": "directory", "path": "/tmp/my-tmpl"}],
                }
            }
        }
        save_config(cfg)
        save_local_projects([])
        result = require_project("my-tmpl")
        assert result["name"] == "my-tmpl"
        assert result["path"] == "/tmp/my-tmpl"
        assert result["machine"] == "local"
        assert result["template"] == "my-tmpl"

    def test_git_template_not_found_as_project(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import require_project
        cfg = {
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": "/tmp/projects",
                    "templates": [{"name": "git-tmpl", "type": "git", "url": "https://example.com/repo"}],
                }
            }
        }
        save_config(cfg)
        save_local_projects([])
        with pytest.raises(SystemExit):
            require_project("git-tmpl")


class TestCmdCreateTemplateNameConflict:
    def test_errors_when_name_matches_existing_template(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_create
        template_dir = tmp_path / "my-tmpl"
        template_dir.mkdir()
        cfg = {
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": str(tmp_path / "projects"),
                    "templates": [{"name": "my-tmpl", "type": "directory", "path": str(template_dir)}],
                }
            },
            "default_machine": "local",
        }
        save_config(cfg)
        save_local_projects([])
        args = MagicMock()
        args.name = "my-tmpl"
        args.machine = "local"
        args.template = "my-tmpl"
        with pytest.raises(SystemExit):
            cmd_create(args)


class TestCmdLinkTemplateNameConflict:
    def test_errors_when_name_matches_existing_template(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_link
        template_dir = tmp_path / "my-tmpl"
        template_dir.mkdir()
        link_dir = tmp_path / "link-target"
        link_dir.mkdir()
        cfg = {
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": str(tmp_path / "projects"),
                    "templates": [{"name": "my-tmpl", "type": "directory", "path": str(template_dir)}],
                }
            },
            "default_machine": "local",
        }
        save_config(cfg)
        save_local_projects([])
        args = MagicMock()
        args.path = str(link_dir)
        args.name = "my-tmpl"
        args.machine = "local"
        with pytest.raises(SystemExit):
            cmd_link(args)


class TestCmdDeleteTemplateGuard:
    def test_errors_when_given_template_name(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_delete
        template_dir = tmp_path / "my-tmpl"
        template_dir.mkdir()
        cfg = {
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": str(tmp_path / "projects"),
                    "templates": [{"name": "my-tmpl", "type": "directory", "path": str(template_dir)}],
                }
            },
            "default_machine": "local",
        }
        save_config(cfg)
        save_local_projects([])
        args = MagicMock()
        args.name = "my-tmpl"
        with pytest.raises(SystemExit):
            cmd_delete(args)
        # Source directory must NOT have been touched
        assert template_dir.exists()


class TestCmdUnlinkTemplateGuard:
    def test_errors_when_given_template_name(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.project.commands import cmd_unlink
        template_dir = tmp_path / "my-tmpl"
        template_dir.mkdir()
        cfg = {
            "machines": {
                "local": {
                    "type": "local",
                    "projects_dir": str(tmp_path / "projects"),
                    "templates": [{"name": "my-tmpl", "type": "directory", "path": str(template_dir)}],
                }
            },
            "default_machine": "local",
        }
        save_config(cfg)
        save_local_projects([])
        args = MagicMock()
        args.name = "my-tmpl"
        with pytest.raises(SystemExit):
            cmd_unlink(args)


class TestSshInteractiveNestedTmux:
    """ssh_interactive disables local tmux mouse when called from inside tmux."""

    def _machine(self):
        return {"host": "server"}

    def test_outside_tmux_no_mouse_ops(self, monkeypatch):
        """When not inside tmux, no tmux window-option calls are made."""
        from colette_cli.utils.ssh import ssh_interactive

        monkeypatch.delenv("TMUX", raising=False)
        calls = []
        with patch("colette_cli.utils.ssh.subprocess.run", side_effect=lambda *a, **kw: calls.append(a[0])):
            ssh_interactive(self._machine(), "tmux attach-session -t foo")

        tmux_option_calls = [c for c in calls if c[:3] == ["tmux", "set-window-option", "mouse"] or
                             c[:3] == ["tmux", "set-window-option", "-u"]]
        assert tmux_option_calls == []

    def test_inside_tmux_disables_mouse_before_ssh(self, monkeypatch):
        """When inside tmux, mouse is disabled before SSH runs."""
        from colette_cli.utils.ssh import ssh_interactive

        monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,0,0")
        call_log = []
        with patch("colette_cli.utils.ssh.subprocess.run",
                   side_effect=lambda *a, **kw: call_log.append(list(a[0]))):
            ssh_interactive(self._machine(), "tmux attach-session -t foo")

        assert call_log[0] == ["tmux", "set-window-option", "mouse", "off"]
        ssh_call = next(c for c in call_log if c[0] == "ssh")
        assert "-t" in ssh_call
        assert "server" in ssh_call

    def test_inside_tmux_restores_mouse_after_ssh(self, monkeypatch):
        """When inside tmux, the window-level mouse override is removed after SSH exits."""
        from colette_cli.utils.ssh import ssh_interactive

        monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,0,0")
        call_log = []
        with patch("colette_cli.utils.ssh.subprocess.run",
                   side_effect=lambda *a, **kw: call_log.append(list(a[0]))):
            ssh_interactive(self._machine(), "tmux attach-session -t foo")

        assert call_log[-1] == ["tmux", "set-window-option", "-u", "mouse"]

    def test_inside_tmux_restores_mouse_even_on_ssh_failure(self, monkeypatch):
        """Mouse is restored even if SSH raises an exception."""
        from colette_cli.utils.ssh import ssh_interactive

        monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,0,0")
        restore_calls = []

        def fake_run(cmd, **kw):
            if cmd[:3] == ["tmux", "set-window-option", "-u"]:
                restore_calls.append(cmd)
                return
            if cmd[0] == "ssh":
                raise RuntimeError("connection refused")

        with patch("colette_cli.utils.ssh.subprocess.run", side_effect=fake_run):
            with pytest.raises(RuntimeError):
                ssh_interactive(self._machine(), "tmux attach-session -t foo")

        assert restore_calls == [["tmux", "set-window-option", "-u", "mouse"]]
