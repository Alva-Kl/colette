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
        # Kills standard, copilot and logs sessions
        killed = [c[0][0][3] for c in mock_run.call_args_list]
        assert "proj" in killed
        assert "proj-copilot" in killed
        assert "proj-logs" in killed

    def test_stop_tmux_call_uses_capture_output(self, tmp_config):
        """tmux kill-session must use capture_output=True to avoid tty pollution."""
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
        for call in mock_run.call_args_list:
            assert call[1].get("capture_output") is True

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


# ---------------------------------------------------------------------------
# TestCmdMonitor
# ---------------------------------------------------------------------------

class TestCmdMonitor:
    def _std_args(self):
        """Return a MagicMock args for standard monitor mode (no --copilot/--all)."""
        args = MagicMock(machine=None, projects=[])
        args.copilot = False
        args.all = False
        return args

    def test_monitor_only_shows_active_sessions(self, tmp_config):
        """Only projects with an active tmux session appear in the monitor window."""
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_projects([
            make_project("active-proj", path="/tmp/active"),
            make_project("idle-proj", path="/tmp/idle"),
        ])
        args = self._std_args()

        with patch("colette_cli.session.commands.get_sessions", return_value={"active-proj"}), \
             patch("colette_cli.session.commands.create_tmux_window_with_panes") as mock_panes, \
             patch("subprocess.run"):
            cmd_monitor(args)

        active_list = mock_panes.call_args[0][1]
        active_names = [p["name"] for p, _ in active_list]
        assert "active-proj" in active_names
        assert "idle-proj" not in active_names

    def test_monitor_does_not_create_new_sessions(self, tmp_config):
        """Monitor must NOT start new tmux sessions for idle projects."""
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_projects([make_project("idle-proj", path="/tmp/idle")])
        args = self._std_args()

        with patch("colette_cli.session.commands.get_sessions", return_value=set()), \
             patch("subprocess.run") as mock_run, \
             patch("colette_cli.session.commands.create_tmux_window_with_panes"):
            # Should raise SystemExit because no active sessions → err()
            with pytest.raises(SystemExit):
                cmd_monitor(args)

        # subprocess.run should NOT have been called to create a tmux session
        tmux_new = [c for c in mock_run.call_args_list
                    if c[0] and "new-session" in c[0][0]]
        assert not tmux_new, "monitor should not create new sessions"

    def test_monitor_exits_when_no_active_sessions(self, tmp_config):
        """cmd_monitor exits with an error when no sessions are active."""
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        args = self._std_args()

        with patch("colette_cli.session.commands.get_sessions", return_value=set()), \
             patch("colette_cli.session.commands.create_tmux_window_with_panes"):
            with pytest.raises(SystemExit):
                cmd_monitor(args)

    def test_monitor_blocked_from_monitor_session(self, tmp_config):
        """cmd_monitor exits when run from within the colette-monitor session."""
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        args = self._std_args()

        with patch("colette_cli.session.commands._get_current_tmux_session", return_value="colette-monitor"):
            with pytest.raises(SystemExit):
                cmd_monitor(args)

    def test_monitor_blocked_from_project_session(self, tmp_config):
        """cmd_monitor exits when run from within a registered colette project session."""
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_projects([make_project("my-proj", path="/tmp/my-proj")])
        args = self._std_args()

        with patch("colette_cli.session.commands._get_current_tmux_session", return_value="my-proj"):
            with pytest.raises(SystemExit):
                cmd_monitor(args)

    def test_monitor_allowed_outside_tmux(self, tmp_config):
        """cmd_monitor proceeds normally when not inside a tmux session."""
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_projects([make_project("proj", path="/tmp/proj")])
        args = self._std_args()

        with patch("colette_cli.session.commands._get_current_tmux_session", return_value=None), \
             patch("colette_cli.session.commands.get_sessions", return_value={"proj"}), \
             patch("colette_cli.session.commands.create_tmux_window_with_panes") as mock_panes:
            cmd_monitor(args)

        mock_panes.assert_called_once()

    def test_monitor_allowed_from_unrelated_tmux_session(self, tmp_config):
        """cmd_monitor proceeds normally when run from an unrelated tmux session."""
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_projects([make_project("proj", path="/tmp/proj")])
        args = self._std_args()

        with patch("colette_cli.session.commands._get_current_tmux_session", return_value="unrelated-session"), \
             patch("colette_cli.session.commands.get_sessions", return_value={"proj"}), \
             patch("colette_cli.session.commands.create_tmux_window_with_panes") as mock_panes:
            cmd_monitor(args)

        mock_panes.assert_called_once()

    def test_monitor_copilot_shows_copilot_sessions(self, tmp_config):
        """--copilot flag shows <project>-copilot sessions, not standard ones."""
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_projects([
            make_project("proj-a", path="/tmp/a"),
            make_project("proj-b", path="/tmp/b"),
        ])
        args = MagicMock(machine=None, projects=[])
        args.copilot = True
        args.all = False

        # proj-a has a copilot session, proj-b does not
        with patch("colette_cli.session.commands._get_current_tmux_session", return_value=None), \
             patch("colette_cli.session.commands.get_sessions", return_value={"proj-a-copilot"}), \
             patch("colette_cli.session.commands.create_tmux_window_with_panes") as mock_panes:
            cmd_monitor(args)

        active_list = mock_panes.call_args[0][1]
        active_names = [p["name"] for p, _ in active_list]
        assert "proj-a" in active_names
        assert "proj-b" not in active_names

    def test_monitor_copilot_exits_when_no_copilot_sessions(self, tmp_config):
        """--copilot exits when no copilot sessions are active."""
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_projects([make_project("proj", path="/tmp/proj")])
        args = MagicMock(machine=None, projects=[])
        args.copilot = True
        args.all = False

        with patch("colette_cli.session.commands._get_current_tmux_session", return_value=None), \
             patch("colette_cli.session.commands.get_sessions", return_value={"proj"}), \
             patch("colette_cli.session.commands.create_tmux_window_with_panes"):
            with pytest.raises(SystemExit):
                cmd_monitor(args)

    def test_monitor_all_groups_sessions_by_project(self, tmp_config):
        """--all groups standard + copilot + logs sessions per project as rows."""
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_projects([
            make_project("proj-a", path="/tmp/a"),
            make_project("proj-b", path="/tmp/b"),
        ])
        args = MagicMock(machine=None, projects=[])
        args.copilot = False
        args.all = True

        active_sessions = {"proj-a", "proj-a-copilot", "proj-a-logs", "proj-b"}

        with patch("colette_cli.session.commands._get_current_tmux_session", return_value=None), \
             patch("colette_cli.session.commands.get_sessions", return_value=active_sessions), \
             patch("colette_cli.session.commands.create_tmux_window_with_rows") as mock_rows:
            cmd_monitor(args)

        mock_rows.assert_called_once()
        project_rows = mock_rows.call_args[0][1]
        row_map = {proj["name"]: sessions for proj, sessions in project_rows}

        assert "proj-a" in row_map
        assert "proj-b" in row_map
        # proj-a has 3 sessions (standard, copilot, logs)
        assert len(row_map["proj-a"]) == 3
        labels_a = [lbl for lbl, _ in row_map["proj-a"]]
        assert "standard" in labels_a
        assert "copilot" in labels_a
        assert "logs" in labels_a
        # proj-b has only 1 session (standard)
        assert len(row_map["proj-b"]) == 1

    def test_monitor_all_exits_when_no_sessions(self, tmp_config):
        """--all exits when no sessions of any kind are active."""
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        args = MagicMock(machine=None, projects=[])
        args.copilot = False
        args.all = True

        with patch("colette_cli.session.commands._get_current_tmux_session", return_value=None), \
             patch("colette_cli.session.commands.get_sessions", return_value=set()), \
             patch("colette_cli.session.commands.create_tmux_window_with_rows"):
            with pytest.raises(SystemExit):
                cmd_monitor(args)
