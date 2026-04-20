"""Tests for colette_cli.template.registry."""

import pytest


class TestScaffoldTemplateHookFiles:
    def test_creates_all_hooks(self, tmp_config):
        from colette_cli.template.registry import scaffold_template_hook_files, SCRIPT_KEYS
        from colette_cli.utils.config import template_hook_exists
        scaffold_template_hook_files("tmpl")
        for key in SCRIPT_KEYS:
            assert template_hook_exists("tmpl", key)

    def test_does_not_overwrite_existing(self, tmp_config):
        from colette_cli.template.registry import scaffold_template_hook_files
        from colette_cli.utils.config import write_template_hook, read_template_hook
        write_template_hook("tmpl", "onstart", "custom")
        scaffold_template_hook_files("tmpl")
        assert read_template_hook("tmpl", "onstart") == "custom"

    def test_default_shell_hook_content(self, tmp_config):
        from colette_cli.template.registry import scaffold_template_hook_files
        from colette_cli.utils.config import read_template_hook
        scaffold_template_hook_files("tmpl")
        content = read_template_hook("tmpl", "onstart")
        assert "#!/usr/bin/env bash" in content

    def test_default_coletterc_content(self, tmp_config):
        from colette_cli.template.registry import scaffold_template_hook_files
        from colette_cli.utils.config import read_template_hook
        scaffold_template_hook_files("tmpl")
        content = read_template_hook("tmpl", "coletterc")
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


class TestUpsertTemplateMetadata:
    def test_inserts_new(self):
        from colette_cli.template.registry import upsert_template_metadata
        cfg = {"templates": []}
        upsert_template_metadata(cfg, "t1", "A template", {"KEY": "val"})
        assert len(cfg["templates"]) == 1
        assert cfg["templates"][0]["name"] == "t1"
        assert cfg["templates"][0]["description"] == "A template"

    def test_updates_existing(self):
        from colette_cli.template.registry import upsert_template_metadata
        cfg = {"templates": [{"name": "t1", "description": "old"}]}
        upsert_template_metadata(cfg, "t1", "new desc")
        assert cfg["templates"][0]["description"] == "new desc"

    def test_keeps_existing_params_when_none_passed(self):
        from colette_cli.template.registry import upsert_template_metadata
        cfg = {"templates": [{"name": "t1", "params": {"K": "v"}}]}
        upsert_template_metadata(cfg, "t1", "desc", None)
        assert cfg["templates"][0].get("params") == {"K": "v"}

    def test_removes_params_when_empty_dict(self):
        from colette_cli.template.registry import upsert_template_metadata
        cfg = {"templates": [{"name": "t1", "params": {"K": "v"}}]}
        upsert_template_metadata(cfg, "t1", None, {})
        assert "params" not in cfg["templates"][0]


class TestRemoveTemplateMetadata:
    def test_removes_by_name(self):
        from colette_cli.template.registry import remove_template_metadata
        cfg = {"templates": [{"name": "t1"}, {"name": "t2"}]}
        remove_template_metadata(cfg, "t1")
        assert len(cfg["templates"]) == 1
        assert cfg["templates"][0]["name"] == "t2"

    def test_missing_name_is_noop(self):
        from colette_cli.template.registry import remove_template_metadata
        cfg = {"templates": [{"name": "t1"}]}
        remove_template_metadata(cfg, "nope")
        assert len(cfg["templates"]) == 1


class TestListTemplateHookPaths:
    def test_returns_existing_hooks(self, tmp_config):
        from colette_cli.template.registry import scaffold_template_hook_files, list_template_hook_paths
        scaffold_template_hook_files("tmpl")
        paths = list_template_hook_paths("tmpl")
        assert "onstart" in paths
        assert "oncreate" in paths


class TestScaffoldMachineTemplateHookFiles:
    def test_creates_all_hook_files(self, tmp_config):
        from colette_cli.template.registry import scaffold_machine_template_hook_files
        from colette_cli.utils.config import machine_template_hook_exists

        scaffold_machine_template_hook_files("myhost", "dev")
        for hook in ("oncreate", "onstart", "onstop", "onlogs", "coletterc"):
            assert machine_template_hook_exists("myhost", "dev", hook)

    def test_does_not_overwrite_existing(self, tmp_config):
        from colette_cli.template.registry import scaffold_machine_template_hook_files
        from colette_cli.utils.config import write_machine_template_hook, read_machine_template_hook

        write_machine_template_hook("myhost", "dev", "onstart", "custom content")
        scaffold_machine_template_hook_files("myhost", "dev")
        assert read_machine_template_hook("myhost", "dev", "onstart") == "custom content"
