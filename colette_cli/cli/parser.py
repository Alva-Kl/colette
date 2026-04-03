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
        description=BANNER,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  colette config add-machine\n"
            "  colette create my-project -m local -t my-template\n"
            "  colette start -m local my-project\n"
            "  colette monitor my-project\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", metavar="<subcommand>")

    cp = sub.add_parser(
        "config",
        help="Manage machines, templates, and hook scripts",
        description="Manage machines, templates, and hook scripts.",
    )
    csub = cp.add_subparsers(dest="config_cmd", metavar="<action>")
    cp.set_defaults(config_parser=cp)
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
        choices=["oncreate", "onstart", "onstop", "onlogs", "onupdate", "coletterc"],
        help="Hook to edit",
    )
    ephp = csub.add_parser(
        "edit-project-hook", help="Edit a project-specific hook script with nano"
    )
    ephp.add_argument("project_name", help="Project name")
    ephp.add_argument(
        "hook_name",
        choices=["oncreate", "onstart", "onstop", "onlogs", "onupdate", "coletterc"],
        help="Hook to edit",
    )
    rtup = csub.add_parser(
        "run-template-update",
        help="Run the onupdate hook directly for a template",
        description=(
            "Runs the 'onupdate' hook defined for a template without a project context.\n"
            "Use this to update the template itself (e.g. pull latest changes).\n\n"
            "The hook file is at:\n"
            "  ~/.config/colette/templates/<template>/.onupdate"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    rtup.add_argument("template_name", help="Template name")
    rtup.add_argument(
        "--machine",
        "-m",
        metavar="MACHINE",
        help="Machine to run the hook on (default: configured default machine)",
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
    dp.add_argument("name", nargs="?", default=None, help="Project name (default: detected from current directory)")

    ulp = sub.add_parser(
        "unlink", help="Remove a project from colette without deleting its files"
    )
    ulp.add_argument("name", nargs="?", default=None, help="Project name (default: detected from current directory)")

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
    atp.add_argument("name", nargs="?", default=None, help="Project name (default: detected from current directory)")

    cop = sub.add_parser("code", help="Open project in VS Code (local or SSH)")
    cop.add_argument("name", nargs="?", default=None, help="Project name (default: detected from current directory)")

    copp = sub.add_parser(
        "copilot",
        help="Open project in GitHub Copilot in a dedicated tmux session",
    )
    copp.add_argument("name", nargs="?", default=None, help="Project name (default: detected from current directory)")

    monp = sub.add_parser(
        "monitor",
        help="Monitor project sessions in tmux panes",
        description=(
            "Opens a tmux window with panes attached to active project sessions.\n\n"
            "When run from a registered project directory without arguments, only\n"
            "that project is monitored. Otherwise all active sessions are shown."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    monp.add_argument(
        "--machine",
        "-m",
        metavar="MACHINE",
        help="Only show sessions from one machine",
    )
    monp.add_argument("projects", nargs="*", help="Optional project names")
    mon_mode = monp.add_mutually_exclusive_group()
    mon_mode.add_argument(
        "--copilot",
        action="store_true",
        default=False,
        help="Monitor active Copilot sessions (<project>-copilot) instead of standard sessions",
    )
    mon_mode.add_argument(
        "--all",
        action="store_true",
        default=False,
        help=(
            "Monitor all active sessions (standard, copilot, logs) "
            "with one row per project"
        ),
    )

    stp = sub.add_parser(
        "start",
        help="Start tmux sessions for projects",
        description=(
            "Starts tmux sessions for one or more projects.\n\n"
            "When run from a registered project directory without arguments, only\n"
            "that project is started. Otherwise all projects are started."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    stp.add_argument(
        "--machine",
        "-m",
        metavar="MACHINE",
        help="Only start sessions for one machine",
    )
    stp.add_argument("projects", nargs="*", help="Optional project names")

    stpp = sub.add_parser(
        "stop",
        help="Stop tmux sessions for projects",
        description=(
            "Stops tmux sessions for one or more projects.\n\n"
            "When run from a registered project directory without arguments, only\n"
            "that project is stopped. Otherwise all projects are stopped."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    stpp.add_argument(
        "--machine",
        "-m",
        metavar="MACHINE",
        help="Only stop sessions for one machine",
    )
    stpp.add_argument("projects", nargs="*", help="Optional project names")

    updp = sub.add_parser(
        "update",
        help="Run the 'onupdate' hook for one or many projects",
        description=(
            "Runs the 'onupdate' hook defined for each project's template.\n\n"
            "When run from a registered project directory without arguments, only\n"
            "that project is updated. Otherwise all projects are updated.\n\n"
            "To enable updates for a template, edit:\n"
            "  ~/.config/colette/templates/<template>/.onupdate\n\n"
            "To run onupdate directly on a template (without a project), use:\n"
            "  colette config run-template-update <template>"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    updp.add_argument(
        "--machine",
        "-m",
        metavar="MACHINE",
        help="Only update projects on one machine",
    )
    updp.add_argument("projects", nargs="*", help="Optional project names")

    logsp = sub.add_parser(
        "logs",
        help="Run the 'onlogs' hook for one or many projects",
        description=(
            "Runs the 'onlogs' hook defined for each project's template.\n"
            "For a single project, opens an interactive tmux session.\n"
            "Without a project name, opens a multi-pane tmux window for all projects\n"
            "that have an 'onlogs' hook.\n\n"
            "When run from a registered project directory without a name argument,\n"
            "the current project is used automatically.\n\n"
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

    sub.add_parser("tui", help="Interactive TUI (arrow-key navigation)")

    dbgp = sub.add_parser(
        "debug",
        help="Debug utilities",
        description="Debug utilities for inspecting Colette internals.",
    )
    dbgsub = dbgp.add_subparsers(dest="debug_cmd", metavar="<action>")
    dbgp.set_defaults(debug_parser=dbgp)
    hlp = dbgsub.add_parser(
        "hook-log",
        help="Show hook script failure log",
        description=(
            "Shows the log of hook scripts that exited with a non-zero status.\n"
            "Entries are stored in ~/.config/colette/hook-failures.json (last 200 kept)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    hlp.add_argument(
        "--project",
        "-p",
        metavar="NAME",
        help="Filter entries to a specific project",
    )
    hlp.add_argument(
        "--clear",
        action="store_true",
        help="Clear the hook failure log",
    )

    return parser, sub.choices
