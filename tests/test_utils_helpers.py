"""Tests for colette_cli.utils.helpers."""

from colette_cli.utils.helpers import build_projects_by_machine, filter_projects_by_name


PROJECTS = [
    {"name": "a", "machine": "local"},
    {"name": "b", "machine": "local"},
    {"name": "c", "machine": "remote"},
]


class TestBuildProjectsByMachine:
    def test_groups_by_machine(self):
        result = build_projects_by_machine(PROJECTS)
        assert set(result.keys()) == {"local", "remote"}
        assert len(result["local"]) == 2
        assert len(result["remote"]) == 1

    def test_filter_by_machine(self):
        result = build_projects_by_machine(PROJECTS, filter_machine="local")
        assert list(result.keys()) == ["local"]
        assert len(result["local"]) == 2

    def test_filter_no_match_returns_empty(self):
        result = build_projects_by_machine(PROJECTS, filter_machine="nowhere")
        assert result == {}

    def test_empty_projects_returns_empty(self):
        assert build_projects_by_machine([]) == {}


class TestFilterProjectsByName:
    def test_no_names_returns_all(self):
        result = filter_projects_by_name(PROJECTS, [])
        assert result == list(PROJECTS)

    def test_filter_by_names(self):
        result = filter_projects_by_name(PROJECTS, ["a", "c"])
        names = [p["name"] for p in result]
        assert sorted(names) == ["a", "c"]

    def test_filter_nonexistent_name_returns_empty(self):
        result = filter_projects_by_name(PROJECTS, ["zzz"])
        assert result == []

    def test_none_names_returns_all(self):
        result = filter_projects_by_name(PROJECTS, None)
        assert result == list(PROJECTS)


class TestIsRemoteMachine:
    def test_none_machine_is_not_remote(self):
        from colette_cli.utils.helpers import is_remote_machine
        assert is_remote_machine(None) is False

    def test_local_machine_is_not_remote(self):
        from colette_cli.utils.helpers import is_remote_machine
        assert is_remote_machine({"type": "local"}) is False

    def test_machine_without_type_is_not_remote(self):
        from colette_cli.utils.helpers import is_remote_machine
        assert is_remote_machine({}) is False

    def test_ssh_machine_is_remote(self):
        from colette_cli.utils.helpers import is_remote_machine
        assert is_remote_machine({"type": "ssh", "host": "example.com"}) is True


