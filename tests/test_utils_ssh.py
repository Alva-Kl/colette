"""Tests for colette_cli.utils.ssh."""

import pytest
from unittest.mock import patch, MagicMock


class TestSshFlagsStr:
    def test_no_flags_returns_empty(self):
        from colette_cli.utils.ssh import ssh_flags_str
        machine = {"type": "ssh", "host": "myhost"}
        assert ssh_flags_str(machine) == ""

    def test_port_included(self):
        from colette_cli.utils.ssh import ssh_flags_str
        machine = {"type": "ssh", "host": "myhost", "port": 24}
        result = ssh_flags_str(machine)
        assert "-p" in result
        assert "24" in result

    def test_key_included(self):
        from colette_cli.utils.ssh import ssh_flags_str
        machine = {"type": "ssh", "host": "myhost", "ssh_key": "/home/user/.ssh/id_rsa"}
        result = ssh_flags_str(machine)
        assert "-i" in result
        assert "id_rsa" in result

    def test_port_and_key_both_included(self):
        from colette_cli.utils.ssh import ssh_flags_str
        machine = {"type": "ssh", "host": "myhost", "port": 2222, "ssh_key": "/key"}
        result = ssh_flags_str(machine)
        assert "-p" in result
        assert "2222" in result
        assert "-i" in result



class TestSshBaseArgsWithPort:
    def test_port_added_as_dash_p(self):
        from colette_cli.utils.ssh import _ssh_base_args
        machine = {"type": "ssh", "host": "myhost", "port": 24}
        args = _ssh_base_args(machine)
        assert "-p" in args
        assert "24" in args

    def test_no_port_no_dash_p(self):
        from colette_cli.utils.ssh import _ssh_base_args
        machine = {"type": "ssh", "host": "myhost"}
        args = _ssh_base_args(machine)
        assert "-p" not in args



class TestPushProjectEntry:
    def test_push_project_entry_merges_by_name_and_remaps_machine(self, tmp_config):
        """push_project_entry merges into the remote's own projects.json and
        rewrites "machine" to the remote's own self-name (from its config.json),
        not the controller's connection name for it."""
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import push_project_entry

        machine = {"type": "ssh", "host": "myhost"}
        project = {"name": "myproj", "machine": "remote-box", "path": "/p/myproj", "template": None}

        remote_config = {"machines": {"local": {"type": "local"}}, "default_machine": "local"}
        ok = MagicMock(returncode=0)

        def fake_ssh_run(m, cmd, extra_opts=None):
            if "config.json" in cmd:
                import json
                return MagicMock(returncode=0, stdout=json.dumps(remote_config))
            if "projects.json" in cmd:
                return MagicMock(returncode=0, stdout="[]")
            return ok

        with patch("colette_cli.utils.ssh.ssh_run", side_effect=fake_ssh_run), \
             patch("subprocess.run", return_value=ok) as mock_run:
            result = push_project_entry(machine, "remote-box", project)

        assert result is True
        write_calls = [c for c in mock_run.call_args_list if "cat >" in (c.args[0][-1] if c.args else "")]
        assert any("projects.json" in c.args[0][-1] for c in write_calls)
        json_write = next(c for c in write_calls if "projects.json" in c.args[0][-1])
        written = json_write.kwargs["input"].decode()
        assert '"machine": "local"' in written
        assert '"name": "myproj"' in written

    def test_push_project_entry_warns_when_remote_has_no_local_machine(self, tmp_config, capsys):
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import push_project_entry

        machine = {"type": "ssh", "host": "myhost"}
        project = {"name": "myproj", "machine": "remote-box", "path": "/p/myproj", "template": None}

        with patch("colette_cli.utils.ssh.ssh_run", return_value=MagicMock(returncode=0, stdout="{}")):
            result = push_project_entry(machine, "remote-box", project)

        assert result is False
        assert "no local machine entry" in capsys.readouterr().err

    def test_uses_home_variable_not_tilde(self, tmp_config):
        """Remote paths must use $HOME so the shell expands them, not literal ~."""
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import push_project_entry

        machine = {"type": "ssh", "host": "myhost"}
        project = {"name": "homechk", "machine": "remote", "path": "/p/homechk", "template": None}
        remote_config = {"machines": {"local": {"type": "local"}}, "default_machine": "local"}

        ssh_calls = []
        subprocess_calls = []

        def fake_ssh_run(m, cmd, extra_opts=None):
            ssh_calls.append(cmd)
            if "config.json" in cmd:
                import json
                return MagicMock(returncode=0, stdout=json.dumps(remote_config))
            return MagicMock(returncode=0, stdout="[]")

        def fake_subprocess_run(args, **kwargs):
            subprocess_calls.append(args[-1] if args else "")
            return MagicMock(returncode=0)

        with patch("colette_cli.utils.ssh.ssh_run", side_effect=fake_ssh_run), \
             patch("subprocess.run", side_effect=fake_subprocess_run):
            push_project_entry(machine, "remote", project)

        all_cmds = ssh_calls + subprocess_calls
        bad_cmds = [c for c in all_cmds if "'~/" in c]
        assert not bad_cmds, f"Found single-quoted tilde in remote command: {bad_cmds}"
        mkdir_cmds = [c for c in all_cmds if "mkdir" in c]
        assert all("$HOME" in c for c in mkdir_cmds), f"mkdir not using $HOME: {mkdir_cmds}"

    def test_warns_and_returns_false_on_mkdir_failure(self, tmp_config, capsys):
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import push_project_entry

        machine = {"type": "ssh", "host": "myhost"}
        project = {"name": "failproj", "machine": "remote", "path": "/p/fail", "template": None}
        remote_config = {"machines": {"local": {"type": "local"}}, "default_machine": "local"}

        def fake_ssh_run(m, cmd, extra_opts=None):
            if "config.json" in cmd:
                import json
                return MagicMock(returncode=0, stdout=json.dumps(remote_config))
            return MagicMock(returncode=1, stdout="", stderr="permission denied")

        with patch("colette_cli.utils.ssh.ssh_run", side_effect=fake_ssh_run):
            result = push_project_entry(machine, "remote", project)

        assert result is False
        assert "failed to create remote config dir" in capsys.readouterr().err



