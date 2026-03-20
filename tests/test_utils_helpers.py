"""Tests for colette_cli.utils.helpers."""

from colette_cli.utils.helpers import build_projects_by_machine, filter_projects_by_name


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