class TestDetectProjectFromCwd:
    def test_returns_project_name_when_cwd_matches(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_projects
        from colette_cli.utils.helpers import detect_project_from_cwd
        project_path = tmp_path / "my-project"
        project_path.mkdir()
        save_projects([{"name": "my-project", "machine": "local", "path": str(project_path)}])

        import os
        orig = os.getcwd()
        try:
            os.chdir(str(project_path))
            result = detect_project_from_cwd()
        finally:
            os.chdir(orig)

        assert result == "my-project"

    def test_returns_none_when_cwd_does_not_match(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_projects
        from colette_cli.utils.helpers import detect_project_from_cwd
        project_path = tmp_path / "my-project"
        project_path.mkdir()
        other_path = tmp_path / "other"
        other_path.mkdir()
        save_projects([{"name": "my-project", "machine": "local", "path": str(project_path)}])

        import os
        orig = os.getcwd()
        try:
            os.chdir(str(other_path))
            result = detect_project_from_cwd()
        finally:
            os.chdir(orig)

        assert result is None

    def test_returns_none_when_no_projects(self, tmp_config, tmp_path):
        from colette_cli.utils.helpers import detect_project_from_cwd
        import os
        orig = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            result = detect_project_from_cwd()
        finally:
            os.chdir(orig)
        assert result is None


PROJECTS = [
    {"name": "a", "machine": "local"},
    {"name": "b", "machine": "local"},
    {"name": "c", "machine": "remote"},
]


class TestBuildProjectsByMachine:
    def test_groups_by_machine(self):
        result = build_projects_by_machine(PROJECTS)
        assert set(result.keys()) == {"local", "remote"}
        assert len(result["local"]) == 2
        assert len(result["remote"]) == 1

    def test_filter_by_machine(self):
        result = build_projects_by_machine(PROJECTS, filter_machine="local")
        assert list(result.keys()) == ["local"]
        assert len(result["local"]) == 2

    def test_filter_no_match_returns_empty(self):
        result = build_projects_by_machine(PROJECTS, filter_machine="nowhere")
        assert result == {}

    def test_empty_projects_returns_empty(self):
        assert build_projects_by_machine([]) == {}


class TestFilterProjectsByName:
    def test_no_names_returns_all(self):
        result = filter_projects_by_name(PROJECTS, [])
        assert result == list(PROJECTS)

    def test_filter_by_names(self):
        result = filter_projects_by_name(PROJECTS, ["a", "c"])
        names = [p["name"] for p in result]
        assert sorted(names) == ["a", "c"]

    def test_filter_nonexistent_name_returns_empty(self):
        result = filter_projects_by_name(PROJECTS, ["zzz"])
        assert result == []

    def test_none_names_returns_all(self):
        result = filter_projects_by_name(PROJECTS, None)
        assert result == list(PROJECTS)


class TestIsRemoteMachine:
    def test_none_machine_is_not_remote(self):
        from colette_cli.utils.helpers import is_remote_machine
        assert is_remote_machine(None) is False

    def test_local_machine_is_not_remote(self):
        from colette_cli.utils.helpers import is_remote_machine
        assert is_remote_machine({"type": "local"}) is False

    def test_machine_without_type_is_not_remote(self):
        from colette_cli.utils.helpers import is_remote_machine
        assert is_remote_machine({}) is False

    def test_ssh_machine_is_remote(self):
        from colette_cli.utils.helpers import is_remote_machine
        assert is_remote_machine({"type": "ssh", "host": "example.com"}) is True


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


    def test_transfers_project_hooks_and_json(self, tmp_config):
        from unittest.mock import patch, MagicMock, call
        from colette_cli.utils.ssh import inject_project_config
        from colette_cli.utils.config import save_projects, PROJECT_HOOKS_DIR

        project = {"name": "myproj", "machine": "remote-box", "path": "/p/myproj", "template": None}
        save_projects([project])

        # Create a local hook file
        hook_dir = PROJECT_HOOKS_DIR / "myproj"
        hook_dir.mkdir(parents=True, exist_ok=True)
        (hook_dir / ".onstart").write_text("#!/bin/bash\necho hi")

        machine = {"type": "ssh", "host": "myhost"}
        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = "[]"

        with patch("colette_cli.utils.ssh.ssh_run", return_value=ok), \
             patch("subprocess.run", return_value=ok) as mock_run:
            result = inject_project_config(machine, "remote-box", project)

        assert result is True
        # A subprocess.run call piping the hook content should exist
        write_calls = [c for c in mock_run.call_args_list if "cat >" in (c.args[0][-1] if c.args else "")]
        assert any(".onstart" in c.args[0][-1] for c in write_calls)

    def test_transfers_template_hooks_when_present(self, tmp_config):
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import inject_project_config
        from colette_cli.utils.config import save_projects, save_templates, TEMPLATE_SCRIPTS_DIR

        project = {"name": "proj2", "machine": "remote-box", "path": "/p/proj2", "template": "mytmpl"}
        save_projects([project])
        save_templates({"templates": [{"name": "mytmpl"}]})

        tmpl_dir = TEMPLATE_SCRIPTS_DIR / "mytmpl"
        tmpl_dir.mkdir(parents=True, exist_ok=True)
        (tmpl_dir / ".onupdate").write_text("#!/bin/bash\necho update")

        machine = {"type": "ssh", "host": "myhost"}
        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = "[]"

        with patch("colette_cli.utils.ssh.ssh_run", return_value=ok), \
             patch("subprocess.run", return_value=ok) as mock_run:
            result = inject_project_config(machine, "remote-box", project)

        assert result is True
        write_calls = [c for c in mock_run.call_args_list if "cat >" in (c.args[0][-1] if c.args else "")]
        assert any(".onupdate" in c.args[0][-1] for c in write_calls)

    def test_uses_home_variable_not_tilde(self, tmp_config):
        """Remote paths must use $HOME so the shell expands them, not literal ~."""
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import inject_project_config
        from colette_cli.utils.config import save_projects

        project = {"name": "homechk", "machine": "remote", "path": "/p/homechk", "template": None}
        save_projects([project])

        machine = {"type": "ssh", "host": "myhost"}
        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = "[]"

        ssh_calls = []
        subprocess_calls = []

        def fake_ssh_run(m, cmd):
            ssh_calls.append(cmd)
            return ok

        def fake_subprocess_run(args, **kwargs):
            subprocess_calls.append(args[-1] if args else "")
            return ok

        with patch("colette_cli.utils.ssh.ssh_run", side_effect=fake_ssh_run), \
             patch("subprocess.run", side_effect=fake_subprocess_run):
            inject_project_config(machine, "remote", project)

        all_cmds = ssh_calls + subprocess_calls
        # No command should contain a single-quoted tilde
        bad_cmds = [c for c in all_cmds if "'~/" in c]
        assert not bad_cmds, f"Found single-quoted tilde in remote command: {bad_cmds}"
        # The mkdir command should use $HOME
        mkdir_cmds = [c for c in all_cmds if "mkdir" in c]
        assert all("$HOME" in c for c in mkdir_cmds), f"mkdir not using $HOME: {mkdir_cmds}"

    def test_warns_and_returns_false_on_mkdir_failure(self, tmp_config, capsys):
        from unittest.mock import patch, MagicMock
        from colette_cli.utils.ssh import inject_project_config
        from colette_cli.utils.config import save_projects

        project = {"name": "failproj", "machine": "remote", "path": "/p/fail", "template": None}
        save_projects([project])

        machine = {"type": "ssh", "host": "myhost"}
        fail = MagicMock()
        fail.returncode = 1
        fail.stdout = ""
        fail.stderr = "permission denied"

        with patch("colette_cli.utils.ssh.ssh_run", return_value=fail):
            result = inject_project_config(machine, "remote", project)

        assert result is False
        assert "inject" in capsys.readouterr().err


class TestEnsureSessionRemote:
    def test_warns_when_tmux_new_session_fails(self, capsys):
        from unittest.mock import patch, MagicMock
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
        from unittest.mock import patch, MagicMock
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