class TestRemoveRemoteProjectEntry:
    def test_remove_remote_project_entry(self, tmp_config):
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import remove_remote_project_entry

        machine = {"type": "ssh", "host": "myhost"}
        existing = [{"name": "keep-me", "machine": "local"}, {"name": "gone", "machine": "local"}]

        def fake_ssh_run(m, cmd, extra_opts=None):
            import json
            return MagicMock(returncode=0, stdout=json.dumps(existing))

        ok = MagicMock(returncode=0)
        with patch("colette_cli.utils.ssh.ssh_run", side_effect=fake_ssh_run), \
             patch("subprocess.run", return_value=ok) as mock_run:
            result = remove_remote_project_entry(machine, "remote-box", "gone")

        assert result is True
        write_call = next(c for c in mock_run.call_args_list if "cat >" in c.args[0][-1])
        written = write_call.kwargs["input"].decode()
        assert "gone" not in written
        assert "keep-me" in written


class TestPushProjectHooks:
    def test_push_project_hooks_transfers_files(self, tmp_config):
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import push_project_hooks
        from colette_cli.utils.config import PROJECT_HOOKS_DIR

        hook_dir = PROJECT_HOOKS_DIR / "myproj"
        hook_dir.mkdir(parents=True, exist_ok=True)
        (hook_dir / ".onstart").write_text("#!/bin/bash\necho hi")

        machine = {"type": "ssh", "host": "myhost"}
        ok = MagicMock(returncode=0)

        with patch("colette_cli.utils.ssh.ssh_run", return_value=ok), \
             patch("subprocess.run", return_value=ok) as mock_run:
            result = push_project_hooks(machine, "remote-box", "myproj")

        assert result is True
        write_calls = [c for c in mock_run.call_args_list if "cat >" in (c.args[0][-1] if c.args else "")]
        assert any(".onstart" in c.args[0][-1] for c in write_calls)

    def test_push_project_hooks_noop_when_no_local_dir(self, tmp_config):
        from unittest.mock import patch
        from colette_cli.utils.ssh import push_project_hooks

        machine = {"type": "ssh", "host": "myhost"}
        with patch("subprocess.run") as mock_run:
            result = push_project_hooks(machine, "remote-box", "no-such-project")

        assert result is True
        mock_run.assert_not_called()


class TestPushTemplateHooks:
    def test_push_template_hooks_writes_effective_content(self, tmp_config):
        """push_template_hooks writes the flattened, effective hook content
        (machine-override if effective, else shared template hook) per hook name."""
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import push_template_hooks
        from colette_cli.utils.config import write_machine_template_hook

        write_machine_template_hook("remote-box", "mytmpl", "onstart", "#!/bin/bash\necho machine-override")

        machine = {"type": "ssh", "host": "myhost"}
        ok = MagicMock(returncode=0)

        with patch("colette_cli.utils.ssh.ssh_run", return_value=ok), \
             patch("subprocess.run", return_value=ok) as mock_run:
            result = push_template_hooks(machine, "remote-box", "mytmpl")

        assert result is True
        write_calls = [c for c in mock_run.call_args_list if "cat >" in (c.args[0][-1] if c.args else "")]
        onstart_calls = [c for c in write_calls if c.args[0][-1].endswith(".onstart")]
        assert onstart_calls, "onstart hook was not pushed"
        assert b"machine-override" in onstart_calls[0].kwargs["input"]



