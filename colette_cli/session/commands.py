"""Session sub-commands: start, stop, monitor, logs."""

import os
import shlex
import subprocess
from pathlib import Path

from colette_cli.project import require_project
from colette_cli.template import (
    build_hook_command,
    build_project_bootstrap,
    get_project_template_name,
    get_template_metadata,
    run_template_hook,
)
from colette_cli.utils.config import (
    get_machine,
    load_config,
    load_projects,
)
from colette_cli.utils.formatting import bold, cyan, dim, err, info
from colette_cli.utils.helpers import build_projects_by_machine, filter_projects_by_name, is_remote_machine
from colette_cli.utils.ssh import ssh_interactive, ssh_run, ssh_flags_str, sync_remote_colette
from colette_cli.utils.tmux import (
    create_tmux_window_with_panes,
    create_tmux_window_with_rows,
    ensure_session,
    get_sessions,
    local_tmux_session,
)


def cmd_start(args):
    """Start tmux sessions for projects."""
    projects = load_projects()
    cfg = load_config()

    if not projects:
        print("No projects. Create one with: colette create <name>")
        return

    filter_machine = getattr(args, "machine", None)
    filter_names = getattr(args, "projects", None) or []
    by_machine = build_projects_by_machine(projects, filter_machine)

    if not by_machine:
        err(f"no projects found for machine '{filter_machine}'.")

    for machine_name, machine_projects in sorted(by_machine.items()):
        machine_projects = filter_projects_by_name(machine_projects, filter_names)
        if not machine_projects:
            continue
        machine = get_machine(cfg, machine_name) or {}
        is_remote = is_remote_machine(machine)

        if is_remote:
            sync_remote_colette(machine, machine_name)

        print(f"\n{bold(f'[{machine_name}]')}")

        for project in sorted(machine_projects, key=lambda x: x["name"]):
            template_metadata = get_template_metadata(
                machine, machine_name, get_project_template_name(project)
            )
            created = ensure_session(
                project,
                machine,
                is_remote,
                build_project_bootstrap(project, machine_name, template_metadata, is_remote),
            )
            run_template_hook(
                project,
                machine,
                machine_name,
                is_remote,
                template_metadata,
                "onstart",
                fail_on_error=False,
            )
            if created:
                info(f"Started session for '{project['name']}'")
            else:
                print(f"  {cyan(project['name'])}  {dim('- session already running')}")

    print()


def cmd_stop(args):
    """Stop tmux sessions for projects (optional filter)."""
    projects = load_projects()
    if not projects:
        print("No projects. Create one with: colette create <name>")
        return

    filter_machine = getattr(args, "machine", None)
    filter_names = getattr(args, "projects", None) or []
    by_machine = build_projects_by_machine(projects, filter_machine)

    if not by_machine:
        err("no projects found.")

    cfg = load_config()
    for machine_name, machine_projects in sorted(by_machine.items()):
        machine_projects = filter_projects_by_name(machine_projects, filter_names)
        if not machine_projects:
            continue
        machine = get_machine(cfg, machine_name)
        is_remote = is_remote_machine(machine)

        print(f"\n{bold(f'[{machine_name}]')}")

        for project in sorted(machine_projects, key=lambda x: x["name"]):
            name = project["name"]
            template_metadata = get_template_metadata(
                machine, machine_name, get_project_template_name(project)
            )
            run_template_hook(
                project,
                machine,
                machine_name,
                is_remote,
                template_metadata,
                "onstop",
                fail_on_error=False,
            )
            if is_remote:
                for session in [name, f"{name}-copilot", f"{name}-logs"]:
                    ssh_run(machine, f"tmux kill-session -t {shlex.quote(session)} 2>/dev/null")
            else:
                for session in [name, f"{name}-copilot", f"{name}-logs"]:
                    subprocess.run(
                        ["tmux", "kill-session", "-t", session],
                        capture_output=True,
                        stdin=subprocess.DEVNULL,
                    )
            info(f"Stopped session for '{name}'")

    print()


