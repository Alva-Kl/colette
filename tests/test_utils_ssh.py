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



class TestSyncRemoteColette:
    def setup_method(self):
        import colette_cli.utils.ssh as ssh_module
        ssh_module._synced_machines().clear()

    def test_skips_when_no_colette_path(self):
        from colette_cli.utils.ssh import sync_remote_colette
        machine = {"type": "ssh", "host": "myhost"}
        result = sync_remote_colette(machine, "myhost")
        assert result is False

    def test_syncs_when_remote_version_differs(self, tmp_path):
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import sync_remote_colette

        local_bin = tmp_path / "colette"
        local_bin.write_bytes(b"x" * 1024)

        machine = {"type": "ssh", "host": "myhost", "colette_path": "/usr/local/bin/colette"}

        version_result = MagicMock()
        version_result.stdout = "colette 1.0.0"  # outdated remote version
        version_result.returncode = 0

        scp_result = MagicMock()
        scp_result.returncode = 0

        with patch("colette_cli.utils.ssh._LOCAL_BIN", local_bin), \
             patch("colette_cli.utils.ssh.ssh_run", return_value=version_result), \
             patch("colette_cli.utils.ssh._local_version", "2.0.0"), \
             patch("subprocess.run", return_value=scp_result) as mock_run:
            result = sync_remote_colette(machine, "myhost")

        assert result is True
        scp_calls = [c for c in mock_run.call_args_list if c.args[0][0] == "scp"]
        assert len(scp_calls) == 1

    def test_syncs_when_remote_binary_absent(self, tmp_path):
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import sync_remote_colette

        local_bin = tmp_path / "colette"
        local_bin.write_bytes(b"x" * 1024)

        machine = {"type": "ssh", "host": "myhost", "colette_path": "/usr/local/bin/colette"}

        version_result = MagicMock()
        version_result.stdout = ""  # binary not found, no output
        version_result.returncode = 0

        scp_result = MagicMock()
        scp_result.returncode = 0

        with patch("colette_cli.utils.ssh._LOCAL_BIN", local_bin), \
             patch("colette_cli.utils.ssh.ssh_run", return_value=version_result), \
             patch("colette_cli.utils.ssh._local_version", "2.0.0"), \
             patch("subprocess.run", return_value=scp_result) as mock_run:
            result = sync_remote_colette(machine, "myhost")

        assert result is True
        scp_calls = [c for c in mock_run.call_args_list if c.args[0][0] == "scp"]
        assert len(scp_calls) == 1

    def test_skips_when_remote_version_matches(self, tmp_path):
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import sync_remote_colette

        local_bin = tmp_path / "colette"
        local_bin.write_bytes(b"x" * 512)

        machine = {"type": "ssh", "host": "myhost", "colette_path": "/usr/local/bin/colette"}

        version_result = MagicMock()
        version_result.stdout = "colette 2.0.0"  # same version
        version_result.returncode = 0

        with patch("colette_cli.utils.ssh._LOCAL_BIN", local_bin), \
             patch("colette_cli.utils.ssh.ssh_run", return_value=version_result), \
             patch("colette_cli.utils.ssh._local_version", "2.0.0"):
            result = sync_remote_colette(machine, "myhost")

        assert result is False

    def test_skips_cached_machine(self):
        from unittest.mock import patch
        import colette_cli.utils.ssh as ssh_module
        from colette_cli.utils.ssh import sync_remote_colette

        machine = {"name": "mymachine", "type": "ssh", "host": "myhost", "colette_path": "/usr/local/bin/colette"}
        ssh_module._synced_machines().add("mymachine")

        with patch("colette_cli.utils.ssh.ssh_run") as mock_ssh:
            result = sync_remote_colette(machine, "mymachine")

        assert result is False
        mock_ssh.assert_not_called()

    def test_sends_installed_notification_when_binary_absent(self, tmp_path, capsys):
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import sync_remote_colette

        local_bin = tmp_path / "colette"
        local_bin.write_bytes(b"x" * 100)
        machine = {"type": "ssh", "host": "myhost", "colette_path": "/opt/colette"}

        version_result = MagicMock()
        version_result.stdout = ""
        scp_result = MagicMock()
        scp_result.returncode = 0

        with patch("colette_cli.utils.ssh._LOCAL_BIN", local_bin), \
             patch("colette_cli.utils.ssh.ssh_run", return_value=version_result), \
             patch("colette_cli.utils.ssh._local_version", "2.0.0"), \
             patch("colette_cli.utils.ssh.send_notification") as mock_notify, \
             patch("subprocess.run", return_value=scp_result):
            sync_remote_colette(machine, "myserver")

        mock_notify.assert_called_once()
        title, body = mock_notify.call_args.args
        assert "Installed" in body and "myserver" in body
        out = capsys.readouterr().out
        assert "Installed" in out and "myserver" in out

    def test_sends_updated_notification_when_version_differs(self, tmp_path, capsys):
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import sync_remote_colette

        local_bin = tmp_path / "colette"
        local_bin.write_bytes(b"x" * 100)
        machine = {"type": "ssh", "host": "myhost", "colette_path": "/opt/colette"}

        version_result = MagicMock()
        version_result.stdout = "colette 1.9.9"
        scp_result = MagicMock()
        scp_result.returncode = 0

        with patch("colette_cli.utils.ssh._LOCAL_BIN", local_bin), \
             patch("colette_cli.utils.ssh.ssh_run", return_value=version_result), \
             patch("colette_cli.utils.ssh._local_version", "2.0.0"), \
             patch("colette_cli.utils.ssh.send_notification") as mock_notify, \
             patch("subprocess.run", return_value=scp_result):
            sync_remote_colette(machine, "myserver")

        mock_notify.assert_called_once()
        title, body = mock_notify.call_args.args
        assert "Updated" in body and "myserver" in body
        out = capsys.readouterr().out
        assert "Updated" in out and "myserver" in out

    def test_no_notification_when_version_matches(self, tmp_path):
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import sync_remote_colette

        local_bin = tmp_path / "colette"
        local_bin.write_bytes(b"x" * 100)
        machine = {"type": "ssh", "host": "myhost", "colette_path": "/opt/colette"}

        version_result = MagicMock()
        version_result.stdout = "colette 2.0.0"

        with patch("colette_cli.utils.ssh._LOCAL_BIN", local_bin), \
             patch("colette_cli.utils.ssh.ssh_run", return_value=version_result), \
             patch("colette_cli.utils.ssh._local_version", "2.0.0"), \
             patch("colette_cli.utils.ssh.send_notification") as mock_notify:
            sync_remote_colette(machine, "myserver")

        mock_notify.assert_not_called()

    def test_warns_when_local_binary_missing(self, tmp_path, capsys):
        from unittest.mock import patch
        from colette_cli.utils.ssh import sync_remote_colette

        missing_bin = tmp_path / "no_colette_here"
        machine = {"type": "ssh", "host": "myhost", "colette_path": "/opt/colette"}

        with patch("colette_cli.utils.ssh._LOCAL_BIN", missing_bin), \
             patch("colette_cli.utils.ssh.send_notification") as mock_notify:
            result = sync_remote_colette(machine, "myserver")

        assert result is None
        assert "binary sync skipped" in capsys.readouterr().err
        mock_notify.assert_called_once()

    def test_warns_when_scp_fails(self, tmp_path, capsys):
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import sync_remote_colette

        local_bin = tmp_path / "colette"
        local_bin.write_bytes(b"x" * 100)
        machine = {"type": "ssh", "host": "myhost", "colette_path": "/opt/colette"}

        version_result = MagicMock()
        version_result.stdout = ""  # absent on remote
        scp_fail = MagicMock()
        scp_fail.returncode = 1
        scp_fail.stderr = "Connection refused"

        with patch("colette_cli.utils.ssh._LOCAL_BIN", local_bin), \
             patch("colette_cli.utils.ssh.ssh_run", return_value=version_result), \
             patch("colette_cli.utils.ssh._local_version", "2.0.0"), \
             patch("colette_cli.utils.ssh.send_notification") as mock_notify, \
             patch("subprocess.run", return_value=scp_fail):
            result = sync_remote_colette(machine, "myserver")

        assert result is None
        assert "failed to copy colette" in capsys.readouterr().err
        mock_notify.assert_called_once()

    def test_warns_when_chmod_fails(self, tmp_path, capsys):
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import sync_remote_colette

        local_bin = tmp_path / "colette"
        local_bin.write_bytes(b"x" * 100)
        machine = {"type": "ssh", "host": "myhost", "colette_path": "/opt/colette"}

        version_result = MagicMock()
        version_result.stdout = ""  # absent on remote

        scp_ok = MagicMock()
        scp_ok.returncode = 0

        chmod_fail = MagicMock()
        chmod_fail.returncode = 1

        def fake_ssh_run(m, cmd, **kw):
            if "chmod" in cmd:
                return chmod_fail
            return version_result

        with patch("colette_cli.utils.ssh._LOCAL_BIN", local_bin), \
             patch("colette_cli.utils.ssh.ssh_run", side_effect=fake_ssh_run), \
             patch("colette_cli.utils.ssh._local_version", "2.0.0"), \
             patch("colette_cli.utils.ssh.send_notification"), \
             patch("subprocess.run", return_value=scp_ok):
            result = sync_remote_colette(machine, "myserver")

        assert result is True  # copy succeeded even though chmod failed
        assert "chmod +x failed" in capsys.readouterr().err

    def test_thread_local_cache_independent_between_threads(self, tmp_path):
        """Each thread should have its own independent synced-machines cache."""
        import threading
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import sync_remote_colette

        local_bin = tmp_path / "colette"
        local_bin.write_bytes(b"x" * 100)
        machine = {"type": "ssh", "host": "myhost", "colette_path": "/opt/colette"}

        version_result = MagicMock()
        version_result.stdout = ""  # absent on remote
        scp_ok = MagicMock()
        scp_ok.returncode = 0

        call_counts = []

        def run_sync():
            with patch("colette_cli.utils.ssh._LOCAL_BIN", local_bin), \
                 patch("colette_cli.utils.ssh.ssh_run", return_value=version_result), \
                 patch("colette_cli.utils.ssh._local_version", "2.0.0"), \
                 patch("colette_cli.utils.ssh.send_notification"), \
                 patch("subprocess.run", return_value=scp_ok) as mock_run:
                sync_remote_colette(machine, "myserver")
                # Count SCP calls — should always be 1 in a fresh thread
                call_counts.append(len([c for c in mock_run.call_args_list if c.args[0][0] == "scp"]))

        t1 = threading.Thread(target=run_sync)
        t2 = threading.Thread(target=run_sync)
        t1.start(); t1.join()
        t2.start(); t2.join()

        # Each thread should have triggered exactly one SCP call
        assert call_counts == [1, 1]

    def test_sync_opts_passed_to_ssh_run_and_scp(self, tmp_path):
        """BatchMode=yes and ConnectTimeout are forwarded to ssh_run and scp."""
        from unittest.mock import patch, MagicMock, call
        from colette_cli.utils.ssh import sync_remote_colette, _SYNC_SSH_OPTS

        local_bin = tmp_path / "colette"
        local_bin.write_bytes(b"x" * 100)
        machine = {"type": "ssh", "host": "myhost", "colette_path": "/opt/colette"}

        version_result = MagicMock()
        version_result.stdout = ""  # absent, need_sync=True
        scp_ok = MagicMock()
        scp_ok.returncode = 0

        with patch("colette_cli.utils.ssh._LOCAL_BIN", local_bin), \
             patch("colette_cli.utils.ssh.ssh_run", return_value=version_result) as mock_ssh, \
             patch("colette_cli.utils.ssh._local_version", "2.0.0"), \
             patch("colette_cli.utils.ssh.send_notification"), \
             patch("subprocess.run", return_value=scp_ok) as mock_run:
            sync_remote_colette(machine, "myserver")

        # All ssh_run calls should include _SYNC_SSH_OPTS
        for c in mock_ssh.call_args_list:
            assert c.kwargs.get("extra_opts") == _SYNC_SSH_OPTS

        # The scp subprocess.run call should include _SYNC_SSH_OPTS
        scp_calls = [c for c in mock_run.call_args_list if c.args[0][0] == "scp"]
        assert len(scp_calls) == 1
        scp_cmd = scp_calls[0].args[0]
        for opt in _SYNC_SSH_OPTS:
            assert opt in scp_cmd


