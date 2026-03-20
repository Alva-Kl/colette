"""Tmux session and window management utilities."""

import os
import shlex
import subprocess
from pathlib import Path
from .ssh import ssh_run
from .formatting import info


DEFAULT_BOOTSTRAP = "exec bash"


def _ensure_session_local(project, startup_command=None):
    """Ensure a tmux session exists for the project locally. Returns True if newly created."""
    name = project["name"]
    path = project["path"]
    startup_command = startup_command or DEFAULT_BOOTSTRAP
    r = subprocess.run(
        ["tmux", "has-session", "-t", name], capture_output=True, text=True
    )
    if r.returncode != 0:
        local_path = str(Path(path).expanduser())
        subprocess.run(
            [
                "tmux",
                "new-session",
                "-d",
                "-s",
                name,
                "-c",
                local_path,
                "bash",
                "-lc",
                startup_command,
            ],
            capture_output=True,
        )
        return True
    return False


def _ensure_session_remote(project, machine, startup_command=None):
    """Ensure a tmux session exists for the project on remote. Returns True if newly created."""
    name = project["name"]
    path = project["path"]
    startup_command = startup_command or DEFAULT_BOOTSTRAP
    r = ssh_run(
        machine, f"tmux has-session -t {name} 2>/dev/null && echo yes || echo no"
    )
    if r.stdout.strip() != "yes":
        ssh_run(
            machine,
            f"tmux new-session -d -s {shlex.quote(name)} -c {shlex.quote(path)} bash -lc {shlex.quote(startup_command)}",
        )
        return True
    return False


def ensure_session(project, machine, is_remote, startup_command=None):
    """Ensure a tmux session exists for the project. Returns True if newly created."""
    if is_remote:
        return _ensure_session_remote(project, machine, startup_command)
    else:
        return _ensure_session_local(project, startup_command)


def _get_sessions_local():
    """Get list of local tmux sessions."""
    r = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True,
        text=True,
    )
    return set(r.stdout.strip().splitlines()) if r.returncode == 0 else set()


def _get_sessions_remote(machine):
    """Get list of remote tmux sessions."""
    r = ssh_run(machine, "tmux list-sessions -F '#{session_name}' 2>/dev/null")
    return set(r.stdout.strip().splitlines()) if r.returncode == 0 else set()


def get_sessions(machine, is_remote):
    """Get list of tmux sessions (local or remote)."""
    if is_remote:
        return _get_sessions_remote(machine)
    else:
        return _get_sessions_local()


def _create_tmux_window_with_panes(
    session_name, active_commands, replace_existing=False
):
    """Create a tmux session/window with split panes for each command.

    Args:
        session_name: Name of the tmux session to create
        active_commands: List of (project_dict, command_string) tuples
    """
    _first_project, first_cmd = active_commands[0]
    inside_tmux = bool(os.environ.get("TMUX"))

    if replace_existing:
        subprocess.run(["tmux", "kill-window", "-t", session_name], capture_output=True)
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name], capture_output=True
        )

    if inside_tmux:
        # Create a new window in the current session
        subprocess.run(
            ["tmux", "new-window", "-n", session_name, first_cmd],
            capture_output=True,
        )
        target = session_name
    else:
        # Create a detached session; we'll attach at the end
        subprocess.run(
            [
                "tmux",
                "new-session",
                "-d",
                "-s",
                session_name,
                "-n",
                session_name,
                first_cmd,
            ],
            capture_output=True,
        )
        target = f"{session_name}:{session_name}"

    # Split panes for remaining projects
    for _project, cmd in active_commands[1:]:
        subprocess.run(
            ["tmux", "split-window", "-t", target, cmd],
            capture_output=True,
        )
        subprocess.run(
            ["tmux", "select-layout", "-t", target, "tiled"],
            capture_output=True,
        )

    subprocess.run(
        ["tmux", "select-layout", "-t", target, "tiled"],
        capture_output=True,
    )

    if inside_tmux:
        info(f"Window '{session_name}' opened with {len(active_commands)} pane(s).")
    else:
        info(
            f"Session '{session_name}' created with {len(active_commands)} pane(s). Attaching…"
        )
        subprocess.run(["tmux", "attach-session", "-t", session_name])


def create_tmux_window_with_panes(
    session_name, active_commands, replace_existing=False
):
    """Public interface for creating tmux window with panes."""
    _create_tmux_window_with_panes(session_name, active_commands, replace_existing)


def local_tmux_session(session_name, cwd, command):
    """Open or switch to a local tmux session running a command.

    If already inside tmux, switch to an existing session or create and switch.
    Otherwise open a new session interactively with -A (attach-or-create).
    """
    if os.environ.get("TMUX"):
        result = subprocess.run(
            ["tmux", "switch-client", "-t", session_name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            subprocess.run(
                [
                    "tmux", "new-session", "-d", "-s", session_name,
                    "-c", cwd, "bash", "-lc", command,
                ]
            )
            subprocess.run(["tmux", "switch-client", "-t", session_name])
    else:
        subprocess.run(
            [
                "tmux", "new-session", "-A", "-s", session_name,
                "-c", cwd, "bash", "-lc", command,
            ]
        )
