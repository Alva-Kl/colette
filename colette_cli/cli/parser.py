"""CLI argument parsing and help text."""

import argparse

BANNER = r"""
   ██████╗ ██████╗ ██╗     ███████╗████████╗████████╗███████╗
  ██╔════╝██╔═══██╗██║     ██╔════╝╚══██╔══╝╚══██╔══╝██╔════╝
  ██║     ██║   ██║██║     █████╗     ██║      ██║   █████╗
  ██║     ██║   ██║██║     ██╔══╝     ██║      ██║   ██╔══╝
  ╚██████╗╚██████╔╝███████╗███████╗   ██║      ██║   ███████╗
   ╚═════╝ ╚═════╝ ╚══════╝╚══════╝   ╚═╝      ╚═╝   ╚══════╝
  Context Organizer for Local Environments and Task Tracking Engine
"""


def build_parser():
    """Build the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="colette",
        description=(
            BANNER
            + "\nSubcommands:\n"
            + "  config   Manage machines and templates\n"
            + "  create   Create a project from a template\n"
            + "  link     Link an existing directory as a project\n"
            + "  unlink   Remove a project from colette (files kept)\n"
            + "  delete   Delete a project\n"
            + "  list     List projects\n"
            + "  attach   Attach to project session\n"
            + "  code     Open project in VS Code\n"
            + "  start    Start project sessions\n"
            + "  stop     Stop project sessions\n"
            + "  monitor  Watch multiple sessions in tmux panes\n"
            + "  logs     Run onlogs hook for one or all projects\n\n"
            + "Run 'colette <subcommand> --help' for details."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  colette config --help\n"
            "  colette config add-machine\n"
            "  colette create my-project -m local -t my-template\n"
            "  colette start -m local my-project\n"
            "  colette monitor my-project\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", metavar="<subcommand>")

    cp = sub.add_parser(
        "config",
        help="Manage machine and template configuration",
        description=(
            "Configuration actions for machines, defaults, and templates.\n\n"
            "Actions:\n"
            "  list               List all configured machines\n"
            "  list-templates     List templates for a machine\n"
            "  add-machine        Interactively add a machine\n"
            "  edit-machine       Edit a machine\n"
            "  add-template       Add a template to a machine\n"
            "  edit-template      Edit a template on a machine\n"
            "  edit-hook          Edit a template hook script with nano\n"
            "  edit-project-hook  Edit a project-specific hook script with nano\n"
            "  remove-template    Remove a template from a machine\n"
            "  remove-machine     Remove a machine\n"
            "  set-default        Set the default machine\n\n"
            "Run 'colette config <action> --help' for action-specific usage."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    csub = cp.add_subparsers(dest="config_cmd", metavar="<action>")
    csub.add_parser("list", help="List all configured machines")
    ltp = csub.add_parser("list-templates", help="List templates for a machine")
    ltp.add_argument(
        "machine_name",
        nargs="?",
        help="Machine name (default: configured default machine)",
    )
    csub.add_parser("add-machine", help="Interactively add a machine")
    emp = csub.add_parser("edit-machine", help="Interactively edit a machine")
    emp.add_argument("machine_name", help="Machine name")
    atp = csub.add_parser("add-template", help="Add a template to a machine")
    atp.add_argument("machine_name", help="Machine name")
    atp.add_argument("template_name", help="Template name")
    atp.add_argument(
        "--param",
        action="append",
        metavar="KEY=VALUE",
        dest="params",
        help="Template parameter passed as COLETTE_PARAM_<KEY> to hooks (repeatable)",
    )
    etp = csub.add_parser("edit-template", help="Edit a template on a machine")
    etp.add_argument("machine_name", help="Machine name")
    etp.add_argument("template_name", help="Template name")
    etp.add_argument(
        "--param",
        action="append",
        metavar="KEY=VALUE",
        dest="params",
        help="Replace template parameters (repeatable; omit to keep existing params)",
    )
    ehp = csub.add_parser("edit-hook", help="Edit a template hook script with nano")
    ehp.add_argument("template_name", help="Template name")
    ehp.add_argument(
        "hook_name",
        choices=["oncreate", "onstart", "onstop", "onlogs", "coletterc"],
        help="Hook to edit",
    )
    ephp = csub.add_parser(
        "edit-project-hook", help="Edit a project-specific hook script with nano"
    )
    ephp.add_argument("project_name", help="Project name")
    ephp.add_argument(
        "hook_name",
        choices=["oncreate", "onstart", "onstop", "onlogs", "coletterc"],
        help="Hook to edit",
    )
    rtp = csub.add_parser("remove-template", help="Remove a template from a machine")
    rtp.add_argument("machine_name", help="Machine name")
    rtp.add_argument("template_name", help="Template name")
    rmp = csub.add_parser("remove-machine", help="Remove a machine from config")
    rmp.add_argument("machine_name", help="Machine name")
    sdp = csub.add_parser("set-default", help="Set the default machine")
    sdp.add_argument("machine_name", help="Machine name")

    crp = sub.add_parser("create", help="Create a new project from a template")
    crp.add_argument("name", help="Project name (lowercase letters, numbers, hyphens)")
    crp.add_argument(
        "--machine",
        "-m",
        metavar="MACHINE",
        help="Target machine (default: configured default machine)",
    )
    crp.add_argument(
        "--template",
        "-t",
        metavar="TEMPLATE",
        help="Template name (if omitted, you will be prompted)",
    )

    dp = sub.add_parser("delete", help="Delete a project and its files")
    dp.add_argument("name", help="Project name")

    ulp = sub.add_parser(
        "unlink", help="Remove a project from colette without deleting its files"
    )
    ulp.add_argument("name", help="Project name")

    sub.add_parser("list", help="List all projects grouped by machine")

    lnp = sub.add_parser(
        "link", help="Link an existing directory to colette as a project"
    )
    lnp.add_argument("path", help="Absolute path to the existing project directory")
    lnp.add_argument(
        "--machine",
        "-m",
        metavar="MACHINE",
        help="Target machine (default: configured default machine)",
    )
    lnp.add_argument(
        "--name",
        "-n",
        metavar="NAME",
        help="Project name (default: directory basename)",
    )

    atp = sub.add_parser("attach", help="Attach to or create project tmux session")
    atp.add_argument("name", help="Project name")

    cop = sub.add_parser("code", help="Open project in VS Code (local or SSH)")
    cop.add_argument("name", help="Project name")

    monp = sub.add_parser("monitor", help="Monitor project sessions in tmux panes")
    monp.add_argument(
        "--machine",
        "-m",
        metavar="MACHINE",
        help="Only show sessions from one machine",
    )
    monp.add_argument("projects", nargs="*", help="Optional project names")

    stp = sub.add_parser("start", help="Start tmux sessions for projects")
    stp.add_argument(
        "--machine",
        "-m",
        metavar="MACHINE",
        help="Only start sessions for one machine",
    )
    stp.add_argument("projects", nargs="*", help="Optional project names")

    stpp = sub.add_parser("stop", help="Stop tmux sessions for projects")
    stpp.add_argument(
        "--machine",
        "-m",
        metavar="MACHINE",
        help="Only stop sessions for one machine",
    )
    stpp.add_argument("projects", nargs="*", help="Optional project names")

    logsp = sub.add_parser(
        "logs",
        help="Run the 'onlogs' hook for one or many projects",
        description=(
            "Runs the 'onlogs' hook defined for each project's template.\n"
            "For a single project, opens an interactive tmux session.\n"
            "Without a project name, opens a multi-pane tmux window for all projects\n"
            "that have an 'onlogs' hook.\n\n"
            "To enable logs for a template, edit:\n"
            "  ~/.config/colette/templates/<template>/.onlogs"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    logsp.add_argument(
        "name",
        nargs="?",
        help="Project name (if omitted, show logs for all filtered projects)",
    )
    logsp.add_argument(
        "--machine",
        "-m",
        metavar="MACHINE",
        help="Only show logs from one machine",
    )

    return parser
