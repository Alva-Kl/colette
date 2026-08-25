"""Tests for colette_cli.utils.config."""

import json
import pytest

from tests.conftest import write_config, write_projects


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

    def test_load_local_projects_missing_returns_empty(self, tmp_config):
        from colette_cli.utils.config import load_local_projects

        assert load_local_projects() == []

    def test_save_and_load_local_projects_roundtrip(self, tmp_config):
        from colette_cli.utils.config import load_local_projects, save_local_projects

        projects = [
            {"name": "p", "machine": "local", "path": "/tmp/p", "template": None}
        ]
        save_local_projects(projects)
        assert load_local_projects() == projects

    def test_load_projects_matches_local_when_no_remotes(self, tmp_config):
        """With no remote machines configured, the merged view equals local projects."""
        from colette_cli.utils.config import load_projects, save_local_projects

        projects = [
            {"name": "p", "machine": "local", "path": "/tmp/p", "template": None}
        ]
        save_local_projects(projects)
        assert load_projects() == projects

    def test_load_projects_merges_remote_cache(self, tmp_config):
        """load_projects() merges in cached remote projects, tagged _cached and
        remapped to the controller's connection name for that machine."""
        from colette_cli.utils.config import load_projects, save_config, save_local_projects, save_machine_cache

        save_config({
            "machines": {
                "local": {"type": "local", "projects_dir": "/tmp"},
                "myserver": {"type": "ssh", "host": "server", "colette_path": "/bin/colette"},
            },
            "default_machine": "local",
        })
        save_local_projects([{"name": "local-proj", "machine": "local", "path": "/tmp/local-proj", "template": None}])
        save_machine_cache("myserver", {
            "machine": "myserver",
            "synced_at": "2026-01-01T00:00:00Z",
            "projects_dir": "/home/user",
            "templates": [],
            "projects": [
                {"name": "remote-proj", "machine": "local", "path": "/home/user/remote-proj", "template": None}
            ],
        })

        projects = load_projects()
        names = {p["name"] for p in projects}
        assert names == {"local-proj", "remote-proj"}

        remote = next(p for p in projects if p["name"] == "remote-proj")
        assert remote["machine"] == "myserver"
        assert remote["_cached"] is True
        assert remote["_synced_at"] == "2026-01-01T00:00:00Z"

        local = next(p for p in projects if p["name"] == "local-proj")
        assert "_cached" not in local

    def test_load_projects_ignores_cache_for_unconfigured_machine(self, tmp_config):
        """A stray cache file for a machine no longer in config.json is ignored."""
        from colette_cli.utils.config import load_projects, save_config, save_local_projects, save_machine_cache

        save_config({"machines": {"local": {"type": "local", "projects_dir": "/tmp"}}, "default_machine": "local"})
        save_local_projects([])
        save_machine_cache("ghost", {"machine": "ghost", "synced_at": "x", "projects_dir": "", "templates": [], "projects": [{"name": "orphan", "machine": "local", "path": "/x", "template": None}]})

        assert load_projects() == []

class TestGetProject:
    def test_get_project_found(self, tmp_config):
        from colette_cli.utils.config import get_project, save_local_projects

        save_local_projects(
            [{"name": "foo", "machine": "local", "path": "/p", "template": None}]
        )
        project = get_project("foo")
        assert project["name"] == "foo"

    def test_get_project_not_found_returns_none_with_no_remotes(self, tmp_config):
        """With no remote machines configured, there's nothing to fall back to."""
        from colette_cli.utils.config import get_project

        assert get_project("missing") is None

    def test_get_project_falls_back_to_live_ssh_check(self, tmp_config):
        """A miss in the merged local+cache view triggers a live self-report
        check against configured remote machines, and patches the cache."""
        from unittest.mock import patch
        from colette_cli.utils.config import get_project, load_machine_cache, save_config, save_local_projects

        save_config({
            "machines": {
                "local": {"type": "local", "projects_dir": "/tmp"},
                "myserver": {"type": "ssh", "host": "server", "colette_path": "/bin/colette"},
            },
            "default_machine": "local",
        })
        save_local_projects([])

        report = {
            "machine": {"projects_dir": "/home/user", "templates": []},
            "projects": [{"name": "fresh-proj", "machine": "local", "path": "/home/user/fresh-proj", "template": None}],
        }
        with patch("colette_cli.utils.ssh.fetch_self_report", return_value=report):
            project = get_project("fresh-proj")

        assert project is not None
        assert project["machine"] == "myserver"
        assert project["_cached"] is True

        cache = load_machine_cache("myserver")
        assert cache["projects"] == report["projects"]

    def test_get_project_returns_none_when_remote_check_also_misses(self, tmp_config):
        from unittest.mock import patch
        from colette_cli.utils.config import get_project, save_config, save_local_projects

        save_config({
            "machines": {"myserver": {"type": "ssh", "host": "server", "colette_path": "/bin/colette"}},
            "default_machine": "myserver",
        })
        save_local_projects([])

        report = {"machine": {"projects_dir": "/home/user", "templates": []}, "projects": []}
        with patch("colette_cli.utils.ssh.fetch_self_report", return_value=report):
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
