"""Tests for colette_cli.template.registry."""

import pytest


class TestScaffoldTemplateHookFiles:
    def test_creates_all_hooks(self, tmp_config):
        from colette_cli.template.registry import scaffold_template_hook_files, SCRIPT_KEYS
        from colette_cli.utils.config import machine_template_hook_exists
        scaffold_template_hook_files("tmpl", "myhost")
        for key in SCRIPT_KEYS:
            assert machine_template_hook_exists("myhost", "tmpl", key)

    def test_does_not_overwrite_existing(self, tmp_config):
        from colette_cli.template.registry import scaffold_template_hook_files
        from colette_cli.utils.config import write_machine_template_hook, read_machine_template_hook
        write_machine_template_hook("myhost", "tmpl", "onstart", "custom")
        scaffold_template_hook_files("tmpl", "myhost")
        assert read_machine_template_hook("myhost", "tmpl", "onstart") == "custom"

    def test_default_shell_hook_content(self, tmp_config):
        from colette_cli.template.registry import scaffold_template_hook_files
        from colette_cli.utils.config import read_machine_template_hook
        scaffold_template_hook_files("tmpl", "myhost")
        content = read_machine_template_hook("myhost", "tmpl", "onstart")
        assert "#!/usr/bin/env bash" in content

    def test_default_coletterc_content(self, tmp_config):
        from colette_cli.template.registry import scaffold_template_hook_files
        from colette_cli.utils.config import read_machine_template_hook
        scaffold_template_hook_files("tmpl", "myhost")
        content = read_machine_template_hook("myhost", "tmpl", "coletterc")
        assert "#!/usr/bin/env bash" not in content
        assert "tmpl" in content


class TestNormalizeMachineTemplates:
    def test_empty_machine_returns_empty(self):
        from colette_cli.template.registry import normalize_machine_templates
        assert normalize_machine_templates({}) == []

    def test_returns_templates_list(self):
        from colette_cli.template.registry import normalize_machine_templates
        machine = {"templates": [{"name": "t", "type": "directory", "path": "/p"}]}
        assert normalize_machine_templates(machine) == machine["templates"]


class TestGetMachineTemplate:
    def test_finds_template(self):
        from colette_cli.template.registry import get_machine_template
        machine = {"templates": [{"name": "t1", "type": "git", "url": "http://x"}]}
        assert get_machine_template(machine, "t1")["url"] == "http://x"

    def test_returns_none_when_not_found(self):
        from colette_cli.template.registry import get_machine_template
        assert get_machine_template({}, "missing") is None


class TestListMachineTemplateNames:
    def test_returns_names(self):
        from colette_cli.template.registry import list_machine_template_names
        machine = {"templates": [{"name": "a"}, {"name": "b"}]}
        assert list_machine_template_names(machine) == ["a", "b"]

    def test_empty_machine_returns_empty(self):
        from colette_cli.template.registry import list_machine_template_names
        assert list_machine_template_names({}) == []


class TestListCreatableTemplates:
    def test_local_machine_returns_own_templates_only(self, tmp_config):
        from colette_cli.template.registry import list_creatable_templates
        machine = {"type": "local", "templates": [{"name": "a", "type": "directory", "path": "/p"}]}
        assert list_creatable_templates(machine, "local") == machine["templates"]

    def test_ssh_machine_with_no_cache_returns_own_templates_only(self, tmp_config):
        from colette_cli.template.registry import list_creatable_templates
        machine = {"type": "ssh", "host": "h", "templates": [{"name": "a"}]}
        assert list_creatable_templates(machine, "remote") == machine["templates"]

    def test_ssh_machine_merges_cached_templates(self, tmp_config):
        from colette_cli.utils.config import save_machine_cache
        from colette_cli.template.registry import list_creatable_templates
        save_machine_cache("remote", {
            "machine": "remote",
            "synced_at": "2026-01-01T00:00:00Z",
            "projects_dir": "/home/user",
            "templates": [{"name": "docker-deployed", "type": "directory", "path": "~/tmpl"}],
            "projects": [],
        })
        machine = {"type": "ssh", "host": "h", "templates": []}
        names = [t["name"] for t in list_creatable_templates(machine, "remote")]
        assert names == ["docker-deployed"]

    def test_local_template_takes_precedence_over_cache_on_name_collision(self, tmp_config):
        from colette_cli.utils.config import save_machine_cache
        from colette_cli.template.registry import list_creatable_templates
        save_machine_cache("remote", {
            "machine": "remote",
            "synced_at": "2026-01-01T00:00:00Z",
            "projects_dir": "/home/user",
            "templates": [{"name": "tmpl", "type": "directory", "path": "/cached/path"}],
            "projects": [],
        })
        machine = {
            "type": "ssh",
            "host": "h",
            "templates": [{"name": "tmpl", "type": "directory", "path": "/local/path"}],
        }
        result = list_creatable_templates(machine, "remote")
        assert len(result) == 1
        assert result[0]["path"] == "/local/path"

    def test_local_machine_ignores_any_stray_cache_file(self, tmp_config):
        """Cache merging is gated on type == 'ssh' — a local machine's own
        entry never gets cache-derived templates even if a cache file exists."""
        from colette_cli.utils.config import save_machine_cache
        from colette_cli.template.registry import list_creatable_templates
        save_machine_cache("local", {
            "machine": "local", "synced_at": "x", "projects_dir": "",
            "templates": [{"name": "should-not-appear"}], "projects": [],
        })
        machine = {"type": "local", "templates": []}
        assert list_creatable_templates(machine, "local") == []


