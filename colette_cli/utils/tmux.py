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
        ["tmux", "has-session", "-t", name],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
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
            stdin=subprocess.DEVNULL,
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
        result = ssh_run(
            machine,
            f"tmux new-session -d -s {shlex.quote(name)} -c {shlex.quote(path)} bash -lc {shlex.quote(startup_command)}",
        )
        if result.returncode != 0:
            from .formatting import warn
            details = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            warn(f"failed to create remote tmux session for '{name}': {details}")
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
        stdin=subprocess.DEVNULL,
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
        subprocess.run(["tmux", "kill-window", "-t", session_name], capture_output=True, stdin=subprocess.DEVNULL)
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name], capture_output=True, stdin=subprocess.DEVNULL
        )

    if inside_tmux:
        # Create a new window and capture its unique window ID for precise targeting
        r = subprocess.run(
            ["tmux", "new-window", "-P", "-F", "#{window_id}", "-n", session_name, first_cmd],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
        )
        target = r.stdout.strip()  # e.g. "@5" — unique across all sessions
    else:
        # Create a detached session and capture the window ID
        r = subprocess.run(
            [
                "tmux", "new-session", "-d", "-P", "-F", "#{window_id}",
                "-s", session_name, "-n", session_name, first_cmd,
            ],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
        )
        target = r.stdout.strip()

    # Split panes for remaining projects.
    # Apply tiled layout after EACH split so that no pane ever becomes too
    # small to split (tmux refuses splits below the minimum pane size).
    for _project, cmd in active_commands[1:]:
        subprocess.run(
            ["tmux", "split-window", "-t", target, cmd],
            capture_output=True,
            stdin=subprocess.DEVNULL,
        )
        subprocess.run(
            ["tmux", "select-layout", "-t", target, "tiled"],
            capture_output=True,
            stdin=subprocess.DEVNULL,
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


def create_tmux_window_with_rows(session_name, project_rows, replace_existing=False):
    """Create a tmux session/window with one horizontal row per project.

    Args:
        session_name: Name of the tmux session to create.
        project_rows: list of (project_dict, [(label, command), ...]).
            Each project occupies one horizontal band; sessions within a
            project are split side-by-side inside that band.
        replace_existing: Kill any existing session/window with this name.

    Layout strategy:
        - First project's first session → initial pane (full screen).
        - Additional sessions of the same project → ``split-window -h``
          (horizontal, within the same row).
        - First session of each subsequent project → ``split-window -v -f``
          (full-width vertical split, adds a new row below all existing rows).
        - Additional sessions of that project → ``split-window -h -t <row_anchor>``.
    """
    # Flatten to check total pane count
    all_cmds = [(proj, cmd) for proj, sessions in project_rows for _lbl, cmd in sessions]
    if not all_cmds:
        return

    # If every project has exactly 1 session, fall back to the simple tiled layout
    if all(len(sessions) == 1 for _proj, sessions in project_rows):
        _create_tmux_window_with_panes(session_name, all_cmds, replace_existing)
        return

    inside_tmux = bool(os.environ.get("TMUX"))
    total_panes = len(all_cmds)

    if replace_existing:
        subprocess.run(["tmux", "kill-window", "-t", session_name], capture_output=True, stdin=subprocess.DEVNULL)
        subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True, stdin=subprocess.DEVNULL)

    first_proj, first_sessions = project_rows[0]
    _first_lbl, first_cmd = first_sessions[0]

    if inside_tmux:
        r = subprocess.run(
            ["tmux", "new-window", "-P", "-F", "#{pane_id}", "-n", session_name, first_cmd],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
        )
        window_target = f"={session_name}"
    else:
        r = subprocess.run(
            [
                "tmux", "new-session", "-d", "-P", "-F", "#{pane_id}",
                "-s", session_name, "-n", session_name, first_cmd,
            ],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
        )
        window_target = session_name

    row_anchor = r.stdout.strip()  # pane_id of the first pane, e.g. "%3"

    # Add remaining sessions of project[0] in the same row (horizontal splits)
    for _lbl, cmd in first_sessions[1:]:
        r = subprocess.run(
            ["tmux", "split-window", "-h", "-t", row_anchor, cmd],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
        )

    # For each subsequent project, add a new full-width row then its sessions
    for proj, sessions in project_rows[1:]:
        _lbl, cmd = sessions[0]
        # -f = full-width split (spans the entire window edge, not just the target pane)
        r = subprocess.run(
            ["tmux", "split-window", "-v", "-f", "-t", window_target, cmd],
            capture_output=True, text=True, stdin=subprocess.DEVNULL,
        )
        row_anchor = r.stdout.strip() if r.stdout.strip() else row_anchor

        for _lbl2, cmd2 in sessions[1:]:
            subprocess.run(
                ["tmux", "split-window", "-h", "-t", row_anchor, cmd2],
                capture_output=True, stdin=subprocess.DEVNULL,
            )

    if inside_tmux:
        info(f"Window '{session_name}' opened with {total_panes} pane(s).")
    else:
        info(
            f"Session '{session_name}' created with {total_panes} pane(s). Attaching…"
        )
        subprocess.run(["tmux", "attach-session", "-t", session_name])


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
