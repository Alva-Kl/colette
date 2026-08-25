"""Tests for colette_cli.utils.tmux."""

import pytest
from unittest.mock import patch, MagicMock


class TestEnsureSessionRemote:
    def test_warns_when_tmux_new_session_fails(self, capsys):
        from colette_cli.utils.tmux import _ensure_session_remote

        project = {"name": "myproj", "path": "/p/myproj"}
        machine = {"type": "ssh", "host": "myhost"}

        has_session_result = MagicMock()
        has_session_result.returncode = 0
        has_session_result.stdout = "no\n"

        fail_result = MagicMock()
        fail_result.returncode = 1
        fail_result.stdout = ""
        fail_result.stderr = "tmux: unknown command"

        call_count = 0
        def fake_ssh_run(m, cmd):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return has_session_result
            return fail_result

        with patch("colette_cli.utils.tmux.ssh_run", side_effect=fake_ssh_run):
            result = _ensure_session_remote(project, machine)

        assert result is True  # still returns True (attempted creation)
        assert "failed to create remote tmux session" in capsys.readouterr().err

    def test_no_warning_when_session_creation_succeeds(self, capsys):
        from colette_cli.utils.tmux import _ensure_session_remote

        project = {"name": "myproj", "path": "/p/myproj"}
        machine = {"type": "ssh", "host": "myhost"}

        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = "no\n"

        with patch("colette_cli.utils.tmux.ssh_run", return_value=ok):
            result = _ensure_session_remote(project, machine)

        assert result is True
        assert capsys.readouterr().err == ""

    def test_returns_false_when_session_already_exists(self):
        from colette_cli.utils.tmux import _ensure_session_remote

        project = {"name": "myproj", "path": "/p/myproj"}
        machine = {"type": "ssh", "host": "myhost"}
        already = MagicMock(returncode=0, stdout="yes\n")

        with patch("colette_cli.utils.tmux.ssh_run", return_value=already) as mock_ssh:
            result = _ensure_session_remote(project, machine)

        assert result is False
        mock_ssh.assert_called_once()


class TestEnsureSessionLocal:
    def test_creates_new_session_when_absent(self):
        from colette_cli.utils.tmux import _ensure_session_local

        project = {"name": "myproj", "path": "/tmp/myproj"}
        has_session_fail = MagicMock(returncode=1)

        with patch("subprocess.run", return_value=has_session_fail) as mock_run:
            result = _ensure_session_local(project, "exec bash")

        assert result is True
        new_session_calls = [c for c in mock_run.call_args_list if "new-session" in c.args[0]]
        assert len(new_session_calls) == 1
        assert "myproj" in new_session_calls[0].args[0]

    def test_returns_false_when_session_already_exists(self):
        from colette_cli.utils.tmux import _ensure_session_local

        project = {"name": "myproj", "path": "/tmp/myproj"}
        has_session_ok = MagicMock(returncode=0)

        with patch("subprocess.run", return_value=has_session_ok) as mock_run:
            result = _ensure_session_local(project)

        assert result is False
        assert mock_run.call_count == 1  # only the has-session check, no new-session


class TestEnsureSession:
    def test_dispatches_to_remote_when_is_remote_true(self):
        from colette_cli.utils.tmux import ensure_session
        with patch("colette_cli.utils.tmux._ensure_session_remote", return_value=True) as mock_remote, \
             patch("colette_cli.utils.tmux._ensure_session_local") as mock_local:
            result = ensure_session({"name": "p"}, {"type": "ssh"}, True)
        assert result is True
        mock_remote.assert_called_once()
        mock_local.assert_not_called()

    def test_dispatches_to_local_when_is_remote_false(self):
        from colette_cli.utils.tmux import ensure_session
        with patch("colette_cli.utils.tmux._ensure_session_remote") as mock_remote, \
             patch("colette_cli.utils.tmux._ensure_session_local", return_value=False) as mock_local:
            result = ensure_session({"name": "p"}, {"type": "local"}, False)
        assert result is False
        mock_local.assert_called_once()
        mock_remote.assert_not_called()


class TestGetSessions:
    def test_local_parses_session_names(self):
        from colette_cli.utils.tmux import get_sessions
        ok = MagicMock(returncode=0, stdout="proj-a\nproj-b\n")
        with patch("subprocess.run", return_value=ok):
            result = get_sessions({}, False)
        assert result == {"proj-a", "proj-b"}

    def test_local_returns_empty_set_on_failure(self):
        from colette_cli.utils.tmux import get_sessions
        fail = MagicMock(returncode=1, stdout="")
        with patch("subprocess.run", return_value=fail):
            result = get_sessions({}, False)
        assert result == set()

    def test_remote_parses_session_names(self):
        from colette_cli.utils.tmux import get_sessions
        ok = MagicMock(returncode=0, stdout="proj-a\nproj-b\n")
        with patch("colette_cli.utils.tmux.ssh_run", return_value=ok):
            result = get_sessions({"type": "ssh"}, True)
        assert result == {"proj-a", "proj-b"}

    def test_remote_returns_empty_set_on_failure(self):
        from colette_cli.utils.tmux import get_sessions
        fail = MagicMock(returncode=1, stdout="")
        with patch("colette_cli.utils.tmux.ssh_run", return_value=fail):
            result = get_sessions({"type": "ssh"}, True)
        assert result == set()


