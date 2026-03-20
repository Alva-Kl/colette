"""Tests for colette_cli.session.commands."""

import pytest
from unittest.mock import patch, MagicMock, call

from tests.conftest import make_local_machine, make_project


LOCAL_CFG = {
    "machines": {"local": make_local_machine("/tmp/projects")},
    "default_machine": "local",
}


class TestCmdStart:
    def test_no_projects_prints_message(self, tmp_config, capsys):
        from colette_cli.session.commands import cmd_start
        cmd_start(MagicMock(machine=None, projects=[]))
        assert "No projects" in capsys.readouterr().out

    def test_starts_session_for_project(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.session.commands import cmd_start
        save_config(LOCAL_CFG)
        save_projects([make_project("proj", path="/tmp")])
        args = MagicMock(machine=None, projects=[])
        with (
            patch("colette_cli.session.commands.ensure_session", return_value=True) as mock_ensure,
            patch("colette_cli.session.commands.run_template_hook", return_value=True),
        ):
            cmd_start(args)
        mock_ensure.assert_called_once()

    def test_onstart_hook_runs_on_start(self, tmp_config, tmp_path):
        """The onstart hook actually executes when cmd_start is called."""
        from colette_cli.utils.config import save_config, save_projects, write_template_hook
        from colette_cli.session.commands import cmd_start
        marker = tmp_path / "marker.txt"
        write_template_hook("tmpl", "onstart", f"#!/usr/bin/env bash\necho onstart > {marker}")
        save_config({
            "machines": {"local": make_local_machine(str(tmp_path))},
            "default_machine": "local",
        })
        save_projects([make_project("proj", path=str(tmp_path), template="tmpl")])
        args = MagicMock(machine=None, projects=[])
        with patch("colette_cli.session.commands.ensure_session", return_value=True):
            cmd_start(args)
        assert marker.exists(), "onstart hook did not run"
        assert marker.read_text().strip() == "onstart"

    def test_filters_by_machine(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.session.commands import cmd_start
        save_config(LOCAL_CFG)
        save_projects([make_project("proj", path="/tmp")])
        args = MagicMock(machine="nonexistent", projects=[])
        with pytest.raises(SystemExit):
            cmd_start(args)


class TestCmdStop:
    def test_no_projects_prints_message(self, tmp_config, capsys):
        from colette_cli.session.commands import cmd_stop
        cmd_stop(MagicMock(machine=None, projects=[]))
        assert "No projects" in capsys.readouterr().out

    def test_stops_local_session(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.session.commands import cmd_stop
        save_config(LOCAL_CFG)
        save_projects([make_project("proj", path="/tmp")])
        args = MagicMock(machine=None, projects=[])
        with (
            patch("colette_cli.session.commands.run_template_hook", return_value=True),
            patch("subprocess.run") as mock_run,
        ):
            cmd_stop(args)
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["tmux", "kill-session", "-t", "proj"]

    def test_onstop_hook_runs_on_stop(self, tmp_config, tmp_path):
        """The onstop hook actually executes when cmd_stop is called."""
        from colette_cli.utils.config import save_config, save_projects, write_template_hook
        from colette_cli.session.commands import cmd_stop
        marker = tmp_path / "marker.txt"
        write_template_hook("tmpl", "onstop", f"#!/usr/bin/env bash\necho onstop > {marker}")
        save_config({
            "machines": {"local": make_local_machine(str(tmp_path))},
            "default_machine": "local",
        })
        save_projects([make_project("proj", path=str(tmp_path), template="tmpl")])
        args = MagicMock(machine=None, projects=[])
        # subprocess.run is called for tmux kill-session (fails silently, capture_output=True)
        # and for the hook itself — only mock the tmux call so the hook runs for real.
        original_run = __import__("subprocess").run

        def selective_run(cmd, *a, **kw):
            if cmd and cmd[0] == "tmux":
                from unittest.mock import MagicMock as MM
                m = MM()
                m.returncode = 0
                return m
            return original_run(cmd, *a, **kw)

        with patch("subprocess.run", side_effect=selective_run):
            cmd_stop(args)
        assert marker.exists(), "onstop hook did not run"
        assert marker.read_text().strip() == "onstop"
