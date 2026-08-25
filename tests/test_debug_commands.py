"""Tests for colette_cli.debug.commands."""

import pytest
from unittest.mock import MagicMock

from tests.conftest import make_local_machine


LOCAL_CFG = {
    "machines": {"local": make_local_machine()},
    "default_machine": "local",
}


class TestCmdDebugHookLog:
    def _make_entry(self, project="proj", hook="onstart", exit_code=1, output="oops"):
        return {
            "ts": "2026-01-01T00:00:00Z",
            "project": project,
            "template": "tmpl",
            "hook": hook,
            "exit_code": exit_code,
            "output": output,
        }

    def test_no_failures_prints_message(self, tmp_config, capsys):
        from colette_cli.debug.commands import cmd_debug_hook_log
        cmd_debug_hook_log(MagicMock(clear=False, project=None))
        assert "No hook failures" in capsys.readouterr().out

    def test_shows_failures_most_recent_first(self, tmp_config, capsys):
        from colette_cli.utils.config import append_hook_failure
        from colette_cli.debug.commands import cmd_debug_hook_log
        append_hook_failure(self._make_entry(project="first"))
        append_hook_failure(self._make_entry(project="second"))
        cmd_debug_hook_log(MagicMock(clear=False, project=None))
        out = capsys.readouterr().out
        assert out.index("second") < out.index("first")

    def test_clear_flag_wipes_log(self, tmp_config, capsys):
        from colette_cli.utils.config import append_hook_failure, load_hook_failures
        from colette_cli.debug.commands import cmd_debug_hook_log
        append_hook_failure(self._make_entry())
        cmd_debug_hook_log(MagicMock(clear=True, project=None))
        assert load_hook_failures() == []
        assert "cleared" in capsys.readouterr().out.lower()

    def test_project_filter_narrows_results(self, tmp_config, capsys):
        from colette_cli.utils.config import append_hook_failure
        from colette_cli.debug.commands import cmd_debug_hook_log
        append_hook_failure(self._make_entry(project="alpha"))
        append_hook_failure(self._make_entry(project="beta"))
        cmd_debug_hook_log(MagicMock(clear=False, project="alpha"))
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" not in out

    def test_project_filter_no_match_prints_message(self, tmp_config, capsys):
        from colette_cli.utils.config import append_hook_failure
        from colette_cli.debug.commands import cmd_debug_hook_log
        append_hook_failure(self._make_entry(project="other"))
        cmd_debug_hook_log(MagicMock(clear=False, project="ghost"))
        assert "No hook failures" in capsys.readouterr().out

    def test_output_is_shown_in_entry(self, tmp_config, capsys):
        from colette_cli.utils.config import append_hook_failure
        from colette_cli.debug.commands import cmd_debug_hook_log
        append_hook_failure(self._make_entry(output="something went wrong"))
        cmd_debug_hook_log(MagicMock(clear=False, project=None))
        assert "something went wrong" in capsys.readouterr().out


class TestCmdDebugSelfReport:
    def test_uses_default_machine_when_it_is_local(self, tmp_config, capsys):
        import json
        from colette_cli.utils.config import save_config, save_local_projects
        from colette_cli.debug.commands import cmd_debug_self_report
        save_config({
            "machines": {
                "local": {"type": "local", "projects_dir": "/home/user/projects", "templates": []},
                "other": {"type": "local", "projects_dir": "/elsewhere", "templates": []},
            },
            "default_machine": "local",
        })
        save_local_projects([{"name": "p", "machine": "local", "path": "/home/user/projects/p", "template": None}])
        cmd_debug_self_report(MagicMock())
        report = json.loads(capsys.readouterr().out)
        assert report["machine"]["projects_dir"] == "/home/user/projects"
        assert report["projects"][0]["name"] == "p"

    def test_falls_back_to_first_local_entry_when_default_is_ssh(self, tmp_config, capsys):
        import json
        from colette_cli.utils.config import save_config
        from colette_cli.debug.commands import cmd_debug_self_report
        save_config({
            "machines": {
                "remote-stub": {"type": "ssh", "host": "user@elsewhere"},
                "local": {"type": "local", "projects_dir": "/home/user/projects", "templates": []},
            },
            "default_machine": "remote-stub",
        })
        cmd_debug_self_report(MagicMock())
        report = json.loads(capsys.readouterr().out)
        assert report["machine"]["projects_dir"] == "/home/user/projects"

    def test_falls_back_to_first_local_entry_when_no_default_set(self, tmp_config, capsys):
        import json
        from colette_cli.utils.config import save_config
        from colette_cli.debug.commands import cmd_debug_self_report
        save_config({
            "machines": {"local": {"type": "local", "projects_dir": "/p", "templates": []}},
            "default_machine": None,
        })
        cmd_debug_self_report(MagicMock())
        report = json.loads(capsys.readouterr().out)
        assert report["machine"]["projects_dir"] == "/p"

    def test_errors_when_no_local_machine_entry_exists(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.debug.commands import cmd_debug_self_report
        save_config({
            "machines": {"remote": {"type": "ssh", "host": "user@host"}},
            "default_machine": "remote",
        })
        with pytest.raises(SystemExit):
            cmd_debug_self_report(MagicMock())


class TestCmdDebugDispatch:
    def test_hook_log_subcommand_dispatches(self, tmp_config, capsys):
        from colette_cli.debug.commands import cmd_debug
        args = MagicMock()
        args.debug_cmd = "hook-log"
        args.clear = False
        args.project = None
        cmd_debug(args)
        assert "No hook failures" in capsys.readouterr().out

    def test_self_report_subcommand_dispatches(self, tmp_config, capsys):
        import json
        from colette_cli.utils.config import save_config
        from colette_cli.debug.commands import cmd_debug
        save_config({
            "machines": {"local": {"type": "local", "projects_dir": "/p", "templates": []}},
            "default_machine": "local",
        })
        args = MagicMock()
        args.debug_cmd = "self-report"
        cmd_debug(args)
        report = json.loads(capsys.readouterr().out)
        assert report["machine"]["projects_dir"] == "/p"

    def test_no_subcommand_prints_help(self, tmp_config):
        from colette_cli.debug.commands import cmd_debug
        mock_parser = MagicMock()
        args = MagicMock()
        args.debug_cmd = None
        args.debug_parser = mock_parser
        cmd_debug(args)
        mock_parser.print_help.assert_called_once()