class TestGetCreatableTemplate:
    def test_finds_local_template(self, tmp_config):
        from colette_cli.template.registry import get_creatable_template
        machine = {"type": "local", "templates": [{"name": "a", "path": "/p"}]}
        assert get_creatable_template(machine, "local", "a")["path"] == "/p"

    def test_finds_cached_template(self, tmp_config):
        from colette_cli.utils.config import save_machine_cache
        from colette_cli.template.registry import get_creatable_template
        save_machine_cache("remote", {
            "machine": "remote", "synced_at": "x", "projects_dir": "",
            "templates": [{"name": "docker-deployed", "type": "directory", "path": "~/tmpl"}],
            "projects": [],
        })
        machine = {"type": "ssh", "host": "h", "templates": []}
        found = get_creatable_template(machine, "remote", "docker-deployed")
        assert found["path"] == "~/tmpl"

    def test_returns_none_when_missing(self, tmp_config):
        from colette_cli.template.registry import get_creatable_template
        assert get_creatable_template({"type": "ssh"}, "remote", "missing") is None


class TestListCreatableTemplateNames:
    def test_merges_local_and_cached_names(self, tmp_config):
        from colette_cli.utils.config import save_machine_cache
        from colette_cli.template.registry import list_creatable_template_names
        save_machine_cache("remote", {
            "machine": "remote", "synced_at": "x", "projects_dir": "",
            "templates": [{"name": "cached-tmpl"}], "projects": [],
        })
        machine = {"type": "ssh", "host": "h", "templates": [{"name": "local-tmpl"}]}
        names = list_creatable_template_names(machine, "remote")
        assert set(names) == {"local-tmpl", "cached-tmpl"}


class TestListMachineTemplateHookPaths:
    def test_returns_existing_hooks(self, tmp_config):
        from colette_cli.template.registry import scaffold_template_hook_files, list_machine_template_hook_paths
        scaffold_template_hook_files("tmpl", "myhost")
        paths = list_machine_template_hook_paths("myhost", "tmpl")
        assert "onstart" in paths
        assert "oncreate" in paths


class TestGetTemplateMetadata:
    def test_reads_description_and_params_from_machine_entry(self, tmp_config):
        from colette_cli.template.registry import get_template_metadata
        machine = {
            "type": "local",
            "templates": [{"name": "tmpl", "description": "A template", "params": {"KEY": "val"}}],
        }
        metadata = get_template_metadata(machine, "local", "tmpl")
        assert metadata["description"] == "A template"
        assert metadata["params"] == {"KEY": "val"}

    def test_no_description_or_params_when_machine_entry_lacks_them(self, tmp_config):
        from colette_cli.template.registry import get_template_metadata
        machine = {"type": "local", "templates": [{"name": "tmpl"}]}
        metadata = get_template_metadata(machine, "local", "tmpl")
        assert "description" not in metadata
        assert "params" not in metadata

    def test_returns_none_without_template_name(self, tmp_config):
        from colette_cli.template.registry import get_template_metadata
        assert get_template_metadata({}, "local", None) is None

    def test_scaffolds_hooks_and_reports_hooks_dir(self, tmp_config):
        from colette_cli.template.registry import get_template_metadata
        from colette_cli.utils.config import machine_template_hook_exists
        machine = {"type": "local", "templates": [{"name": "tmpl"}]}
        metadata = get_template_metadata(machine, "local", "tmpl")
        assert machine_template_hook_exists("local", "tmpl", "oncreate")
        assert metadata["hooks_dir"].endswith("machines/local/templates/tmpl")
        assert "oncreate" in metadata["scripts"]
