"""Tests for colette_cli.utils.config."""

import json
import os
import pytest

from tests.conftest import write_config, write_projects, write_templates


class TestLoadSaveConfig:
    def test_load_config_missing_returns_defaults(self, tmp_config):
        from colette_cli.utils.config import load_config

        cfg = load_config()
        assert cfg == {"machines": {}, "default_machine": None}

    def test_save_and_load_config_roundtrip(self, tmp_config):
        from colette_cli.utils.config import load_config, save_config

        data = {"machines": {"local": {"type": "local"}}, "default_machine": "local"}
        save_config(data)
        assert load_config() == data

    def test_load_projects_missing_returns_empty(self, tmp_config):
        from colette_cli.utils.config import load_projects

        assert load_projects() == []

    def test_save_and_load_projects_roundtrip(self, tmp_config):
        from colette_cli.utils.config import load_projects, save_projects

        projects = [
            {"name": "p", "machine": "local", "path": "/tmp/p", "template": None}
        ]
        save_projects(projects)
        assert load_projects() == projects

    def test_load_templates_missing_returns_defaults(self, tmp_config):
        from colette_cli.utils.config import load_templates

        assert load_templates() == {"templates": []}

    def test_save_and_load_templates_roundtrip(self, tmp_config):
        from colette_cli.utils.config import load_templates, save_templates

        data = {"templates": [{"name": "tmpl"}]}
        save_templates(data)
        assert load_templates() == data


class TestGetProject:
    def test_get_project_found(self, tmp_config):
        from colette_cli.utils.config import get_project, save_projects

        save_projects(
            [{"name": "foo", "machine": "local", "path": "/p", "template": None}]
        )
        project = get_project("foo")
        assert project["name"] == "foo"

    def test_get_project_not_found_returns_none(self, tmp_config):
        from colette_cli.utils.config import get_project

        assert get_project("missing") is None


class TestGetMachine:
    def test_get_machine_found(self, tmp_config):
        from colette_cli.utils.config import get_machine, save_config

        save_config(
            {"machines": {"local": {"type": "local"}}, "default_machine": "local"}
        )
        from colette_cli.utils.config import load_config

        cfg = load_config()
        m = get_machine(cfg, "local")
        assert m == {"type": "local"}

    def test_get_machine_not_found_returns_none(self, tmp_config):
        from colette_cli.utils.config import get_machine

        assert get_machine({}, "nonexistent") is None

    def test_require_machine_exits_when_not_found(self, tmp_config):
        from colette_cli.utils.config import require_machine

        with pytest.raises(SystemExit):
            require_machine({}, "nope")


class TestTemplateHooks:
    def test_get_template_dir(self, tmp_config):
        from colette_cli.utils.config import get_template_dir

        d = get_template_dir("my-tmpl")
        assert str(d).endswith("templates/my-tmpl")

    def test_ensure_template_dir_creates(self, tmp_config):
        from colette_cli.utils.config import ensure_template_dir

        d = ensure_template_dir("new-tmpl")
        assert d.exists()

    def test_write_and_read_template_hook(self, tmp_config):
        from colette_cli.utils.config import write_template_hook, read_template_hook

        write_template_hook("tmpl", "onstart", "#!/usr/bin/env bash\necho hi")
        content = read_template_hook("tmpl", "onstart")
        assert "echo hi" in content

    def test_template_hook_exists_true_and_false(self, tmp_config):
        from colette_cli.utils.config import template_hook_exists, write_template_hook

        assert not template_hook_exists("tmpl", "onstart")
        write_template_hook("tmpl", "onstart", "content")
        assert template_hook_exists("tmpl", "onstart")

    def test_read_template_hook_missing_returns_none(self, tmp_config):
        from colette_cli.utils.config import read_template_hook

        assert read_template_hook("notemplate", "oncreate") is None

    def test_hook_executable_bit(self, tmp_config):
        from colette_cli.utils.config import write_template_hook, get_template_hook_path

        write_template_hook("tmpl", "onstart", "#!/usr/bin/env bash\n")
        path = get_template_hook_path("tmpl", "onstart")
        assert os.access(path, os.X_OK)

    def test_coletterc_not_executable(self, tmp_config):
        from colette_cli.utils.config import write_template_hook, get_template_hook_path

        write_template_hook("tmpl", "coletterc", "# rc\n")
        path = get_template_hook_path("tmpl", "coletterc")
        assert not os.access(path, os.X_OK)

    def test_remove_template_dir(self, tmp_config):
        from colette_cli.utils.config import (
            ensure_template_dir,
            remove_template_dir,
            get_template_dir,
        )

        ensure_template_dir("tmp-tmpl")
        assert get_template_dir("tmp-tmpl").exists()
        remove_template_dir("tmp-tmpl")
        assert not get_template_dir("tmp-tmpl").exists()