class TestFindLocalBin:
    def test_find_local_bin_zipapp(self, tmp_path):
        """_find_local_bin resolves correctly when __file__ is inside a zipapp.

        Simulate a zipapp at tmp_path/build/beta/colette (a real file) and a
        virtual __file__ path inside it.  The expected result is
        tmp_path/build/prod/colette regardless of the variant directory.
        """
        from colette_cli.utils.ssh import _find_local_bin
        import unittest.mock as mock

        # Create the fake zipapp file so is_file() returns True
        zipapp = tmp_path / "build" / "beta" / "colette"
        zipapp.parent.mkdir(parents=True)
        zipapp.write_bytes(b"fake-zipapp")

        # Virtual path that __file__ would have inside the zipapp
        fake_file = str(zipapp / "colette_cli" / "utils" / "ssh.py")

        with mock.patch("colette_cli.utils.ssh.__file__", fake_file):
            result = _find_local_bin()

        assert result == tmp_path / "build" / "prod" / "colette"

    def test_find_local_bin_dev_install(self, tmp_path):
        """_find_local_bin falls back to __file__-relative logic for dev installs.

        Simulate a normal editable install where __file__ is a real file on
        disk and no ancestor is a file.
        """
        from colette_cli.utils.ssh import _find_local_bin
        import unittest.mock as mock

        # Create a real file structure mimicking the source tree
        utils_dir = tmp_path / "colette_cli" / "utils"
        utils_dir.mkdir(parents=True)
        fake_file = utils_dir / "ssh.py"
        fake_file.write_bytes(b"# fake")

        with mock.patch("colette_cli.utils.ssh.__file__", str(fake_file)):
            result = _find_local_bin()

        assert result == tmp_path / "build" / "prod" / "colette"



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
        assert mock_run.call_args.args[0] == ["ssh", "user@host", "echo hi"]
        assert mock_run.call_args.kwargs["stdin"] is not None

    def test_includes_key_and_port(self):
        from colette_cli.utils.ssh import ssh_run
        machine = {"type": "ssh", "host": "user@host", "ssh_key": "/k", "port": 24}
        ok = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=ok) as mock_run:
            ssh_run(machine, "echo hi")
        cmd = mock_run.call_args.args[0]
        assert cmd == ["ssh", "-i", "/k", "-p", "24", "user@host", "echo hi"]

    def test_extra_opts_inserted_before_host(self):
        from colette_cli.utils.ssh import ssh_run
        machine = {"type": "ssh", "host": "user@host"}
        ok = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=ok) as mock_run:
            ssh_run(machine, "echo hi", extra_opts=["-o", "BatchMode=yes"])
        cmd = mock_run.call_args.args[0]
        assert cmd == ["ssh", "-o", "BatchMode=yes", "user@host", "echo hi"]


class TestSshInteractive:
    def test_builds_command_with_tty_flag(self, monkeypatch):
        from colette_cli.utils.ssh import ssh_interactive
        monkeypatch.delenv("TMUX", raising=False)
        machine = {"type": "ssh", "host": "user@host"}
        with patch("subprocess.run") as mock_run:
            ssh_interactive(machine, "bash -l")
        mock_run.assert_called_once_with(["ssh", "-t", "user@host", "bash -l"])

    def test_disables_and_restores_local_tmux_mouse(self, monkeypatch):
        from colette_cli.utils.ssh import ssh_interactive
        monkeypatch.setenv("TMUX", "/tmp/tmux-0/default,123,0")
        machine = {"type": "ssh", "host": "user@host"}
        with patch("subprocess.run") as mock_run:
            ssh_interactive(machine, "bash -l")
        calls = [c.args[0] for c in mock_run.call_args_list]
        assert ["tmux", "set-window-option", "mouse", "off"] in calls
        assert ["tmux", "set-window-option", "-u", "mouse"] in calls
        assert ["ssh", "-t", "user@host", "bash -l"] in calls


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