class TestSshRun:
    def test_builds_correct_ssh_command(self):
        from colette_cli.utils.ssh import ssh_run
        machine = {"type": "ssh", "host": "user@host"}
        ok = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=ok) as mock_run:
            ssh_run(machine, "echo hi")
        assert mock_run.call_args.args[0] == [
            "ssh", "-o", "ConnectTimeout=15", "-o", "BatchMode=yes", "user@host", "echo hi",
        ]
        assert mock_run.call_args.kwargs["stdin"] is not None

    def test_includes_key_and_port(self):
        from colette_cli.utils.ssh import ssh_run
        machine = {"type": "ssh", "host": "user@host", "ssh_key": "/k", "port": 24}
        ok = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=ok) as mock_run:
            ssh_run(machine, "echo hi")
        cmd = mock_run.call_args.args[0]
        assert cmd == [
            "ssh", "-o", "ConnectTimeout=15", "-i", "/k", "-p", "24",
            "-o", "BatchMode=yes", "user@host", "echo hi",
        ]

    def test_extra_opts_inserted_before_host(self):
        from colette_cli.utils.ssh import ssh_run
        machine = {"type": "ssh", "host": "user@host"}
        ok = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=ok) as mock_run:
            ssh_run(machine, "echo hi", extra_opts=["-o", "BatchMode=yes"])
        cmd = mock_run.call_args.args[0]
        assert cmd == ["ssh", "-o", "ConnectTimeout=15", "-o", "BatchMode=yes", "user@host", "echo hi"]

    def test_default_extra_opts_can_be_overridden(self):
        """Passing extra_opts=[] (not None) opts out of the default BatchMode."""
        from colette_cli.utils.ssh import ssh_run
        machine = {"type": "ssh", "host": "user@host"}
        ok = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=ok) as mock_run:
            ssh_run(machine, "echo hi", extra_opts=[])
        cmd = mock_run.call_args.args[0]
        assert cmd == ["ssh", "-o", "ConnectTimeout=15", "user@host", "echo hi"]


class TestFetchSelfReport:
    def test_passes_projects_dir_to_remote_command(self):
        from colette_cli.utils.ssh import fetch_self_report
        machine = {
            "type": "ssh", "host": "user@host", "colette_path": "/bin/colette",
            "projects_dir": "/root/colette-projects-dev",
        }
        ok = MagicMock(returncode=0, stdout='{"machine": {}, "projects": []}')
        with patch("subprocess.run", return_value=ok) as mock_run:
            fetch_self_report(machine, "dev")
        cmd = mock_run.call_args.args[0]
        assert cmd[-1] == "/bin/colette debug self-report /root/colette-projects-dev"

    def test_passes_empty_string_when_no_projects_dir_configured(self):
        from colette_cli.utils.ssh import fetch_self_report
        machine = {"type": "ssh", "host": "user@host", "colette_path": "/bin/colette"}
        ok = MagicMock(returncode=0, stdout='{"machine": {}, "projects": []}')
        with patch("subprocess.run", return_value=ok) as mock_run:
            fetch_self_report(machine, "dev")
        cmd = mock_run.call_args.args[0]
        assert cmd[-1] == "/bin/colette debug self-report ''"

    def test_returns_none_when_no_colette_path(self):
        from colette_cli.utils.ssh import fetch_self_report
        assert fetch_self_report({"type": "ssh", "host": "user@host"}, "dev") is None

    def test_returns_none_on_nonzero_exit(self):
        from colette_cli.utils.ssh import fetch_self_report
        machine = {"type": "ssh", "host": "user@host", "colette_path": "/bin/colette"}
        bad = MagicMock(returncode=1, stdout="")
        with patch("subprocess.run", return_value=bad):
            assert fetch_self_report(machine, "dev") is None

    def test_returns_none_on_malformed_json(self):
        from colette_cli.utils.ssh import fetch_self_report
        machine = {"type": "ssh", "host": "user@host", "colette_path": "/bin/colette"}
        bad = MagicMock(returncode=0, stdout="not json")
        with patch("subprocess.run", return_value=bad):
            assert fetch_self_report(machine, "dev") is None


