"""Tests for colette_cli.template.executor."""

import pytest
from unittest.mock import patch, MagicMock


class TestHasEffectiveScript:
    """_has_effective_script returns True only for non-empty, non-comment content."""

    def _call(self, content):
        from colette_cli.template.executor import _has_effective_script
        return _has_effective_script(content)

    def test_none_returns_false(self):
        assert not self._call(None)

    def test_empty_string_returns_false(self):
        assert not self._call("")

    def test_only_shebang_returns_false(self):
        assert not self._call("#!/usr/bin/env bash\n")

    def test_only_comments_returns_false(self):
        assert not self._call("#!/usr/bin/env bash\n# just a comment\n")

    def test_real_command_returns_true(self):
        assert self._call("#!/usr/bin/env bash\necho hello\n")

    def test_whitespace_only_returns_false(self):
        assert not self._call("   \n  \n")


class TestResolveHook:
    """_resolve_hook returns project hook first, then template hook, then None."""

    def test_returns_project_hook_when_present(self, tmp_config):
        from colette_cli.utils.config import write_project_hook
        from colette_cli.template.executor import _resolve_hook
        write_project_hook("proj", "onstart", "#!/usr/bin/env bash\necho proj")
        result = _resolve_hook("proj", "tmpl", "onstart")
        assert "echo proj" in result

    def test_falls_back_to_template_hook(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import _resolve_hook
        write_template_hook("tmpl", "onstart", "#!/usr/bin/env bash\necho tmpl")
        result = _resolve_hook("proj", "tmpl", "onstart")
        assert "echo tmpl" in result

    def test_returns_none_when_no_hook(self, tmp_config):
        from colette_cli.template.executor import _resolve_hook
        result = _resolve_hook("proj", "tmpl", "onstart")
        assert result is None

    def test_project_hook_takes_precedence(self, tmp_config):
        from colette_cli.utils.config import write_project_hook, write_template_hook
        from colette_cli.template.executor import _resolve_hook
        write_project_hook("proj", "onstart", "#!/usr/bin/env bash\necho project")
        write_template_hook("tmpl", "onstart", "#!/usr/bin/env bash\necho template")
        result = _resolve_hook("proj", "tmpl", "onstart")
        assert "project" in result

    def test_ineffective_hook_returns_none(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import _resolve_hook
        write_template_hook("tmpl", "onstart", "#!/usr/bin/env bash\n# empty\n")
        assert _resolve_hook("proj", "tmpl", "onstart") is None


class TestBuildProjectBootstrap:
    def test_returns_exec_bash_when_no_coletterc(self, tmp_config):
        from colette_cli.template.executor import build_project_bootstrap
        project = {"name": "p", "path": "/p", "machine": "local", "template": "t"}
        result = build_project_bootstrap(project, "local", {"name": "t"})
        assert result == "exec bash"

    def test_includes_coletterc_when_present(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import build_project_bootstrap
        write_template_hook("t", "coletterc", "export FOO=bar\n")
        project = {"name": "p", "path": "/p", "machine": "local", "template": "t"}
        result = build_project_bootstrap(project, "local", {"name": "t"})
        assert "FOO=bar" in result
        assert "exec bash" in result


class TestRunTemplateHook:
    def test_returns_true_when_no_hook(self, tmp_config):
        from colette_cli.template.executor import run_template_hook
        project = {"name": "proj", "path": "/p", "machine": "local", "template": None}
        machine = {"type": "local"}
        result = run_template_hook(project, machine, "local", False, None, "onstart")
        assert result is True

    def test_runs_local_hook_successfully(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import run_template_hook
        write_template_hook("t", "onstart", "#!/usr/bin/env bash\nexit 0")
        project = {"name": "proj", "path": "/tmp", "machine": "local", "template": "t"}
        metadata = {"name": "t"}
        result = run_template_hook(project, {}, "local", False, metadata, "onstart")
        assert result is True

    def test_failed_hook_returns_false_by_default(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import run_template_hook
        write_template_hook("t", "onstart", "#!/usr/bin/env bash\nexit 1")
        project = {"name": "proj", "path": "/tmp", "machine": "local", "template": "t"}
        metadata = {"name": "t"}
        result = run_template_hook(project, {}, "local", False, metadata, "onstart", fail_on_error=False)
        assert result is False

    def test_failed_hook_exits_when_fail_on_error(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import run_template_hook
        write_template_hook("t", "oncreate", "#!/usr/bin/env bash\nexit 42")
        project = {"name": "proj", "path": "/tmp", "machine": "local", "template": "t"}
        metadata = {"name": "t"}
        with pytest.raises(SystemExit):
            run_template_hook(project, {}, "local", False, metadata, "oncreate", fail_on_error=True)

    def test_echo_hook_writes_marker_file(self, tmp_config, tmp_path):
        """An echo hook actually executes: its output reaches the filesystem."""
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import run_template_hook
        marker = tmp_path / "marker.txt"
        write_template_hook("t", "onstart", f"#!/usr/bin/env bash\necho ran > {marker}")
        project = {"name": "proj", "path": str(tmp_path), "machine": "local", "template": "t"}
        metadata = {"name": "t"}
        result = run_template_hook(project, {}, "local", False, metadata, "onstart")
        assert result is True
        assert marker.read_text().strip() == "ran"


class TestBuildHookCommand:
    def test_returns_none_when_no_hook(self, tmp_config):
        from colette_cli.template.executor import build_hook_command
        project = {"name": "proj", "path": "/p", "machine": "local", "template": None}
        assert build_hook_command(project, "local", None, {}, "onlogs") is None

    def test_returns_shell_command_when_hook_present(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import build_hook_command
        write_template_hook("t", "onlogs", "#!/usr/bin/env bash\ntail -f log")
        project = {"name": "proj", "path": "/tmp", "machine": "local", "template": "t"}
        metadata = {"name": "t"}
        cmd = build_hook_command(project, "local", metadata, {}, "onlogs")
        assert cmd is not None
        assert "tail -f log" in cmd
        assert "COLETTE_PROJECT_NAME" in cmd
