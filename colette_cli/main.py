"""Main entrypoint for the Colette CLI."""

import sys
from colette_cli.cli import build_parser
from colette_cli.config import cmd_config
from colette_cli.project import (
    cmd_create,
    cmd_delete,
    cmd_list,
    cmd_attach,
    cmd_code,
    cmd_copilot,
    cmd_link,
    cmd_unlink,
)
from colette_cli.session import cmd_start, cmd_stop, cmd_monitor, cmd_logs, cmd_update
from colette_cli.debug import cmd_debug
from colette_cli.tui import cmd_tui
from colette_cli.utils.helpers import detect_project_from_cwd

# Commands that accept a single optional project name and fall back to cwd detection
_CWD_DETECT_COMMANDS = {"attach", "code", "copilot", "delete", "unlink"}


def main():
    """Main CLI dispatcher."""
    parser, subparsers = build_parser()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # Auto-detect project from cwd when name was omitted
    if args.command in _CWD_DETECT_COMMANDS and getattr(args, "name", None) is None:
        detected = detect_project_from_cwd()
        if detected:
            args.name = detected
        else:
            subparsers[args.command].print_help()
            sys.exit(0)

    handlers = {
        "config": cmd_config,
        "create": cmd_create,
        "delete": cmd_delete,
        "list": cmd_list,
        "link": cmd_link,
        "unlink": cmd_unlink,
        "attach": cmd_attach,
        "code": cmd_code,
        "copilot": cmd_copilot,
        "monitor": cmd_monitor,
        "start": cmd_start,
        "stop": cmd_stop,
        "update": cmd_update,
        "logs": cmd_logs,
        "debug": cmd_debug,
        "tui": cmd_tui,
    }

    handler = handlers.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
