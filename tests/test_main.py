"""Tests for colette_cli.main — the top-level CLI dispatcher."""

import sys
import pytest
from argparse import Namespace
from unittest.mock import patch, MagicMock


class TestMainHelpPaths:
    def test_zero_argv_prints_help_and_exits_zero(self):
        from colette_cli.main import main
        with patch.object(sys, "argv", ["colette"]), \
             patch("argparse.ArgumentParser.print_help") as mock_help:
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 0
        mock_help.assert_called_once()

    def test_unmapped_command_falls_through_to_help_and_exits_one(self):
        """Defensive branch: if args.command somehow doesn't match any handler
        (structurally unreachable via real argv, since subparsers restrict
        valid choices), main() must still fail safely via help + exit(1)."""
        from colette_cli.main import main
        fake_parser = MagicMock()
        fake_parser.parse_args.return_value = Namespace(command="not-a-real-command")
        with patch.object(sys, "argv", ["colette", "not-a-real-command"]), \
             patch("colette_cli.main.build_parser", return_value=(fake_parser, {})):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 1
        fake_parser.print_help.assert_called_once()


class TestMainDispatch:
    """Each handler is reached via real argv parsing (not mocked build_parser),
    with only the handler function itself mocked out."""

    def test_config_dispatches(self):
        from colette_cli.main import main
        with patch.object(sys, "argv", ["colette", "config", "list"]), \
             patch("colette_cli.main.cmd_config") as mock_cmd:
            main()
        mock_cmd.assert_called_once()
        assert mock_cmd.call_args[0][0].command == "config"

    def test_tui_dispatches(self):
        from colette_cli.main import main
        with patch.object(sys, "argv", ["colette", "tui"]), \
             patch("colette_cli.main.cmd_tui") as mock_cmd:
            main()
        mock_cmd.assert_called_once()

    def test_create_dispatches_with_name_and_flags(self):
        from colette_cli.main import main
        with patch.object(sys, "argv", ["colette", "create", "my-proj", "-m", "local", "-t", "mytmpl"]), \
             patch("colette_cli.main.cmd_create") as mock_cmd:
            main()
        mock_cmd.assert_called_once()
        args = mock_cmd.call_args[0][0]
        assert args.name == "my-proj"
        assert args.machine == "local"
        assert args.template == "mytmpl"

    def test_list_dispatches(self):
        from colette_cli.main import main
        with patch.object(sys, "argv", ["colette", "list"]), \
             patch("colette_cli.main.cmd_list") as mock_cmd:
            main()
        mock_cmd.assert_called_once()

    def test_link_dispatches_with_path(self):
        from colette_cli.main import main
        with patch.object(sys, "argv", ["colette", "link", "/some/path"]), \
             patch("colette_cli.main.cmd_link") as mock_cmd:
            main()
        mock_cmd.assert_called_once()
        assert mock_cmd.call_args[0][0].path == "/some/path"

    def test_debug_dispatches(self):
        from colette_cli.main import main
        with patch.object(sys, "argv", ["colette", "debug", "self-report"]), \
             patch("colette_cli.main.cmd_debug") as mock_cmd:
            main()
        mock_cmd.assert_called_once()
        assert mock_cmd.call_args[0][0].debug_cmd == "self-report"