class TestLocalTmuxSession:
    def test_outside_tmux_creates_attach_or_create_session(self, monkeypatch):
        from colette_cli.utils.tmux import local_tmux_session
        monkeypatch.delenv("TMUX", raising=False)
        with patch("subprocess.run") as mock_run:
            local_tmux_session("my-session", "/tmp/proj", "exec bash")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["tmux", "new-session", "-A", "-s", "my-session", "-c", "/tmp/proj", "bash", "-lc", "exec bash"]

    def test_inside_tmux_switches_to_existing_session(self, monkeypatch):
        from colette_cli.utils.tmux import local_tmux_session
        monkeypatch.setenv("TMUX", "/tmp/tmux-0/default,123,0")
        switch_ok = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=switch_ok) as mock_run:
            local_tmux_session("my-session", "/tmp/proj", "exec bash")
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["tmux", "switch-client", "-t", "my-session"]

    def test_inside_tmux_creates_session_when_switch_fails(self, monkeypatch):
        from colette_cli.utils.tmux import local_tmux_session
        monkeypatch.setenv("TMUX", "/tmp/tmux-0/default,123,0")
        switch_fail = MagicMock(returncode=1)
        with patch("subprocess.run", return_value=switch_fail) as mock_run:
            local_tmux_session("my-session", "/tmp/proj", "exec bash")
        calls = mock_run.call_args_list
        assert calls[0].args[0] == ["tmux", "switch-client", "-t", "my-session"]
        assert "new-session" in calls[1].args[0]
        assert calls[2].args[0] == ["tmux", "switch-client", "-t", "my-session"]


class TestCreateTmuxWindowWithPanes:
    def test_inside_tmux_uses_new_window(self, monkeypatch):
        from colette_cli.utils.tmux import create_tmux_window_with_panes
        monkeypatch.setenv("TMUX", "/tmp/tmux-0/default,123,0")
        new_window_result = MagicMock(returncode=0, stdout="@5\n")
        active = [({"name": "proj-a"}, "tail -f a"), ({"name": "proj-b"}, "tail -f b")]

        with patch("subprocess.run", return_value=new_window_result) as mock_run:
            create_tmux_window_with_panes("colette-logs", active)

        first_call = mock_run.call_args_list[0].args[0]
        assert "new-window" in first_call
        split_calls = [c for c in mock_run.call_args_list if "split-window" in c.args[0]]
        assert len(split_calls) == 1

    def test_outside_tmux_creates_detached_session_and_attaches(self, monkeypatch):
        from colette_cli.utils.tmux import create_tmux_window_with_panes
        monkeypatch.delenv("TMUX", raising=False)
        new_session_result = MagicMock(returncode=0, stdout="@1\n")
        active = [({"name": "proj-a"}, "tail -f a")]

        with patch("subprocess.run", return_value=new_session_result) as mock_run:
            create_tmux_window_with_panes("colette-monitor", active)

        calls = [c.args[0] for c in mock_run.call_args_list]
        assert any("new-session" in c for c in calls)
        assert any("attach-session" in c for c in calls)

    def test_replace_existing_kills_prior_window_and_session(self, monkeypatch):
        from colette_cli.utils.tmux import create_tmux_window_with_panes
        monkeypatch.setenv("TMUX", "/tmp/tmux-0/default,123,0")
        ok = MagicMock(returncode=0, stdout="@1\n")
        active = [({"name": "proj-a"}, "tail -f a")]

        with patch("subprocess.run", return_value=ok) as mock_run:
            create_tmux_window_with_panes("colette-monitor", active, replace_existing=True)

        calls = [c.args[0] for c in mock_run.call_args_list]
        assert any("kill-window" in c for c in calls)
        assert any("kill-session" in c for c in calls)

    def test_disable_mouse_sets_window_option(self, monkeypatch):
        from colette_cli.utils.tmux import create_tmux_window_with_panes
        monkeypatch.setenv("TMUX", "/tmp/tmux-0/default,123,0")
        ok = MagicMock(returncode=0, stdout="@1\n")
        active = [({"name": "proj-a"}, "tail -f a")]

        with patch("subprocess.run", return_value=ok) as mock_run:
            create_tmux_window_with_panes("colette-monitor", active, disable_mouse=True)

        calls = [c.args[0] for c in mock_run.call_args_list]
        assert any("mouse" in c and "off" in c for c in calls)
