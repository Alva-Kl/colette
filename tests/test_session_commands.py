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
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_start
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj", path="/tmp")])
        args = MagicMock(machine=None, projects=[])
        with (
            patch("colette_cli.session.commands.ensure_session", return_value=True) as mock_ensure,
            patch("colette_cli.session.commands.run_template_hook", return_value=True),
        ):
            cmd_start(args)
        mock_ensure.assert_called_once()

    def test_onstart_hook_runs_on_start(self, tmp_config, tmp_path):
        """The onstart hook actually executes when cmd_start is called."""
        from colette_cli.utils.config import save_config, save_local_projects, write_machine_template_hook
        from colette_cli.session.commands import cmd_start
        marker = tmp_path / "marker.txt"
        write_machine_template_hook("local", "tmpl", "onstart", f"#!/usr/bin/env bash\necho onstart > {marker}")
        save_config({
            "machines": {"local": make_local_machine(str(tmp_path))},
            "default_machine": "local",
        })
        save_local_projects([make_project("proj", path=str(tmp_path), template="tmpl")])
        args = MagicMock(machine=None, projects=[])
        with patch("colette_cli.session.commands.ensure_session", return_value=True):
            cmd_start(args)
        assert marker.exists(), "onstart hook did not run"
        assert marker.read_text().strip() == "onstart"

    def test_filters_by_machine(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_start
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj", path="/tmp")])
        args = MagicMock(machine="nonexistent", projects=[])
        with pytest.raises(SystemExit):
            cmd_start(args)


class TestCmdStop:
    def test_no_projects_prints_message(self, tmp_config, capsys):
        from colette_cli.session.commands import cmd_stop
        cmd_stop(MagicMock(machine=None, projects=[]))
        assert "No projects" in capsys.readouterr().out

    def test_stops_local_session(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_stop
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj", path="/tmp")])
        args = MagicMock(machine=None, projects=[])
        with (
            patch("colette_cli.session.commands.run_template_hook", return_value=True),
            patch("subprocess.run") as mock_run,
        ):
            cmd_stop(args)
        # Kills standard, agent and logs sessions
        killed = [c[0][0][3] for c in mock_run.call_args_list]
        assert "proj" in killed
        assert "proj-agent" in killed
        assert "proj-logs" in killed

    def test_stop_tmux_call_uses_capture_output(self, tmp_config):
        """tmux kill-session must use capture_output=True to avoid tty pollution."""
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_stop
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj", path="/tmp")])
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
        from colette_cli.utils.config import save_config, save_local_projects, write_machine_template_hook
        from colette_cli.session.commands import cmd_stop
        marker = tmp_path / "marker.txt"
        write_machine_template_hook("local", "tmpl", "onstop", f"#!/usr/bin/env bash\necho onstop > {marker}")
        save_config({
            "machines": {"local": make_local_machine(str(tmp_path))},
            "default_machine": "local",
        })
        save_local_projects([make_project("proj", path=str(tmp_path), template="tmpl")])
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
        """Return a MagicMock args for standard monitor mode (no --agent/--all)."""
        args = MagicMock(machine=None, projects=[])
        args.agent = False
        args.all = False
        return args

    def test_monitor_only_shows_active_sessions(self, tmp_config):
        """Only projects with an active tmux session appear in the monitor window."""
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_local_projects([
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
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_local_projects([make_project("idle-proj", path="/tmp/idle")])
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
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj")])
        args = self._std_args()

        with patch("colette_cli.session.commands.get_sessions", return_value=set()), \
             patch("colette_cli.session.commands.create_tmux_window_with_panes"):
            with pytest.raises(SystemExit):
                cmd_monitor(args)

    def test_monitor_blocked_from_monitor_session(self, tmp_config):
        """cmd_monitor exits when run from within the colette-monitor session."""
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj")])
        args = self._std_args()

        with patch("colette_cli.session.commands._get_current_tmux_session", return_value="colette-monitor"):
            with pytest.raises(SystemExit):
                cmd_monitor(args)

    def test_monitor_remote_machine_uses_ssh_attach_command(self, tmp_config):
        """Standard monitor mode against an ssh-type machine builds an SSH
        attach command via _build_ssh_attach_command, not a bare tmux one."""
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_monitor
        save_config({
            "machines": {"remote": {"type": "ssh", "host": "user@remote-host", "projects_dir": "/home/user"}},
            "default_machine": "remote",
        })
        save_local_projects([make_project("proj", machine="remote", path="/home/user/proj")])
        args = self._std_args()

        with patch("colette_cli.session.commands.get_sessions", return_value={"proj"}), \
             patch("colette_cli.session.commands.create_tmux_window_with_panes") as mock_panes:
            cmd_monitor(args)

        active_list = mock_panes.call_args[0][1]
        assert len(active_list) == 1
        _, wrapped_cmd = active_list[0]
        assert "ssh" in wrapped_cmd
        assert "user@remote-host" in wrapped_cmd

    def test_monitor_blocked_from_project_session(self, tmp_config):
        """cmd_monitor exits when run from within a registered colette project session."""
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_local_projects([make_project("my-proj", path="/tmp/my-proj")])
        args = self._std_args()

        with patch("colette_cli.session.commands._get_current_tmux_session", return_value="my-proj"):
            with pytest.raises(SystemExit):
                cmd_monitor(args)

    def test_monitor_allowed_outside_tmux(self, tmp_config):
        """cmd_monitor proceeds normally when not inside a tmux session."""
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj", path="/tmp/proj")])
        args = self._std_args()

        with patch("colette_cli.session.commands._get_current_tmux_session", return_value=None), \
             patch("colette_cli.session.commands.get_sessions", return_value={"proj"}), \
             patch("colette_cli.session.commands.create_tmux_window_with_panes") as mock_panes:
            cmd_monitor(args)

        mock_panes.assert_called_once()

    def test_monitor_allowed_from_unrelated_tmux_session(self, tmp_config):
        """cmd_monitor proceeds normally when run from an unrelated tmux session."""
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj", path="/tmp/proj")])
        args = self._std_args()

        with patch("colette_cli.session.commands._get_current_tmux_session", return_value="unrelated-session"), \
             patch("colette_cli.session.commands.get_sessions", return_value={"proj"}), \
             patch("colette_cli.session.commands.create_tmux_window_with_panes") as mock_panes:
            cmd_monitor(args)

        mock_panes.assert_called_once()

    def test_monitor_agent_shows_agent_sessions(self, tmp_config):
        """--agent flag shows <project>-agent sessions, not standard ones."""
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_local_projects([
            make_project("proj-a", path="/tmp/a"),
            make_project("proj-b", path="/tmp/b"),
        ])
        args = MagicMock(machine=None, projects=[])
        args.agent = True
        args.all = False

        # proj-a has an agent session, proj-b does not
        with patch("colette_cli.session.commands._get_current_tmux_session", return_value=None), \
             patch("colette_cli.session.commands.get_sessions", return_value={"proj-a-agent"}), \
             patch("colette_cli.session.commands.create_tmux_window_with_panes") as mock_panes:
            cmd_monitor(args)

        active_list = mock_panes.call_args[0][1]
        active_names = [p["name"] for p, _ in active_list]
        assert "proj-a" in active_names
        assert "proj-b" not in active_names

    def test_monitor_agent_exits_when_no_agent_sessions(self, tmp_config):
        """--agent exits when no agent sessions are active."""
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj", path="/tmp/proj")])
        args = MagicMock(machine=None, projects=[])
        args.agent = True
        args.all = False

        with patch("colette_cli.session.commands._get_current_tmux_session", return_value=None), \
             patch("colette_cli.session.commands.get_sessions", return_value={"proj"}), \
             patch("colette_cli.session.commands.create_tmux_window_with_panes"):
            with pytest.raises(SystemExit):
                cmd_monitor(args)

    def test_monitor_all_groups_sessions_by_project(self, tmp_config):
        """--all groups standard + agent + logs sessions per project as rows."""
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_local_projects([
            make_project("proj-a", path="/tmp/a"),
            make_project("proj-b", path="/tmp/b"),
        ])
        args = MagicMock(machine=None, projects=[])
        args.agent = False
        args.all = True

        active_sessions = {"proj-a", "proj-a-agent", "proj-a-logs", "proj-b"}

        with patch("colette_cli.session.commands._get_current_tmux_session", return_value=None), \
             patch("colette_cli.session.commands.get_sessions", return_value=active_sessions), \
             patch("colette_cli.session.commands.create_tmux_window_with_rows") as mock_rows:
            cmd_monitor(args)

        mock_rows.assert_called_once()
        project_rows = mock_rows.call_args[0][1]
        row_map = {proj["name"]: sessions for proj, sessions in project_rows}

        assert "proj-a" in row_map
        assert "proj-b" in row_map
        # proj-a has 3 sessions (standard, agent, logs)
        assert len(row_map["proj-a"]) == 3
        labels_a = [lbl for lbl, _ in row_map["proj-a"]]
        assert "standard" in labels_a
        assert "agent" in labels_a
        assert "logs" in labels_a
        # proj-b has only 1 session (standard)
        assert len(row_map["proj-b"]) == 1

    def test_monitor_all_exits_when_no_sessions(self, tmp_config):
        """--all exits when no sessions of any kind are active."""
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_monitor
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj")])
        args = MagicMock(machine=None, projects=[])
        args.agent = False
        args.all = True

        with patch("colette_cli.session.commands._get_current_tmux_session", return_value=None), \
             patch("colette_cli.session.commands.get_sessions", return_value=set()), \
             patch("colette_cli.session.commands.create_tmux_window_with_rows"):
            with pytest.raises(SystemExit):
                cmd_monitor(args)


# ---------------------------------------------------------------------------
# TestCmdUpdate
# ---------------------------------------------------------------------------

class TestCmdUpdate:
    def test_no_projects_prints_message(self, tmp_config, capsys):
        from colette_cli.session.commands import cmd_update
        cmd_update(MagicMock(machine=None, projects=[]))
        assert "No projects" in capsys.readouterr().out

    def test_calls_onupdate_hook(self, tmp_config):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_update
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj", path="/tmp")])
        args = MagicMock(machine=None, projects=[])
        with patch("colette_cli.session.commands.run_template_hook", return_value=True) as mock_hook:
            cmd_update(args)
        mock_hook.assert_called_once()
        assert mock_hook.call_args[0][5] == "onupdate"

    def test_onupdate_hook_actually_runs(self, tmp_config, tmp_path):
        """The onupdate hook executes when cmd_update is called."""
        from colette_cli.utils.config import save_config, save_local_projects, write_machine_template_hook
        from colette_cli.session.commands import cmd_update
        marker = tmp_path / "marker.txt"
        write_machine_template_hook("local", "tmpl", "onupdate", f"#!/usr/bin/env bash\necho onupdate > {marker}")
        save_config({
            "machines": {"local": make_local_machine(str(tmp_path))},
            "default_machine": "local",
        })
        save_local_projects([make_project("proj", path=str(tmp_path), template="tmpl")])
        args = MagicMock(machine=None, projects=[])
        cmd_update(args)
        assert marker.exists(), "onupdate hook did not run"
        assert marker.read_text().strip() == "onupdate"

    def test_filters_by_machine(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_update
        save_config(LOCAL_CFG)
        save_local_projects([make_project("proj", path="/tmp")])
        args = MagicMock(machine="nonexistent", projects=[])
        with pytest.raises(SystemExit):
            cmd_update(args)


class TestCmdUpdateCwdDetection:
    """Tests for CWD-based project detection in 'colette update' via main()."""

    def _setup(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        project_path = tmp_path / "myproject"
        project_path.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([make_project("myproject", path=str(project_path))])
        return project_path

    def test_main_targets_cwd_project_when_no_args(self, tmp_config, tmp_path):
        """main() sets args.projects to [cwd project] when update is run without args."""
        import os, sys
        project_path = self._setup(tmp_config, tmp_path)
        orig = os.getcwd()
        try:
            os.chdir(str(project_path))
            with patch.object(sys, "argv", ["colette", "update"]), \
                 patch("colette_cli.main.cmd_update") as mock_update:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_update.assert_called_once()
        resolved_args = mock_update.call_args[0][0]
        assert resolved_args.projects == ["myproject"]

    def test_main_updates_all_when_not_in_project_dir(self, tmp_config, tmp_path):
        """main() leaves args.projects empty (all projects) when cwd is not a project."""
        import os, sys
        self._setup(tmp_config, tmp_path)
        unregistered = tmp_path / "other"
        unregistered.mkdir()
        orig = os.getcwd()
        try:
            os.chdir(str(unregistered))
            with patch.object(sys, "argv", ["colette", "update"]), \
                 patch("colette_cli.main.cmd_update") as mock_update:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_update.assert_called_once()
        resolved_args = mock_update.call_args[0][0]
        assert resolved_args.projects == []

    def test_main_explicit_project_name_bypasses_cwd(self, tmp_config, tmp_path):
        """main() respects explicit project names even when cwd is a different project."""
        import os, sys
        from colette_cli.utils.config import save_config, save_local_projects
        project_a = tmp_path / "proj-a"
        project_a.mkdir()
        project_b = tmp_path / "proj-b"
        project_b.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([
            make_project("proj-a", path=str(project_a)),
            make_project("proj-b", path=str(project_b)),
        ])
        orig = os.getcwd()
        try:
            os.chdir(str(project_a))
            with patch.object(sys, "argv", ["colette", "update", "proj-b"]), \
                 patch("colette_cli.main.cmd_update") as mock_update:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_update.assert_called_once()
        resolved_args = mock_update.call_args[0][0]
        assert resolved_args.projects == ["proj-b"]



class TestCwdDetectStart:
    """Tests for CWD-based project detection in 'colette start' via main()."""

    def _setup(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        project_path = tmp_path / "myproject"
        project_path.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([make_project("myproject", path=str(project_path))])
        return project_path

    def test_main_targets_cwd_project_when_no_args(self, tmp_config, tmp_path):
        """main() sets args.projects to [cwd project] when start is run without args."""
        import os, sys
        project_path = self._setup(tmp_config, tmp_path)
        orig = os.getcwd()
        try:
            os.chdir(str(project_path))
            with patch.object(sys, "argv", ["colette", "start"]), \
                 patch("colette_cli.main.cmd_start") as mock_start:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_start.assert_called_once()
        assert mock_start.call_args[0][0].projects == ["myproject"]

    def test_main_starts_all_when_not_in_project_dir(self, tmp_config, tmp_path):
        """main() leaves args.projects empty (all projects) when cwd is not a project."""
        import os, sys
        self._setup(tmp_config, tmp_path)
        unregistered = tmp_path / "other"
        unregistered.mkdir()
        orig = os.getcwd()
        try:
            os.chdir(str(unregistered))
            with patch.object(sys, "argv", ["colette", "start"]), \
                 patch("colette_cli.main.cmd_start") as mock_start:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_start.assert_called_once()
        assert mock_start.call_args[0][0].projects == []

    def test_main_explicit_project_bypasses_cwd(self, tmp_config, tmp_path):
        """main() respects explicit project names even when cwd is a different project."""
        import os, sys
        from colette_cli.utils.config import save_config, save_local_projects
        proj_a = tmp_path / "proj-a"
        proj_a.mkdir()
        proj_b = tmp_path / "proj-b"
        proj_b.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([
            make_project("proj-a", path=str(proj_a)),
            make_project("proj-b", path=str(proj_b)),
        ])
        orig = os.getcwd()
        try:
            os.chdir(str(proj_a))
            with patch.object(sys, "argv", ["colette", "start", "proj-b"]), \
                 patch("colette_cli.main.cmd_start") as mock_start:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_start.assert_called_once()
        assert mock_start.call_args[0][0].projects == ["proj-b"]


class TestCwdDetectStop:
    """Tests for CWD-based project detection in 'colette stop' via main()."""

    def _setup(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        project_path = tmp_path / "myproject"
        project_path.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([make_project("myproject", path=str(project_path))])
        return project_path

    def test_main_targets_cwd_project_when_no_args(self, tmp_config, tmp_path):
        """main() sets args.projects to [cwd project] when stop is run without args."""
        import os, sys
        project_path = self._setup(tmp_config, tmp_path)
        orig = os.getcwd()
        try:
            os.chdir(str(project_path))
            with patch.object(sys, "argv", ["colette", "stop"]), \
                 patch("colette_cli.main.cmd_stop") as mock_stop:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_stop.assert_called_once()
        assert mock_stop.call_args[0][0].projects == ["myproject"]

    def test_main_stops_all_when_not_in_project_dir(self, tmp_config, tmp_path):
        """main() leaves args.projects empty (all projects) when cwd is not a project."""
        import os, sys
        self._setup(tmp_config, tmp_path)
        unregistered = tmp_path / "other"
        unregistered.mkdir()
        orig = os.getcwd()
        try:
            os.chdir(str(unregistered))
            with patch.object(sys, "argv", ["colette", "stop"]), \
                 patch("colette_cli.main.cmd_stop") as mock_stop:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_stop.assert_called_once()
        assert mock_stop.call_args[0][0].projects == []

    def test_main_explicit_project_bypasses_cwd(self, tmp_config, tmp_path):
        """main() respects explicit project names even when cwd is a different project."""
        import os, sys
        from colette_cli.utils.config import save_config, save_local_projects
        proj_a = tmp_path / "proj-a"
        proj_a.mkdir()
        proj_b = tmp_path / "proj-b"
        proj_b.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([
            make_project("proj-a", path=str(proj_a)),
            make_project("proj-b", path=str(proj_b)),
        ])
        orig = os.getcwd()
        try:
            os.chdir(str(proj_a))
            with patch.object(sys, "argv", ["colette", "stop", "proj-b"]), \
                 patch("colette_cli.main.cmd_stop") as mock_stop:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_stop.assert_called_once()
        assert mock_stop.call_args[0][0].projects == ["proj-b"]


class TestCwdDetectMonitor:
    """Tests for CWD-based project detection in 'colette monitor' via main()."""

    def _setup(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        project_path = tmp_path / "myproject"
        project_path.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([make_project("myproject", path=str(project_path))])
        return project_path

    def test_main_targets_cwd_project_when_no_args(self, tmp_config, tmp_path):
        """main() sets args.projects to [cwd project] when monitor is run without args."""
        import os, sys
        project_path = self._setup(tmp_config, tmp_path)
        orig = os.getcwd()
        try:
            os.chdir(str(project_path))
            with patch.object(sys, "argv", ["colette", "monitor"]), \
                 patch("colette_cli.main.cmd_monitor") as mock_monitor:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_monitor.assert_called_once()
        assert mock_monitor.call_args[0][0].projects == ["myproject"]

    def test_main_monitors_all_when_not_in_project_dir(self, tmp_config, tmp_path):
        """main() leaves args.projects empty (all projects) when cwd is not a project."""
        import os, sys
        self._setup(tmp_config, tmp_path)
        unregistered = tmp_path / "other"
        unregistered.mkdir()
        orig = os.getcwd()
        try:
            os.chdir(str(unregistered))
            with patch.object(sys, "argv", ["colette", "monitor"]), \
                 patch("colette_cli.main.cmd_monitor") as mock_monitor:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_monitor.assert_called_once()
        assert mock_monitor.call_args[0][0].projects == []

    def test_main_explicit_project_bypasses_cwd(self, tmp_config, tmp_path):
        """main() respects explicit project names even when cwd is a different project."""
        import os, sys
        from colette_cli.utils.config import save_config, save_local_projects
        proj_a = tmp_path / "proj-a"
        proj_a.mkdir()
        proj_b = tmp_path / "proj-b"
        proj_b.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([
            make_project("proj-a", path=str(proj_a)),
            make_project("proj-b", path=str(proj_b)),
        ])
        orig = os.getcwd()
        try:
            os.chdir(str(proj_a))
            with patch.object(sys, "argv", ["colette", "monitor", "proj-b"]), \
                 patch("colette_cli.main.cmd_monitor") as mock_monitor:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_monitor.assert_called_once()
        assert mock_monitor.call_args[0][0].projects == ["proj-b"]


class TestCwdDetectLogs:
    """Tests for CWD-based project detection in 'colette logs' via main()."""

    def _setup(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        project_path = tmp_path / "myproject"
        project_path.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([make_project("myproject", path=str(project_path))])
        return project_path

    def test_main_targets_cwd_project_when_no_args(self, tmp_config, tmp_path):
        """main() sets args.name to cwd project when logs is run without args."""
        import os, sys
        project_path = self._setup(tmp_config, tmp_path)
        orig = os.getcwd()
        try:
            os.chdir(str(project_path))
            with patch.object(sys, "argv", ["colette", "logs"]), \
                 patch("colette_cli.main.cmd_logs") as mock_logs:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_logs.assert_called_once()
        assert mock_logs.call_args[0][0].name == "myproject"

    def test_main_leaves_name_none_when_not_in_project_dir(self, tmp_config, tmp_path):
        """main() leaves args.name as None (all-projects mode) when cwd is not a project."""
        import os, sys
        self._setup(tmp_config, tmp_path)
        unregistered = tmp_path / "other"
        unregistered.mkdir()
        orig = os.getcwd()
        try:
            os.chdir(str(unregistered))
            with patch.object(sys, "argv", ["colette", "logs"]), \
                 patch("colette_cli.main.cmd_logs") as mock_logs:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_logs.assert_called_once()
        assert mock_logs.call_args[0][0].name is None

    def test_main_explicit_name_bypasses_cwd(self, tmp_config, tmp_path):
        """main() respects explicit name even when cwd is a different project."""
        import os, sys
        from colette_cli.utils.config import save_config, save_local_projects
        proj_a = tmp_path / "proj-a"
        proj_a.mkdir()
        proj_b = tmp_path / "proj-b"
        proj_b.mkdir()
        cfg = {"machines": {"local": make_local_machine()}, "default_machine": "local"}
        save_config(cfg)
        save_local_projects([
            make_project("proj-a", path=str(proj_a)),
            make_project("proj-b", path=str(proj_b)),
        ])
        orig = os.getcwd()
        try:
            os.chdir(str(proj_a))
            with patch.object(sys, "argv", ["colette", "logs", "proj-b"]), \
                 patch("colette_cli.main.cmd_logs") as mock_logs:
                from colette_cli.main import main
                main()
        finally:
            os.chdir(orig)

        mock_logs.assert_called_once()
        assert mock_logs.call_args[0][0].name == "proj-b"


class TestCmdLogs:
    def test_single_project_no_onlogs_hook_exits(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_logs
        save_config({"machines": {"local": make_local_machine(str(tmp_path))}, "default_machine": "local"})
        save_local_projects([make_project("proj", path=str(tmp_path))])
        args = MagicMock()
        args.name = "proj"
        with pytest.raises(SystemExit):
            cmd_logs(args)

    def test_single_project_local_opens_tmux_session(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects, write_project_hook
        from colette_cli.session.commands import cmd_logs
        save_config({"machines": {"local": make_local_machine(str(tmp_path))}, "default_machine": "local"})
        save_local_projects([make_project("proj", path=str(tmp_path))])
        write_project_hook("proj", "onlogs", "#!/usr/bin/env bash\ntail -f log")
        args = MagicMock()
        args.name = "proj"

        with patch("colette_cli.session.commands.local_tmux_session") as mock_tmux:
            cmd_logs(args)

        mock_tmux.assert_called_once()
        assert mock_tmux.call_args[0][0] == "proj-logs"
        assert "tail -f log" in mock_tmux.call_args[0][2]

    def test_single_project_remote_uses_ssh_interactive(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_logs
        save_config({
            "machines": {"remote": {"type": "ssh", "host": "user@host", "projects_dir": str(tmp_path)}},
            "default_machine": "remote",
        })
        save_local_projects([make_project("proj", machine="remote", path=str(tmp_path))])
        args = MagicMock()
        args.name = "proj"

        remote_hooks = {
            "onlogs": {"project": "#!/usr/bin/env bash\ntail -f log", "template": None},
        }
        with patch("colette_cli.utils.ssh.ssh_read_hook_files", return_value=remote_hooks), \
             patch("colette_cli.session.commands.ssh_interactive") as mock_ssh:
            cmd_logs(args)

        mock_ssh.assert_called_once()
        tmux_cmd = mock_ssh.call_args[0][1]
        assert "proj-logs" in tmux_cmd

    def test_all_projects_no_active_hooks_exits(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.session.commands import cmd_logs
        save_config({"machines": {"local": make_local_machine(str(tmp_path))}, "default_machine": "local"})
        save_local_projects([make_project("proj", path=str(tmp_path))])
        args = MagicMock(machine=None)
        args.name = None
        with pytest.raises(SystemExit):
            cmd_logs(args)

    def test_all_projects_creates_panes_only_for_active(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_local_projects, write_project_hook
        from colette_cli.session.commands import cmd_logs
        save_config({"machines": {"local": make_local_machine(str(tmp_path))}, "default_machine": "local"})
        save_local_projects([
            make_project("has-logs", path=str(tmp_path)),
            make_project("no-logs", path=str(tmp_path)),
        ])
        write_project_hook("has-logs", "onlogs", "#!/usr/bin/env bash\ntail -f log")
        args = MagicMock(machine=None)
        args.name = None

        with patch("colette_cli.session.commands.create_tmux_window_with_panes") as mock_panes:
            cmd_logs(args)

        mock_panes.assert_called_once()
        active_names = [p["name"] for p, _ in mock_panes.call_args[0][1]]
        assert active_names == ["has-logs"]

    def test_all_projects_no_projects_at_all_prints_message(self, tmp_config, capsys):
        from colette_cli.utils.config import save_config
        from colette_cli.session.commands import cmd_logs
        save_config(LOCAL_CFG)
        args = MagicMock(machine=None)
        args.name = None
        cmd_logs(args)
        assert "No projects" in capsys.readouterr().out
