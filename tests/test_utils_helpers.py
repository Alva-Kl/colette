"""Tests for colette_cli.utils.helpers."""

from colette_cli.utils.helpers import build_projects_by_machine, filter_projects_by_name


class TestDetectProjectFromCwd:
    def test_returns_project_name_when_cwd_matches(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_local_projects
        from colette_cli.utils.helpers import detect_project_from_cwd
        project_path = tmp_path / "my-project"
        project_path.mkdir()
        save_local_projects([{"name": "my-project", "machine": "local", "path": str(project_path)}])

        import os
        orig = os.getcwd()
        try:
            os.chdir(str(project_path))
            result = detect_project_from_cwd()
        finally:
            os.chdir(orig)

        assert result == "my-project"

    def test_returns_none_when_cwd_does_not_match(self, tmp_config, tmp_path):
        from colette_cli.utils.config import save_local_projects
        from colette_cli.utils.helpers import detect_project_from_cwd
        project_path = tmp_path / "my-project"
        project_path.mkdir()
        other_path = tmp_path / "other"
        other_path.mkdir()
        save_local_projects([{"name": "my-project", "machine": "local", "path": str(project_path)}])

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


class TestIterMachineProjects:
    """iter_machine_projects yields (machine_name, projects, machine, is_remote)."""

    def _make_projects(self):
        return [
            {"name": "a", "machine": "local"},
            {"name": "b", "machine": "local"},
            {"name": "c", "machine": "remote"},
        ]

    def _make_cfg(self):
        return {
            "machines": {
                "local": {"type": "local"},
                "remote": {"type": "ssh", "host": "myhost"},
            }
        }

    def test_yields_all_machines_no_filter(self, tmp_config):
        from colette_cli.utils.helpers import iter_machine_projects
        projects = self._make_projects()
        cfg = self._make_cfg()
        results = list(iter_machine_projects(projects, cfg))
        machine_names = [r[0] for r in results]
        assert sorted(machine_names) == ["local", "remote"]

    def test_yields_correct_project_lists(self, tmp_config):
        from colette_cli.utils.helpers import iter_machine_projects
        projects = self._make_projects()
        cfg = self._make_cfg()
        by_name = {r[0]: r[1] for r in iter_machine_projects(projects, cfg)}
        assert [p["name"] for p in by_name["local"]] == ["a", "b"]
        assert [p["name"] for p in by_name["remote"]] == ["c"]

    def test_filter_machine(self, tmp_config):
        from colette_cli.utils.helpers import iter_machine_projects
        projects = self._make_projects()
        cfg = self._make_cfg()
        results = list(iter_machine_projects(projects, cfg, filter_machine="local"))
        assert len(results) == 1
        assert results[0][0] == "local"

    def test_filter_names(self, tmp_config):
        from colette_cli.utils.helpers import iter_machine_projects
        projects = self._make_projects()
        cfg = self._make_cfg()
        results = list(iter_machine_projects(projects, cfg, filter_names=["a"]))
        machine_names = [r[0] for r in results]
        assert "remote" not in machine_names
        local_result = next(r for r in results if r[0] == "local")
        assert [p["name"] for p in local_result[1]] == ["a"]

    def test_is_remote_flag(self, tmp_config):
        from colette_cli.utils.helpers import iter_machine_projects
        projects = self._make_projects()
        cfg = self._make_cfg()
        by_name = {r[0]: r[3] for r in iter_machine_projects(projects, cfg)}
        assert by_name["local"] is False
        assert by_name["remote"] is True

    def test_skips_machine_when_all_projects_filtered_out(self, tmp_config):
        from colette_cli.utils.helpers import iter_machine_projects
        projects = self._make_projects()
        cfg = self._make_cfg()
        # filter_names matches only "a" in local; remote should be skipped
        results = list(iter_machine_projects(projects, cfg, filter_names=["a"]))
        assert all(r[0] != "remote" for r in results)

    def test_sorted_by_machine_name(self, tmp_config):
        from colette_cli.utils.helpers import iter_machine_projects
        projects = self._make_projects()
        cfg = self._make_cfg()
        names = [r[0] for r in iter_machine_projects(projects, cfg)]
        assert names == sorted(names)

    def test_unknown_machine_resolves_to_empty_dict(self, tmp_config):
        from colette_cli.utils.helpers import iter_machine_projects
        projects = [{"name": "x", "machine": "ghost"}]
        cfg = {"machines": {}}
        results = list(iter_machine_projects(projects, cfg))
        assert len(results) == 1
        _, _, machine, is_remote = results[0]
        assert machine == {}
        assert is_remote is False


class TestAllTemplateNames:
    def test_returns_names_from_all_machines(self, tmp_config):
        from tests.conftest import write_config
        from colette_cli.utils.helpers import all_template_names
        write_config(tmp_config, {
            "machines": {
                "local": {"type": "local", "templates": [{"name": "foo"}, {"name": "bar"}]},
                "remote": {"type": "ssh", "templates": [{"name": "baz"}]},
            }
        })
        assert all_template_names() == {"foo", "bar", "baz"}

    def test_empty_when_no_machines(self, tmp_config):
        from tests.conftest import write_config
        from colette_cli.utils.helpers import all_template_names
        write_config(tmp_config, {"machines": {}})
        assert all_template_names() == set()

    def test_accepts_cfg_arg(self):
        from colette_cli.utils.helpers import all_template_names
        cfg = {"machines": {"local": {"templates": [{"name": "my-tmpl"}]}}}
        assert all_template_names(cfg) == {"my-tmpl"}

    def test_includes_cache_only_names_for_remote_machines(self, tmp_config):
        """A remote's own templates, known only via the sync cache (never
        configured on this controller), still count toward the shared
        project/template namespace."""
        from tests.conftest import write_config
        from colette_cli.utils.config import save_machine_cache
        from colette_cli.utils.helpers import all_template_names
        write_config(tmp_config, {
            "machines": {
                "local": {"type": "local", "templates": [{"name": "foo"}]},
                "remote": {"type": "ssh", "templates": []},
            }
        })
        save_machine_cache("remote", {
            "machine": "remote", "synced_at": "x", "projects_dir": "",
            "templates": [{"name": "docker-deployed"}], "projects": [],
        })
        assert all_template_names() == {"foo", "docker-deployed"}


class TestFindTemplateAsProject:
    def _cfg(self):
        return {
            "machines": {
                "local": {
                    "type": "local",
                    "templates": [
                        {"name": "my-tmpl", "type": "directory", "path": "/tmp/my-tmpl"},
                        {"name": "git-tmpl", "type": "git", "url": "https://example.com/repo"},
                        {"name": "no-path-tmpl", "type": "directory", "path": ""},
                    ],
                }
            }
        }

    def test_returns_project_like_dict_for_directory_template(self):
        from colette_cli.utils.helpers import find_template_as_project
        result = find_template_as_project("my-tmpl", self._cfg())
        assert result == {
            "name": "my-tmpl",
            "machine": "local",
            "path": "/tmp/my-tmpl",
            "template": "my-tmpl",
        }

    def test_returns_none_for_git_type(self):
        from colette_cli.utils.helpers import find_template_as_project
        assert find_template_as_project("git-tmpl", self._cfg()) is None

    def test_returns_none_for_missing_path(self):
        from colette_cli.utils.helpers import find_template_as_project
        assert find_template_as_project("no-path-tmpl", self._cfg()) is None

    def test_returns_none_when_not_found(self):
        from colette_cli.utils.helpers import find_template_as_project
        assert find_template_as_project("nonexistent", self._cfg()) is None
