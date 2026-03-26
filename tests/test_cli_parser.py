"""Tests for colette_cli.cli.parser."""

import pytest
from colette_cli.cli.parser import build_parser


@pytest.fixture()
def parser():
    p, _ = build_parser()
    return p


class TestTopLevelCommands:
    def test_create_command(self, parser):
        args = parser.parse_args(["create", "my-project"])
        assert args.command == "create"
        assert args.name == "my-project"

    def test_create_with_machine_and_template(self, parser):
        args = parser.parse_args(["create", "p", "-m", "local", "-t", "tmpl"])
        assert args.machine == "local"
        assert args.template == "tmpl"

    def test_delete_command(self, parser):
        args = parser.parse_args(["delete", "my-project"])
        assert args.command == "delete"
        assert args.name == "my-project"

    def test_list_command(self, parser):
        args = parser.parse_args(["list"])
        assert args.command == "list"

    def test_link_command(self, parser):
        args = parser.parse_args(["link", "/some/path"])
        assert args.command == "link"
        assert args.path == "/some/path"

    def test_link_with_name_and_machine(self, parser):
        args = parser.parse_args(["link", "/p", "-m", "local", "-n", "my-proj"])
        assert args.name == "my-proj"
        assert args.machine == "local"

    def test_unlink_command(self, parser):
        args = parser.parse_args(["unlink", "my-project"])
        assert args.command == "unlink"
        assert args.name == "my-project"

    def test_attach_command(self, parser):
        args = parser.parse_args(["attach", "proj"])
        assert args.command == "attach"
        assert args.name == "proj"

    def test_code_command(self, parser):
        args = parser.parse_args(["code", "proj"])
        assert args.command == "code"
        assert args.name == "proj"

    def test_start_command_no_args(self, parser):
        args = parser.parse_args(["start"])
        assert args.command == "start"
        assert args.projects == []

    def test_start_with_project_names(self, parser):
        args = parser.parse_args(["start", "a", "b"])
        assert args.projects == ["a", "b"]

    def test_stop_command(self, parser):
        args = parser.parse_args(["stop", "-m", "local"])
        assert args.command == "stop"
        assert args.machine == "local"

    def test_monitor_command(self, parser):
        args = parser.parse_args(["monitor"])
        assert args.command == "monitor"

    def test_logs_command_no_name(self, parser):
        args = parser.parse_args(["logs"])
        assert args.command == "logs"
        assert args.name is None

    def test_logs_command_with_name(self, parser):
        args = parser.parse_args(["logs", "proj"])
        assert args.name == "proj"


class TestConfigSubcommands:
    def test_config_list(self, parser):
        args = parser.parse_args(["config", "list"])
        assert args.config_cmd == "list"

    def test_config_list_templates(self, parser):
        args = parser.parse_args(["config", "list-templates", "local"])
        assert args.config_cmd == "list-templates"
        assert args.machine_name == "local"

    def test_config_add_machine(self, parser):
        args = parser.parse_args(["config", "add-machine"])
        assert args.config_cmd == "add-machine"

    def test_config_edit_machine(self, parser):
        args = parser.parse_args(["config", "edit-machine", "local"])
        assert args.machine_name == "local"

    def test_config_add_template(self, parser):
        args = parser.parse_args(["config", "add-template", "local", "tmpl"])
        assert args.machine_name == "local"
        assert args.template_name == "tmpl"

    def test_config_add_template_with_params(self, parser):
        args = parser.parse_args(["config", "add-template", "local", "tmpl", "--param", "ENV=dev"])
        assert args.params == ["ENV=dev"]

    def test_config_edit_template(self, parser):
        args = parser.parse_args(["config", "edit-template", "local", "tmpl"])
        assert args.template_name == "tmpl"

    def test_config_edit_hook(self, parser):
        args = parser.parse_args(["config", "edit-hook", "tmpl", "onstart"])
        assert args.config_cmd == "edit-hook"
        assert args.template_name == "tmpl"
        assert args.hook_name == "onstart"

    def test_config_edit_hook_invalid_hook(self, parser):
        with pytest.raises(SystemExit):
            parser.parse_args(["config", "edit-hook", "tmpl", "invalid"])

    def test_config_edit_project_hook(self, parser):
        args = parser.parse_args(["config", "edit-project-hook", "my-proj", "onstart"])
        assert args.config_cmd == "edit-project-hook"
        assert args.project_name == "my-proj"
        assert args.hook_name == "onstart"

    def test_config_edit_project_hook_all_hooks(self, parser):
        for hook in ("oncreate", "onstart", "onstop", "onlogs", "coletterc"):
            args = parser.parse_args(["config", "edit-project-hook", "proj", hook])
            assert args.hook_name == hook

    def test_config_remove_template(self, parser):
        args = parser.parse_args(["config", "remove-template", "local", "tmpl"])
        assert args.template_name == "tmpl"

    def test_config_remove_machine(self, parser):
        args = parser.parse_args(["config", "remove-machine", "local"])
        assert args.machine_name == "local"

    def test_config_set_default(self, parser):
        args = parser.parse_args(["config", "set-default", "local"])
        assert args.machine_name == "local"

    def test_config_no_subcommand_has_config_parser_attribute(self, parser):
        args = parser.parse_args(["config"])
        assert args.config_cmd is None
        assert hasattr(args, "config_parser")
        assert args.config_parser is not None

    def test_config_subcommand_also_carries_config_parser(self, parser):
        args = parser.parse_args(["config", "list"])
        assert hasattr(args, "config_parser")
        assert args.config_parser is not None
