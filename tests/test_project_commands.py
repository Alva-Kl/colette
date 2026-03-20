"""Tests for colette_cli.project.commands."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from tests.conftest import write_config, write_projects, make_local_machine, make_project


LOCAL_CFG = {
    "machines": {"local": make_local_machine()},
    "default_machine": "local",
}


class TestRequireProject:
    def test_returns_project_when_found(self, tmp_config):
        from colette_cli.utils.config import save_projects
        from colette_cli.project.commands import require_project
        save_projects([make_project("proj")])
        p = require_project("proj")
        assert p["name"] == "proj"

    def test_exits_when_not_found(self, tmp_config):
        from colette_cli.project.commands import require_project
        with pytest.raises(SystemExit):
            require_project("missing")


class TestCmdList:
    def test_no_projects_prints_message(self, tmp_config, capsys):
        from colette_cli.project.commands import cmd_list
        cmd_list(MagicMock())
        assert "No projects" in capsys.readouterr().out

    def test_lists_projects_by_machine(self, tmp_config, capsys):
        from colette_cli.utils.config import save_projects
        from colette_cli.project.commands import cmd_list
        save_projects([make_project("alpha"), make_project("beta")])
        cmd_list(MagicMock())
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" in out


class TestCmdLink:
    def test_links_existing_local_path(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, load_projects
        from colette_cli.project.commands import cmd_link
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "existing"
        project_dir.mkdir()
        args = MagicMock()
        args.path = str(project_dir)
        args.machine = "local"
        args.name = "my-project"
        cmd_link(args)
        projects = load_projects()
        assert any(p["name"] == "my-project" for p in projects)

    def test_link_derives_name_from_path(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, load_projects
        from colette_cli.project.commands import cmd_link
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "derived-name"
        project_dir.mkdir()
        args = MagicMock()
        args.path = str(project_dir)
        args.machine = "local"
        args.name = None
        cmd_link(args)
        projects = load_projects()
        assert any(p["name"] == "derived-name" for p in projects)

    def test_link_fails_when_path_missing(self, tmp_config):
        from colette_cli.utils.config import save_config
        from colette_cli.project.commands import cmd_link
        save_config(LOCAL_CFG)
        args = MagicMock()
        args.path = "/nonexistent/path"
        args.machine = "local"
        args.name = "proj"
        with pytest.raises(SystemExit):
            cmd_link(args)

    def test_link_fails_on_duplicate_name(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.project.commands import cmd_link
        save_config(LOCAL_CFG)
        save_projects([make_project("existing")])
        project_dir = tmp_path / "existing"
        project_dir.mkdir()
        args = MagicMock()
        args.path = str(project_dir)
        args.machine = "local"
        args.name = "existing"
        with pytest.raises(SystemExit):
            cmd_link(args)

    def test_link_fails_on_invalid_name(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config
        from colette_cli.project.commands import cmd_link
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "some-dir"
        project_dir.mkdir()
        args = MagicMock()
        args.path = str(project_dir)
        args.machine = "local"
        args.name = "Invalid_Name"
        with pytest.raises(SystemExit):
            cmd_link(args)


class TestCmdUnlink:
    def test_unlinks_project_on_confirmation(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects, load_projects
        from colette_cli.project.commands import cmd_unlink
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        args = MagicMock()
        args.name = "proj"
        with patch("builtins.input", return_value="y"):
            cmd_unlink(args)
        assert load_projects() == []

    def test_unlink_aborts_on_no(self, tmp_config):
        from colette_cli.utils.config import save_config, save_projects, load_projects
        from colette_cli.project.commands import cmd_unlink
        save_config(LOCAL_CFG)
        save_projects([make_project("proj")])
        args = MagicMock()
        args.name = "proj"
        with patch("builtins.input", return_value="n"):
            cmd_unlink(args)
        assert len(load_projects()) == 1

    def test_unlink_does_not_delete_files(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_projects
        from colette_cli.project.commands import cmd_unlink
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        save_projects([make_project("proj", path=str(project_dir))])
        args = MagicMock()
        args.name = "proj"
        with patch("builtins.input", return_value="y"):
            cmd_unlink(args)
        assert project_dir.exists()

    def test_unlink_fails_on_missing_project(self, tmp_config):
        from colette_cli.project.commands import cmd_unlink
        args = MagicMock()
        args.name = "missing"
        with pytest.raises(SystemExit):
            cmd_unlink(args)


class TestCmdDelete:
    def test_delete_removes_files_and_record(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_projects, load_projects
        from colette_cli.project.commands import cmd_delete
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        save_projects([make_project("proj", path=str(project_dir))])
        args = MagicMock()
        args.name = "proj"
        with patch("builtins.input", return_value="proj"):
            cmd_delete(args)
        assert not project_dir.exists()
        assert load_projects() == []

    def test_delete_aborts_on_wrong_name(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_config, save_projects, load_projects
        from colette_cli.project.commands import cmd_delete
        save_config(LOCAL_CFG)
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        save_projects([make_project("proj", path=str(project_dir))])
        args = MagicMock()
        args.name = "proj"
        with patch("builtins.input", return_value="wrong"):
            cmd_delete(args)
        assert project_dir.exists()
        assert len(load_projects()) == 1