class TestProjectHooks:
    def test_get_project_hook_dir(self, tmp_config):
        from colette_cli.utils.config import get_project_hook_dir

        d = get_project_hook_dir("my-proj")
        assert str(d).endswith("projects/my-proj")

    def test_write_and_read_project_hook(self, tmp_config):
        from colette_cli.utils.config import write_project_hook, read_project_hook

        write_project_hook("proj", "onstart", "#!/usr/bin/env bash\necho proj")
        content = read_project_hook("proj", "onstart")
        assert "echo proj" in content

    def test_project_hook_exists(self, tmp_config):
        from colette_cli.utils.config import project_hook_exists, write_project_hook

        assert not project_hook_exists("proj", "onstart")
        write_project_hook("proj", "onstart", "content")
        assert project_hook_exists("proj", "onstart")

    def test_read_project_hook_missing_returns_none(self, tmp_config):
        from colette_cli.utils.config import read_project_hook

        assert read_project_hook("noproject", "onstart") is None

    def test_scaffold_project_hook_files(self, tmp_config):
        from colette_cli.utils.config import (
            scaffold_project_hook_files,
            project_hook_exists,
            read_project_hook,
        )

        scaffold_project_hook_files("proj")
        for hook in ("oncreate", "onstart", "onstop", "onlogs", "onupdate", "ondelete", "coletterc"):
            assert project_hook_exists("proj", hook)
            assert 'source "$SUPER"' in read_project_hook("proj", hook)

    def test_scaffold_project_hook_does_not_overwrite(self, tmp_config):
        from colette_cli.utils.config import (
            scaffold_project_hook_files,
            write_project_hook,
            read_project_hook,
        )

        write_project_hook("proj", "onstart", "custom content")
        scaffold_project_hook_files("proj")
        assert read_project_hook("proj", "onstart") == "custom content"


class TestMachineTemplateHooks:
    def test_get_machine_template_dir(self, tmp_config):
        from colette_cli.utils.config import get_machine_template_dir

        d = get_machine_template_dir("myhost", "dev")
        assert str(d).endswith("machines/myhost/templates/dev")

    def test_get_machine_template_hook_path(self, tmp_config):
        from colette_cli.utils.config import get_machine_template_hook_path

        p = get_machine_template_hook_path("myhost", "dev", "onstart")
        assert "machines/myhost/templates/dev" in str(p)
        assert "onstart" in str(p)

    def test_ensure_machine_template_dir_creates(self, tmp_config):
        from colette_cli.utils.config import ensure_machine_template_dir, get_machine_template_dir

        ensure_machine_template_dir("myhost", "dev")
        assert get_machine_template_dir("myhost", "dev").exists()

    def test_write_and_read_machine_template_hook(self, tmp_config):
        from colette_cli.utils.config import write_machine_template_hook, read_machine_template_hook

        write_machine_template_hook("myhost", "dev", "onstart", "#!/usr/bin/env bash\necho hi")
        content = read_machine_template_hook("myhost", "dev", "onstart")
        assert "echo hi" in content

    def test_machine_template_hook_exists(self, tmp_config):
        from colette_cli.utils.config import machine_template_hook_exists, write_machine_template_hook

        assert not machine_template_hook_exists("myhost", "dev", "onstart")
        write_machine_template_hook("myhost", "dev", "onstart", "content")
        assert machine_template_hook_exists("myhost", "dev", "onstart")

    def test_read_machine_template_hook_missing_returns_none(self, tmp_config):
        from colette_cli.utils.config import read_machine_template_hook

        assert read_machine_template_hook("nohost", "dev", "onstart") is None

    def test_get_machine_template_params_found(self):
        from colette_cli.utils.config import get_machine_template_params

        machine = {"templates": [{"name": "dev", "params": {"PORT": "8080"}}]}
        params = get_machine_template_params(machine, "dev")
        assert params == {"PORT": "8080"}

    def test_get_machine_template_params_not_found(self):
        from colette_cli.utils.config import get_machine_template_params

        machine = {"templates": [{"name": "other", "params": {"PORT": "8080"}}]}
        params = get_machine_template_params(machine, "dev")
        assert params == {}

    def test_get_machine_template_params_no_params_key(self):
        from colette_cli.utils.config import get_machine_template_params

        machine = {"templates": [{"name": "dev"}]}
        params = get_machine_template_params(machine, "dev")
        assert params == {}

    def test_get_machine_template_params_empty_machine(self):
        from colette_cli.utils.config import get_machine_template_params

        assert get_machine_template_params({}, "dev") == {}
