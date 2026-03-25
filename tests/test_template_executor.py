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


class TestResolveHookWithSuper:
    """_resolve_hook_with_super returns (content, super_path) with project-first resolution."""

    def test_returns_project_hook_when_present(self, tmp_config):
        from colette_cli.utils.config import write_project_hook
        from colette_cli.template.executor import _resolve_hook_with_super
        write_project_hook("proj", "onstart", "#!/usr/bin/env bash\necho proj")
        content, super_path = _resolve_hook_with_super("proj", "tmpl", "onstart")
        assert "echo proj" in content

    def test_sets_super_path_when_project_override_active(self, tmp_config):
        from colette_cli.utils.config import write_project_hook
        from colette_cli.template.executor import _resolve_hook_with_super
        write_project_hook("proj", "onstart", "#!/usr/bin/env bash\necho proj")
        _content, super_path = _resolve_hook_with_super("proj", "tmpl", "onstart")
        assert super_path is not None
        assert "tmpl" in str(super_path)
        assert "onstart" in str(super_path)

    def test_no_super_path_when_using_template_hook(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import _resolve_hook_with_super
        write_template_hook("tmpl", "onstart", "#!/usr/bin/env bash\necho tmpl")
        _content, super_path = _resolve_hook_with_super("proj", "tmpl", "onstart")
        assert super_path is None

    def test_falls_back_to_template_hook(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import _resolve_hook_with_super
        write_template_hook("tmpl", "onstart", "#!/usr/bin/env bash\necho tmpl")
        content, _ = _resolve_hook_with_super("proj", "tmpl", "onstart")
        assert "echo tmpl" in content

    def test_returns_none_when_no_hook(self, tmp_config):
        from colette_cli.template.executor import _resolve_hook_with_super
        content, super_path = _resolve_hook_with_super("proj", "tmpl", "onstart")
        assert content is None
        assert super_path is None

    def test_project_hook_takes_precedence(self, tmp_config):
        from colette_cli.utils.config import write_project_hook, write_template_hook
        from colette_cli.template.executor import _resolve_hook_with_super
        write_project_hook("proj", "onstart", "#!/usr/bin/env bash\necho project")
        write_template_hook("tmpl", "onstart", "#!/usr/bin/env bash\necho template")
        content, _ = _resolve_hook_with_super("proj", "tmpl", "onstart")
        assert "project" in content

    def test_ineffective_hook_returns_none(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import _resolve_hook_with_super
        write_template_hook("tmpl", "onstart", "#!/usr/bin/env bash\n# empty\n")
        content, _ = _resolve_hook_with_super("proj", "tmpl", "onstart")
        assert content is None


class TestPrependColetterc:
    """_prepend_coletterc prepends coletterc content before a hook command."""

    def test_returns_command_unchanged_when_no_coletterc(self, tmp_config):
        from colette_cli.template.executor import _prepend_coletterc
        result = _prepend_coletterc("proj", "tmpl", "echo hook")
        assert result == "echo hook"

    def test_prepends_template_coletterc(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import _prepend_coletterc
        write_template_hook("tmpl", "coletterc", "export MYVAR=1\n")
        result = _prepend_coletterc("proj", "tmpl", "echo hook")
        assert "MYVAR=1" in result
        assert "echo hook" in result
        assert result.index("MYVAR=1") < result.index("echo hook")

    def test_prepends_project_coletterc_with_super(self, tmp_config):
        from colette_cli.utils.config import write_project_hook, write_template_hook
        from colette_cli.template.executor import _prepend_coletterc
        write_project_hook("proj", "coletterc", "export PROJ_VAR=1\n")
        write_template_hook("tmpl", "coletterc", "export TMPL_VAR=1\n")
        result = _prepend_coletterc("proj", "tmpl", "echo hook")
        assert "PROJ_VAR=1" in result
        assert "SUPER=" in result
        assert "tmpl" in result


class TestBuildProjectBootstrap:
    def test_returns_exec_bash_when_no_coletterc(self, tmp_config):
        from colette_cli.template.executor import build_project_bootstrap
        project = {"name": "p", "path": "/p", "machine": "local", "template": "t"}
        result = build_project_bootstrap(project, "local", {"name": "t"})
        assert result == "exec bash"

    def test_uses_rcfile_when_template_coletterc_present(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import build_project_bootstrap
        write_template_hook("t", "coletterc", "export FOO=bar\n")
        project = {"name": "p", "path": "/p", "machine": "local", "template": "t"}
        result = build_project_bootstrap(project, "local", {"name": "t"})
        assert "--rcfile" in result
        assert "base64" in result

    def test_uses_project_coletterc_over_template(self, tmp_config):
        from colette_cli.utils.config import write_project_hook, write_template_hook
        from colette_cli.template.executor import build_project_bootstrap
        import base64
        write_project_hook("p", "coletterc", "export PROJ=yes\n")
        write_template_hook("t", "coletterc", "export TMPL=yes\n")
        project = {"name": "p", "path": "/p", "machine": "local", "template": "t"}
        result = build_project_bootstrap(project, "local", {"name": "t"})
        # Decode the embedded base64 to verify content
        b64_part = result.split("echo ")[1].split(" |")[0].strip("'\"")
        decoded = base64.b64decode(b64_part).decode()
        assert "PROJ=yes" in decoded
        assert "SUPER=" in decoded

    def test_sources_bashrc_in_rcfile(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import build_project_bootstrap
        import base64
        write_template_hook("t", "coletterc", "export FOO=bar\n")
        project = {"name": "p", "path": "/p", "machine": "local", "template": "t"}
        result = build_project_bootstrap(project, "local", {"name": "t"})
        b64_part = result.split("echo ")[1].split(" |")[0].strip("'\"")
        decoded = base64.b64decode(b64_part).decode()
        assert ".bashrc" in decoded
        assert "FOO=bar" in decoded


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

    def test_coletterc_runs_before_hook(self, tmp_config, tmp_path):
        """coletterc is sourced before the hook script."""
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import run_template_hook
        marker = tmp_path / "order.txt"
        write_template_hook("t", "coletterc", "export COLETTERC_RAN=1\n")
        write_template_hook(
            "t", "onstart",
            f"#!/usr/bin/env bash\necho $COLETTERC_RAN > {marker}"
        )
        project = {"name": "proj", "path": str(tmp_path), "machine": "local", "template": "t"}
        run_template_hook(project, {}, "local", False, {"name": "t"}, "onstart")
        assert marker.read_text().strip() == "1"

    def test_super_is_set_for_project_level_hook(self, tmp_config, tmp_path):
        """$SUPER points to the template hook when a project hook overrides it."""
        from colette_cli.utils.config import write_project_hook, write_template_hook
        from colette_cli.template.executor import run_template_hook
        marker = tmp_path / "super.txt"
        write_template_hook("t", "onstart", "#!/usr/bin/env bash\necho template")
        write_project_hook(
            "proj", "onstart",
            f"#!/usr/bin/env bash\necho $SUPER > {marker}"
        )
        project = {"name": "proj", "path": str(tmp_path), "machine": "local", "template": "t"}
        run_template_hook(project, {}, "local", False, {"name": "t"}, "onstart")
        super_val = marker.read_text().strip()
        assert "t" in super_val
        assert "onstart" in super_val


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

    def test_coletterc_included_in_hook_command(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import build_hook_command
        write_template_hook("t", "coletterc", "export MYENV=1\n")
        write_template_hook("t", "onlogs", "#!/usr/bin/env bash\ntail -f log")
        project = {"name": "proj", "path": "/tmp", "machine": "local", "template": "t"}
        metadata = {"name": "t"}
        cmd = build_hook_command(project, "local", metadata, {}, "onlogs")
        assert "MYENV=1" in cmd

    def test_super_included_in_hook_command_for_project_override(self, tmp_config):
        from colette_cli.utils.config import write_project_hook, write_template_hook
        from colette_cli.template.executor import build_hook_command
        write_template_hook("t", "onlogs", "#!/usr/bin/env bash\ntail -f template.log")
        write_project_hook("proj", "onlogs", "#!/usr/bin/env bash\ntail -f proj.log")
        project = {"name": "proj", "path": "/tmp", "machine": "local", "template": "t"}
        metadata = {"name": "t"}
        cmd = build_hook_command(project, "local", metadata, {}, "onlogs")
        assert "SUPER=" in cmd

    def test_no_super_in_command_for_template_level_hook(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import build_hook_command
        write_template_hook("t", "onlogs", "#!/usr/bin/env bash\ntail -f log")
        project = {"name": "proj", "path": "/tmp", "machine": "local", "template": "t"}
        metadata = {"name": "t"}
        cmd = build_hook_command(project, "local", metadata, {}, "onlogs")
        assert "SUPER=" not in cmd

    def test_template_params_in_hook_command(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import build_hook_command
        write_template_hook("t", "onlogs", "#!/usr/bin/env bash\ntail -f log")
        project = {"name": "proj", "path": "/tmp", "machine": "local", "template": "t"}
        metadata = {"name": "t", "params": {"PORT": "8080", "ENV": "dev"}}
        cmd = build_hook_command(project, "local", metadata, {}, "onlogs")
        assert "COLETTE_PARAM_PORT" in cmd
        assert "8080" in cmd
        assert "COLETTE_PARAM_ENV" in cmd


class TestHookEnvironment:
    """_hook_environment builds the correct env dict."""

    def _call(self, project, machine_name, template_name, machine,
              template_metadata=None, super_path=None):
        from colette_cli.template.executor import _hook_environment
        return _hook_environment(
            project, machine_name, template_name, machine,
            template_metadata, super_path
        )

    def _project(self):
        return {"name": "proj", "path": "/proj", "machine": "local", "template": "t"}

    def test_sets_colette_vars(self):
        env = self._call(self._project(), "local", "tmpl", {})
        assert env["COLETTE_PROJECT_NAME"] == "proj"
        assert env["COLETTE_PROJECT_PATH"] == "/proj"
        assert env["COLETTE_MACHINE_NAME"] == "local"
        assert env["COLETTE_TEMPLATE_NAME"] == "tmpl"

    def test_empty_template_name(self):
        env = self._call(self._project(), "local", None, {})
        assert env["COLETTE_TEMPLATE_NAME"] == ""

    def test_sets_param_vars(self):
        metadata = {"params": {"PORT": "9000", "ENV": "prod"}}
        env = self._call(self._project(), "local", "t", {}, template_metadata=metadata)
        assert env["COLETTE_PARAM_PORT"] == "9000"
        assert env["COLETTE_PARAM_ENV"] == "prod"

    def test_super_set_when_super_path_provided(self):
        from pathlib import Path
        env = self._call(
            self._project(), "local", "t", {},
            super_path=Path("/cfg/templates/t/.onstart")
        )
        assert env["SUPER"] == "/cfg/templates/t/.onstart"

    def test_super_absent_when_super_path_none(self):
        env = self._call(self._project(), "local", "t", {}, super_path=None)
        assert "SUPER" not in env

    def test_inherits_os_environment(self):
        import os
        env = self._call(self._project(), "local", "t", {})
        assert "PATH" in env


class TestResolveHookWithSuperEdgeCases:
    """Edge cases for _resolve_hook_with_super not covered in the main class."""

    def test_no_template_name_and_no_project_hook_returns_none(self, tmp_config):
        from colette_cli.template.executor import _resolve_hook_with_super
        content, super_path = _resolve_hook_with_super("proj", None, "onstart")
        assert content is None
        assert super_path is None

    def test_project_hook_with_no_template_has_no_super(self, tmp_config):
        from colette_cli.utils.config import write_project_hook
        from colette_cli.template.executor import _resolve_hook_with_super
        write_project_hook("proj", "onstart", "#!/usr/bin/env bash\necho proj")
        content, super_path = _resolve_hook_with_super("proj", None, "onstart")
        assert content is not None
        assert super_path is None

    def test_coletterc_resolution_project_over_template(self, tmp_config):
        from colette_cli.utils.config import write_project_hook, write_template_hook
        from colette_cli.template.executor import _resolve_hook_with_super
        write_project_hook("proj", "coletterc", "export PROJ_RC=1\n")
        write_template_hook("t", "coletterc", "export TMPL_RC=1\n")
        content, super_path = _resolve_hook_with_super("proj", "t", "coletterc")
        assert "PROJ_RC=1" in content
        assert super_path is not None
        assert "coletterc" in str(super_path)


class TestPrependColetterrcEdgeCases:
    """Additional edge cases for _prepend_coletterc."""

    def test_no_template_and_no_project_coletterc_returns_command_unchanged(self, tmp_config):
        from colette_cli.template.executor import _prepend_coletterc
        result = _prepend_coletterc("proj", None, "echo hook")
        assert result == "echo hook"

    def test_coletterc_content_appears_before_hook(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import _prepend_coletterc
        write_template_hook("t", "coletterc", "export SETUP=done\n")
        result = _prepend_coletterc("proj", "t", "run_hook")
        lines = result.splitlines()
        setup_idx = next(i for i, l in enumerate(lines) if "SETUP=done" in l)
        hook_idx = next(i for i, l in enumerate(lines) if "run_hook" in l)
        assert setup_idx < hook_idx

    def test_no_super_line_when_using_template_coletterc(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import _prepend_coletterc
        write_template_hook("t", "coletterc", "export VAR=1\n")
        result = _prepend_coletterc("proj", "t", "echo hook")
        assert "SUPER=" not in result


class TestBuildProjectBootstrapEdgeCases:
    """Additional edge cases for build_project_bootstrap."""

    def test_no_template_metadata_returns_exec_bash(self, tmp_config):
        from colette_cli.template.executor import build_project_bootstrap
        project = {"name": "p", "path": "/p", "machine": "local", "template": None}
        result = build_project_bootstrap(project, "local", None)
        assert result == "exec bash"

    def test_template_metadata_without_name_returns_exec_bash(self, tmp_config):
        from colette_cli.template.executor import build_project_bootstrap
        project = {"name": "p", "path": "/p", "machine": "local", "template": None}
        result = build_project_bootstrap(project, "local", {})
        assert result == "exec bash"

    def test_bootstrap_starts_with_exec_bash_rcfile(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import build_project_bootstrap
        write_template_hook("t", "coletterc", "source venv/bin/activate\n")
        project = {"name": "p", "path": "/p", "machine": "local", "template": "t"}
        result = build_project_bootstrap(project, "local", {"name": "t"})
        assert result.startswith("exec bash --rcfile")

    def test_no_super_in_rcfile_when_using_template_coletterc(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import build_project_bootstrap
        import base64
        write_template_hook("t", "coletterc", "export FOO=1\n")
        project = {"name": "p", "path": "/p", "machine": "local", "template": "t"}
        result = build_project_bootstrap(project, "local", {"name": "t"})
        b64_part = result.split("echo ")[1].split(" |")[0].strip("'\"")
        decoded = base64.b64decode(b64_part).decode()
        assert "SUPER=" not in decoded


class TestRunTemplateHookSuperInheritance:
    """Integration tests for $SUPER inheritance in run_template_hook."""

    def test_project_hook_can_source_super_to_run_template_hook(self, tmp_config, tmp_path):
        """A project hook that calls `source $SUPER` runs the template hook too."""
        from colette_cli.utils.config import write_project_hook, write_template_hook
        from colette_cli.template.executor import run_template_hook
        tmpl_marker = tmp_path / "tmpl.txt"
        proj_marker = tmp_path / "proj.txt"
        write_template_hook(
            "t", "onstart",
            f"#!/usr/bin/env bash\necho template > {tmpl_marker}"
        )
        write_project_hook(
            "proj", "onstart",
            f'#!/usr/bin/env bash\nsource "$SUPER"\necho project > {proj_marker}'
        )
        project = {"name": "proj", "path": str(tmp_path), "machine": "local", "template": "t"}
        result = run_template_hook(project, {}, "local", False, {"name": "t"}, "onstart")
        assert result is True
        assert tmpl_marker.read_text().strip() == "template"
        assert proj_marker.read_text().strip() == "project"

    def test_coletterc_super_allows_project_to_extend_template_env(self, tmp_config, tmp_path):
        """Project coletterc can source $SUPER (template coletterc) then add more vars."""
        from colette_cli.utils.config import write_project_hook, write_template_hook
        from colette_cli.template.executor import run_template_hook
        marker = tmp_path / "env.txt"
        write_template_hook("t", "coletterc", "export BASE_VAR=from_template\n")
        write_project_hook("proj", "coletterc", 'source "$SUPER"\nexport EXTRA_VAR=from_project\n')
        write_template_hook(
            "t", "onstart",
            f"#!/usr/bin/env bash\necho $BASE_VAR $EXTRA_VAR > {marker}"
        )
        project = {"name": "proj", "path": str(tmp_path), "machine": "local", "template": "t"}
        run_template_hook(project, {}, "local", False, {"name": "t"}, "onstart")
        result = marker.read_text().strip()
        assert "from_template" in result
        assert "from_project" in result


class TestRunTemplateHookSubprocessIsolation:
    """Hook subprocess must be isolated from the terminal to avoid curses corruption."""

    def test_subprocess_uses_devnull_stdin(self, tmp_config, tmp_path):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import run_template_hook
        from unittest.mock import patch, call
        import subprocess as sp

        write_template_hook("t", "onstart", "#!/usr/bin/env bash\nexit 0")
        project = {"name": "proj", "path": str(tmp_path), "machine": "local", "template": "t"}

        captured_kwargs = {}

        original_run = sp.run
        def capturing_run(cmd, **kwargs):
            if cmd and cmd[0] == "bash":
                captured_kwargs.update(kwargs)
            return original_run(cmd, **kwargs)

        with patch("subprocess.run", side_effect=capturing_run):
            run_template_hook(project, {}, "local", False, {"name": "t"}, "onstart")

        assert captured_kwargs.get("stdin") == sp.DEVNULL
        assert captured_kwargs.get("start_new_session") is True
    """Dead-code fix: fail_on_error=True must exit without also calling warn."""

    def test_fail_on_error_false_warns_and_returns_false(self, tmp_config, capsys):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import run_template_hook
        write_template_hook("t", "onstart", "#!/usr/bin/env bash\nexit 7")
        project = {"name": "proj", "path": "/tmp", "machine": "local", "template": "t"}
        result = run_template_hook(project, {}, "local", False, {"name": "t"}, "onstart", fail_on_error=False)
        assert result is False
        assert "failed" in capsys.readouterr().err

    def test_fail_on_error_true_raises_system_exit(self, tmp_config):
        from colette_cli.utils.config import write_template_hook
        from colette_cli.template.executor import run_template_hook
        import pytest
        write_template_hook("t", "oncreate", "#!/usr/bin/env bash\nexit 3")
        project = {"name": "proj", "path": "/tmp", "machine": "local", "template": "t"}
        with pytest.raises(SystemExit):
            run_template_hook(project, {}, "local", False, {"name": "t"}, "oncreate", fail_on_error=True)


class TestRunTemplateHookPersistsFailures:
    """Hook failures are written to the hook-failures log."""

    def test_failed_hook_appends_to_log(self, tmp_config):
        from colette_cli.utils.config import write_template_hook, load_hook_failures
        from colette_cli.template.executor import run_template_hook
        write_template_hook("t", "onstart", "#!/usr/bin/env bash\necho oops >&2\nexit 1")
        project = {"name": "myproj", "path": "/tmp", "machine": "local", "template": "t"}
        run_template_hook(project, {}, "local", False, {"name": "t"}, "onstart")
        failures = load_hook_failures()
        assert len(failures) == 1
        assert failures[0]["project"] == "myproj"
        assert failures[0]["hook"] == "onstart"
        assert failures[0]["template"] == "t"
        assert failures[0]["exit_code"] == 1
        assert "oops" in failures[0]["output"]

    def test_successful_hook_does_not_append_to_log(self, tmp_config):
        from colette_cli.utils.config import write_template_hook, load_hook_failures
        from colette_cli.template.executor import run_template_hook
        write_template_hook("t", "onstart", "#!/usr/bin/env bash\nexit 0")
        project = {"name": "proj", "path": "/tmp", "machine": "local", "template": "t"}
        run_template_hook(project, {}, "local", False, {"name": "t"}, "onstart")
        assert load_hook_failures() == []

    def test_multiple_failures_accumulate(self, tmp_config):
        from colette_cli.utils.config import write_template_hook, load_hook_failures
        from colette_cli.template.executor import run_template_hook
        write_template_hook("t", "onstart", "#!/usr/bin/env bash\nexit 1")
        project = {"name": "proj", "path": "/tmp", "machine": "local", "template": "t"}
        metadata = {"name": "t"}
        run_template_hook(project, {}, "local", False, metadata, "onstart")
        run_template_hook(project, {}, "local", False, metadata, "onstart")
        assert len(load_hook_failures()) == 2


class TestPrependColetterrcSuperCollision:
    """SUPER is correctly restored after coletterc when hook_super_path is provided."""

    def test_hook_super_path_appears_after_coletterc(self, tmp_config, tmp_path):
        from colette_cli.utils.config import write_project_hook, write_template_hook
        from colette_cli.template.executor import _prepend_coletterc

        write_project_hook("proj", "coletterc", "export PROJ_INIT=1\n")
        write_template_hook("t", "coletterc", "export TMPL_INIT=1\n")

        fake_hook_super = str(tmp_path / "tmpl_onstart")
        result = _prepend_coletterc("proj", "t", "echo hook", hook_super_path=fake_hook_super)

        lines = result.splitlines()
        coletterc_idx = next(i for i, l in enumerate(lines) if "PROJ_INIT=1" in l)
        restore_idx = next(i for i, l in enumerate(lines) if fake_hook_super in l)
        hook_idx = next(i for i, l in enumerate(lines) if "echo hook" in l)
        assert coletterc_idx < restore_idx < hook_idx

    def test_project_hook_super_survives_coletterc(self, tmp_config, tmp_path):
        """$SUPER in the hook still points to the template hook after coletterc runs."""
        from colette_cli.utils.config import write_project_hook, write_template_hook
        from colette_cli.template.executor import run_template_hook

        tmpl_marker = tmp_path / "tmpl.txt"
        proj_marker = tmp_path / "proj.txt"
        coletterc_marker = tmp_path / "rc.txt"

        write_template_hook("t", "coletterc", f"echo rc > {coletterc_marker}\n")
        write_template_hook("t", "onstart", f"#!/usr/bin/env bash\necho template > {tmpl_marker}")
        write_project_hook(
            "proj", "onstart",
            f'#!/usr/bin/env bash\nsource "$SUPER"\necho project > {proj_marker}'
        )
        project = {"name": "proj", "path": str(tmp_path), "machine": "local", "template": "t"}
        result = run_template_hook(project, {}, "local", False, {"name": "t"}, "onstart")

        assert result is True
        assert tmpl_marker.read_text().strip() == "template"
        assert proj_marker.read_text().strip() == "project"
