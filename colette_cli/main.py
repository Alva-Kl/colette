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
    cmd_link,
    cmd_unlink,
)
from colette_cli.session import cmd_start, cmd_stop, cmd_monitor, cmd_logs
from colette_cli.tui import cmd_tui


def main():
    """Main CLI dispatcher."""
    parser = build_parser()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    handlers = {
        "config": cmd_config,
        "create": cmd_create,
        "delete": cmd_delete,
        "list": cmd_list,
        "link": cmd_link,
        "unlink": cmd_unlink,
        "attach": cmd_attach,
        "code": cmd_code,
        "monitor": cmd_monitor,
        "start": cmd_start,
        "stop": cmd_stop,
        "logs": cmd_logs,
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