def cmd_update(args):
    """Run the onupdate hook for one or more projects."""
    projects = load_projects()
    if not projects:
        print("No projects. Create one with: colette create <name>")
        return

    filter_machine = getattr(args, "machine", None)
    filter_names = getattr(args, "projects", None) or []
    by_machine = build_projects_by_machine(projects, filter_machine)

    if not by_machine:
        err(f"no projects found for machine '{filter_machine}'.")

    cfg = load_config()
    for machine_name, machine_projects in sorted(by_machine.items()):
        machine_projects = filter_projects_by_name(machine_projects, filter_names)
        if not machine_projects:
            continue
        machine = get_machine(cfg, machine_name)
        is_remote = is_remote_machine(machine)
        if is_remote:
            sync_remote_colette(machine, machine_name)

        print(f"\n{bold(f'[{machine_name}]')}")

        for project in sorted(machine_projects, key=lambda x: x["name"]):
            template_metadata = get_template_metadata(
                machine, machine_name, get_project_template_name(project)
            )
            run_template_hook(
                project,
                machine,
                machine_name,
                is_remote,
                template_metadata,
                "onupdate",
                fail_on_error=False,
            )
            info(f"Updated '{project['name']}'")

    print()


def _get_current_tmux_session():
    """Return the current tmux session name, or None if not inside tmux."""
    if not os.environ.get("TMUX"):
        return None
    result = subprocess.run(
        ["tmux", "display-message", "-p", "#S"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


def cmd_monitor(args):
    """Open a tmux window with read-only panes for active project sessions."""
    current_session = _get_current_tmux_session()
    if current_session is not None:
        if current_session == "colette-monitor":
            err("cannot run monitor from within the colette-monitor session.")
        project_names = {p["name"] for p in load_projects()}
        if current_session in project_names:
            err(
                f"cannot run monitor from within a colette session "
                f"(current session: '{current_session}')."
            )

    projects = load_projects()
    cfg = load_config()

    filter_machine = getattr(args, "machine", None)
    filter_projects = getattr(args, "projects", None) or []
    mode_copilot = getattr(args, "copilot", False)
    mode_all = getattr(args, "all", False)

    by_machine = build_projects_by_machine(projects, filter_machine)

    if not by_machine:
        if filter_machine:
            err(
                f"no projects found for machine '{filter_machine}'. "
                "Run 'colette list' to see available projects."
            )
        else:
            err("no projects found. Create one with: colette create <name>")

    def monitor_attach_wrapper(command):
        return f'bash -lc "until env -u TMUX {command}; do sleep 0.2; done"'

    if mode_all:
        _cmd_monitor_all(by_machine, cfg, filter_projects, monitor_attach_wrapper)
    elif mode_copilot:
        _cmd_monitor_copilot(by_machine, cfg, filter_projects, monitor_attach_wrapper)
    else:
        _cmd_monitor_standard(by_machine, cfg, filter_projects, monitor_attach_wrapper)


def _collect_monitor_panes(by_machine, cfg, filter_projects, wrap, session_name_fn):
    """Build (project, wrapped_command) pairs for monitor panes.

    session_name_fn(project) → session name string.
    Returns the list of (project, command) pairs with active sessions.
    """
    active = []
    for machine_name, machine_projects in sorted(by_machine.items()):
        machine_projects = filter_projects_by_name(machine_projects, filter_projects)
        if not machine_projects:
            continue
        machine = get_machine(cfg, machine_name)
        is_remote = is_remote_machine(machine)
        sessions = get_sessions(machine, is_remote)
        for project in sorted(machine_projects, key=lambda x: x["name"]):
            session = session_name_fn(project)
            if session not in sessions:
                continue
            if is_remote:
                flags = ssh_flags_str(machine)
                host = machine.get("host", "")
                command = f"ssh -t {flags}{host} tmux set-option -g mouse on \\; tmux attach-session -t {shlex.quote(session)}"
            else:
                command = f"tmux attach-session -t {shlex.quote(session)}"
            active.append((project, wrap(command)))
    return active


def _cmd_monitor_standard(by_machine, cfg, filter_projects, wrap):
    """Monitor mode: standard <project> sessions."""
    active = _collect_monitor_panes(
        by_machine, cfg, filter_projects, wrap, lambda p: p["name"]
    )
    if not active:
        err("no active sessions to monitor.")
    create_tmux_window_with_panes("colette-monitor", active, replace_existing=True)


def _cmd_monitor_copilot(by_machine, cfg, filter_projects, wrap):
    """Monitor mode: <project>-copilot sessions."""
    active = _collect_monitor_panes(
        by_machine, cfg, filter_projects, wrap, lambda p: f"{p['name']}-copilot"
    )
    if not active:
        err("no active copilot sessions to monitor.")
    create_tmux_window_with_panes("colette-monitor", active, replace_existing=True)


def _cmd_monitor_all(by_machine, cfg, filter_projects, wrap):
    """Monitor mode: all active sessions per project, one row per project."""
    project_rows = []
    for machine_name, machine_projects in sorted(by_machine.items()):
        machine_projects = filter_projects_by_name(machine_projects, filter_projects)
        if not machine_projects:
            continue
        machine = get_machine(cfg, machine_name)
        is_remote = is_remote_machine(machine)
        all_sessions = get_sessions(machine, is_remote)

        def _ssh_cmd(session_name):
            flags = ssh_flags_str(machine)
            host = machine.get("host", "")
            return f"ssh -t {flags}{host} tmux set-option -g mouse on \\; tmux attach-session -t {shlex.quote(session_name)}"

        for project in sorted(machine_projects, key=lambda x: x["name"]):
            pname = project["name"]
            row_sessions = []

            for label, session_name in [
                ("standard", pname),
                ("copilot", f"{pname}-copilot"),
                ("logs", f"{pname}-logs"),
            ]:
                if session_name not in all_sessions:
                    continue
                cmd = _ssh_cmd(session_name) if is_remote else f"tmux attach-session -t {shlex.quote(session_name)}"
                row_sessions.append((label, wrap(cmd)))

            if row_sessions:
                project_rows.append((project, row_sessions))

    if not project_rows:
        err("no active sessions to monitor.")

    create_tmux_window_with_rows("colette-monitor", project_rows, replace_existing=True)


def cmd_logs(args):
    """Run the onlogs hook for one or many projects."""
    name = getattr(args, "name", None)
    cfg = load_config()

    if name:
        project = require_project(name)
        machine_name = project["machine"]
        machine = get_machine(cfg, machine_name)
        is_remote = is_remote_machine(machine)
        template_name = get_project_template_name(project)
        template_metadata = get_template_metadata(machine, machine_name, template_name)

        logs_cmd = build_hook_command(
            project, machine_name, template_metadata, machine, "onlogs"
        )
        if logs_cmd is None:
            if template_name:
                hook_path = f"~/.config/colette/templates/{template_name}/.onlogs"
            else:
                hook_path = f"~/.config/colette/projects/{name}/.onlogs"
            err(
                f"no 'onlogs' hook defined for project '{name}'. "
                f"Edit {hook_path} to enable logs."
            )

        session_name = f"{name}-logs"
        if is_remote:
            tmux_cmd = (
                f"tmux set-option -g mouse on \\; new-session -A -s {shlex.quote(session_name)} "
                f"-c {shlex.quote(project['path'])} bash -lc {shlex.quote(logs_cmd)}"
            )
            ssh_interactive(machine, tmux_cmd)
        else:
            project_path = str(Path(project["path"]).expanduser())
            local_tmux_session(session_name, project_path, logs_cmd)
    else:
        projects = load_projects()
        if not projects:
            print("No projects. Create one with: colette create <name>")
            return

        filter_machine = getattr(args, "machine", None)
        by_machine = build_projects_by_machine(projects, filter_machine)

        if not by_machine:
            if filter_machine:
                err(
                    f"no projects found for machine '{filter_machine}'. "
                    "Run 'colette list' to see available projects."
                )
            else:
                err("no projects found. Create one with: colette create <name>")

        active = []
        for machine_name, machine_projects in sorted(by_machine.items()):
            machine = get_machine(cfg, machine_name)
            is_remote = is_remote_machine(machine)
            for project in sorted(machine_projects, key=lambda x: x["name"]):
                template_name = get_project_template_name(project)
                template_metadata = get_template_metadata(machine, machine_name, template_name)
                cmd = build_hook_command(
                    project, machine_name, template_metadata, machine, "onlogs"
                )
                if cmd is None:
                    continue
                if is_remote:
                    flags = ssh_flags_str(machine)
                    host = machine.get("host", "")
                    active.append(
                        (project, f"ssh -t {flags}{host} {shlex.quote(cmd)}")
                    )
                else:
                    active.append((project, cmd))

        if not active:
            err(
                "no projects with an 'onlogs' hook found. Add a .onlogs hook to enable logs."
            )

        create_tmux_window_with_panes("colette-logs", active)