class TestSshInteractive:
    def test_builds_command_with_tty_flag(self, monkeypatch):
        from colette_cli.utils.ssh import ssh_interactive
        monkeypatch.delenv("TMUX", raising=False)
        machine = {"type": "ssh", "host": "user@host"}
        with patch("subprocess.run") as mock_run:
            ssh_interactive(machine, "bash -l")
        mock_run.assert_called_once_with(
            ["ssh", "-t", "-o", "ConnectTimeout=15", "user@host", "bash -l"]
        )

    def test_disables_and_restores_local_tmux_mouse(self, monkeypatch):
        from colette_cli.utils.ssh import ssh_interactive
        monkeypatch.setenv("TMUX", "/tmp/tmux-0/default,123,0")
        machine = {"type": "ssh", "host": "user@host"}
        with patch("subprocess.run") as mock_run:
            ssh_interactive(machine, "bash -l")
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["tmux", "set-window-option", "mouse", "off"] in calls
        assert ["tmux", "set-window-option", "-u", "mouse"] in calls
        assert ["ssh", "-t", "-o", "ConnectTimeout=15", "user@host", "bash -l"] in calls

    def test_no_batch_mode(self, monkeypatch):
        """ssh_interactive must never pass BatchMode=yes — it may rely on
        password auth, unlike every other (non-interactive) ssh call here."""
        from colette_cli.utils.ssh import ssh_interactive
        monkeypatch.delenv("TMUX", raising=False)
        machine = {"type": "ssh", "host": "user@host"}
        with patch("subprocess.run") as mock_run:
            ssh_interactive(machine, "bash -l")
        assert "BatchMode=yes" not in mock_run.call_args.args[0]


class TestSshWriteAndMkdir:
    def test_ssh_write_success(self):
        from colette_cli.utils.ssh import _ssh_write
        ok = MagicMock(returncode=0)
        machine = {"type": "ssh", "host": "user@host"}
        with patch("subprocess.run", return_value=ok) as mock_run:
            result = _ssh_write(machine, "/remote/path", b"content")
        assert result is True
        assert mock_run.call_args.kwargs["input"] == b"content"
        assert "cat > /remote/path" in mock_run.call_args.args[0]

    def test_ssh_write_failure(self):
        from colette_cli.utils.ssh import _ssh_write
        fail = MagicMock(returncode=1)
        machine = {"type": "ssh", "host": "user@host"}
        with patch("subprocess.run", return_value=fail):
            result = _ssh_write(machine, "/remote/path", b"content")
        assert result is False

    def test_ssh_mkdir_success(self):
        from colette_cli.utils.ssh import _ssh_mkdir
        ok = MagicMock(returncode=0)
        machine = {"type": "ssh", "host": "user@host"}
        with patch("colette_cli.utils.ssh.ssh_run", return_value=ok) as mock_ssh:
            result = _ssh_mkdir(machine, "/remote/dir")
        assert result is True
        assert "mkdir -p /remote/dir" in mock_ssh.call_args.args[1]

    def test_ssh_mkdir_failure(self):
        from colette_cli.utils.ssh import _ssh_mkdir
        fail = MagicMock(returncode=1)
        machine = {"type": "ssh", "host": "user@host"}
        with patch("colette_cli.utils.ssh.ssh_run", return_value=fail):
            result = _ssh_mkdir(machine, "/remote/dir")
        assert result is False


class TestRealSshSubprocessGuard:
    def test_unmocked_real_ssh_call_raises_immediately(self):
        """Sanity-checks the autouse conftest guard: any test that forgets to
        mock subprocess.run/the relevant ssh.py function fails instantly
        instead of silently hanging on a real connection attempt."""
        import subprocess
        with pytest.raises(AssertionError, match="real `ssh` subprocess call"):
            subprocess.run(["ssh", "somehost", "echo hi"])


class TestSshReadHookFiles:
    def test_parses_project_and_template_content_by_marker(self):
        from colette_cli.utils.ssh import ssh_read_hook_files
        from colette_cli.utils.config import TEMPLATE_HOOK_FILENAMES

        n_paths = len(TEMPLATE_HOOK_FILENAMES) * 2  # project + template for each hook
        output_parts = []
        for i in range(n_paths):
            output_parts.append(f"__COLETTE_HOOK_{i}__\n")
            # Only the very first entry (project/oncreate) gets real content
            if i == 0:
                output_parts.append("echo oncreate-project-content")
        fake_output = "".join(output_parts)

        ok = MagicMock(returncode=0, stdout=fake_output)
        machine = {"type": "ssh", "host": "user@host"}
        with patch("colette_cli.utils.ssh.ssh_run", return_value=ok):
            resolved = ssh_read_hook_files(machine, "myproj", "mytmpl")

        assert resolved["oncreate"]["project"] == "echo oncreate-project-content"
        assert resolved["oncreate"]["template"] is None
        assert resolved["onstart"]["project"] is None

    def test_no_template_name_skips_template_paths(self):
        from colette_cli.utils.ssh import ssh_read_hook_files
        machine = {"type": "ssh", "host": "user@host"}
        ok = MagicMock(returncode=0, stdout="__COLETTE_HOOK_0__\nsomething")
        with patch("colette_cli.utils.ssh.ssh_run", return_value=ok):
            resolved = ssh_read_hook_files(machine, "myproj", None)
        assert all(v["template"] is None for v in resolved.values())
