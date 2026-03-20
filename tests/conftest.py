"""Shared fixtures for the Colette test suite."""

import json
import pytest


@pytest.fixture()
def tmp_config(tmp_path, monkeypatch):
    """Redirect all colette config paths to a temporary directory."""
    config_dir = tmp_path / ".config" / "colette"
    config_dir.mkdir(parents=True)
    templates_dir = config_dir / "templates"
    templates_dir.mkdir()
    projects_dir = config_dir / "projects"
    projects_dir.mkdir()

    import colette_cli.utils.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", config_dir / "config.json")
    monkeypatch.setattr(cfg_mod, "PROJECTS_FILE", config_dir / "projects.json")
    monkeypatch.setattr(cfg_mod, "TEMPLATES_FILE", config_dir / "templates.json")
    monkeypatch.setattr(cfg_mod, "TEMPLATE_SCRIPTS_DIR", templates_dir)
    monkeypatch.setattr(cfg_mod, "PROJECT_HOOKS_DIR", projects_dir)

    return config_dir


def write_config(config_dir, cfg):
    (config_dir / "config.json").write_text(json.dumps(cfg))


def write_projects(config_dir, projects):
    (config_dir / "projects.json").write_text(json.dumps(projects))


def write_templates(config_dir, templates):
    (config_dir / "templates.json").write_text(json.dumps(templates))


def make_local_machine(projects_dir="/tmp/projects"):
    return {"type": "local", "projects_dir": projects_dir, "templates": []}


def make_project(name="proj", machine="local", path="/tmp/projects/proj", template=None):
    return {"name": name, "machine": machine, "path": path, "template": template}
