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
    load_templates,
)
from colette_cli.utils.formatting import bold, cyan, dim, err, info
from colette_cli.utils.helpers import build_projects_by_machine, filter_projects_by_name
from colette_cli.utils.ssh import ssh_interactive, ssh_run
from colette_cli.utils.tmux import (
    create_tmux_window_with_panes,
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
        machine = cfg.get("machines", {}).get(machine_name, {})
        is_remote = machine.get("type") == "ssh"
        templates_cfg = load_templates()

        print(f"\n{bold(f'[{machine_name}]')}")

        for project in sorted(machine_projects, key=lambda x: x["name"]):
            template_metadata = get_template_metadata(
                templates_cfg, get_project_template_name(project)
            )
            created = ensure_session(
                project,
                machine,
                is_remote,
                build_project_bootstrap(project, machine_name, template_metadata),
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

    for machine_name, machine_projects in sorted(by_machine.items()):
        machine_projects = filter_projects_by_name(machine_projects, filter_names)
        if not machine_projects:
            continue
        machine = get_machine(load_config(), machine_name)
        is_remote = machine and machine.get("type") == "ssh"
        templates_cfg = load_templates()

        print(f"\n{bold(f'[{machine_name}]')}")

        for project in sorted(machine_projects, key=lambda x: x["name"]):
            name = project["name"]
            template_metadata = get_template_metadata(
                templates_cfg, get_project_template_name(project)
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
                ssh_run(machine, f"tmux kill-session -t {name} 2>/dev/null")
            else:
                subprocess.run(
                    ["tmux", "kill-session", "-t", name], capture_output=True
                )
            info(f"Stopped session for '{name}'")

    print()


def cmd_monitor(args):
    """Open a tmux window with read-only panes for all project sessions."""
    projects = load_projects()
    cfg = load_config()
    templates_cfg = load_templates()

    filter_machine = getattr(args, "machine", None)
    filter_projects = getattr(args, "projects", None) or []

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

    def monitor_attach_wrapper(command):
        return f'bash -lc "until env -u TMUX {command}; do sleep 0.2; done"'

    for machine_name, machine_projects in sorted(by_machine.items()):
        machine_projects = filter_projects_by_name(machine_projects, filter_projects)
        if not machine_projects:
            continue
        machine = cfg.get("machines", {}).get(machine_name)
        is_remote = machine and machine.get("type") == "ssh"

        if is_remote:
            remote_sessions = get_sessions(machine, is_remote)
            for project in sorted(machine_projects, key=lambda x: x["name"]):
                if project["name"] not in remote_sessions:
                    template_metadata = get_template_metadata(
                        templates_cfg, get_project_template_name(project)
                    )
                    ssh_run(
                        machine,
                        "tmux new-session -d "
                        f"-s {shlex.quote(project['name'])} "
                        f"-c {shlex.quote(project['path'])} "
                        f"bash -lc {shlex.quote(build_project_bootstrap(project, machine_name, template_metadata))}",
                    )
                    info(f"Started new session for '{project['name']}'")
                key_flag = f"-i {machine['ssh_key']} " if "ssh_key" in machine else ""
                host = machine.get("host", "")
                command = f"ssh -t {key_flag}{host} tmux attach-session -t {project['name']} -r"
                active.append((project, monitor_attach_wrapper(command)))
        else:
            local_sessions = get_sessions(machine, is_remote)
            for project in sorted(machine_projects, key=lambda x: x["name"]):
                if project["name"] not in local_sessions:
                    local_path = str(Path(project["path"]).expanduser())
                    template_metadata = get_template_metadata(
                        templates_cfg, get_project_template_name(project)
                    )
                    subprocess.run(
                        [
                            "tmux",
                            "new-session",
                            "-d",
                            "-s",
                            project["name"],
                            "-c",
                            local_path,
                            "bash",
                            "-lc",
                            build_project_bootstrap(
                                project, machine_name, template_metadata
                            ),
                        ],
                        capture_output=True,
                    )
                    info(f"Started new session for '{project['name']}'")
                active.append(
                    (
                        project,
                        monitor_attach_wrapper(
                            f"tmux attach-session -t {project['name']} -r"
                        ),
                    )
                )

    if not active:
        err("no projects to monitor.")

    create_tmux_window_with_panes("colette-monitor", active, replace_existing=True)


def cmd_logs(args):
    """Run the onlogs hook for one or many projects."""
    name = getattr(args, "name", None)
    cfg = load_config()
    templates_cfg = load_templates()

    if name:
        project = require_project(name)
        machine_name = project["machine"]
        machine = cfg.get("machines", {}).get(machine_name)
        is_remote = machine and machine.get("type") == "ssh"
        template_name = get_project_template_name(project)
        template_metadata = get_template_metadata(templates_cfg, template_name)

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
                f"tmux new-session -A -s {shlex.quote(session_name)} "
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
            machine = cfg.get("machines", {}).get(machine_name)
            is_remote = machine and machine.get("type") == "ssh"
            for project in sorted(machine_projects, key=lambda x: x["name"]):
                template_name = get_project_template_name(project)
                template_metadata = get_template_metadata(templates_cfg, template_name)
                cmd = build_hook_command(
                    project, machine_name, template_metadata, machine, "onlogs"
                )
                if cmd is None:
                    continue
                if is_remote:
                    key_flag = (
                        f"-i {machine['ssh_key']} " if "ssh_key" in machine else ""
                    )
                    host = machine.get("host", "")
                    active.append(
                        (project, f"ssh -t {key_flag}{host} {shlex.quote(cmd)}")
                    )
                else:
                    active.append((project, cmd))

        if not active:
            err(
                "no projects with an 'onlogs' hook found. Add a .onlogs hook to enable logs."
            )

        create_tmux_window_with_panes("colette-logs", active)


def cmd_session(args):
    """Dispatcher for session sub-commands."""
    if args.session_cmd == "start":
        cmd_start(args)
    elif args.session_cmd == "stop":
        cmd_stop(args)
    elif args.session_cmd == "monitor":
        cmd_monitor(args)
    elif args.session_cmd == "logs":
        cmd_logs(args)
