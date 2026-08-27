"""SSH utilities for connecting to remote machines."""

import json
import os
import shlex
import subprocess

# ConnectTimeout applies to every real SSH invocation (interactive or not) so
# an unreachable host fails in ~15s instead of the OS default (~130s on Linux).
_SSH_CONNECT_TIMEOUT_OPTS = ["-o", "ConnectTimeout=15"]

# BatchMode additionally applies only to non-interactive automated calls —
# fail immediately instead of hanging on a password prompt. Never applied to
# ssh_interactive, which may legitimately rely on password auth.
_SSH_BATCH_MODE_OPTS = ["-o", "BatchMode=yes"]


def _ssh_base_args(machine):
    """Build base SSH arguments from machine config."""
    args = ["ssh"] + _SSH_CONNECT_TIMEOUT_OPTS
    if "ssh_key" in machine:
        args += ["-i", machine["ssh_key"]]
    if "port" in machine:
        args += ["-p", str(machine["port"])]
    args.append(machine["host"])
    return args


def ssh_flags_str(machine):
    """Return SSH option flags (key, port) as a shell-safe string for inline commands.

    Produces something like ``-i /path/to/key -p 24 `` (trailing space) or ``""``
    so callers can embed it directly in an f-string before the hostname.
    """
    parts = []
    if "ssh_key" in machine:
        parts += ["-i", shlex.quote(machine["ssh_key"])]
    if "port" in machine:
        parts += ["-p", shlex.quote(str(machine["port"]))]
    return (" ".join(parts) + " ") if parts else ""


def ssh_run(machine, remote_cmd, extra_opts=None):
    """Run a non-interactive command on a remote machine; return CompletedProcess.

    *extra_opts* is an optional list of SSH option flags (e.g. ``["-o",
    "BatchMode=yes"]``) inserted between the connection flags and the hostname.
    Defaults to ``_SSH_BATCH_MODE_OPTS`` — every caller here is a non-interactive
    automated command, so hanging on a password prompt is never wanted.
    """
    base = _ssh_base_args(machine)
    if extra_opts is None:
        extra_opts = _SSH_BATCH_MODE_OPTS
    if extra_opts:
        args = base[:-1] + extra_opts + [base[-1], remote_cmd]
    else:
        args = base + [remote_cmd]
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def ssh_interactive(machine, remote_cmd):
    """Run a command on a remote machine with a TTY allocated.

    When called from inside a local tmux session, temporarily disables mouse
    mode for the current window so that scroll events pass through to the remote
    tmux session instead of being captured by the outer local tmux.  The
    window-level override is removed unconditionally when SSH exits, restoring
    the inherited (session / global) mouse setting.
    """
    inside_tmux = bool(os.environ.get("TMUX"))
    if inside_tmux:
        subprocess.run(
            ["tmux", "set-window-option", "mouse", "off"],
            capture_output=True,
            stdin=subprocess.DEVNULL,
        )
    try:
        base = _ssh_base_args(machine)
        # Insert -t right after "ssh" to force TTY allocation.
        cmd = [base[0], "-t"] + base[1:] + [remote_cmd]
        subprocess.run(cmd)
    finally:
        if inside_tmux:
            subprocess.run(
                ["tmux", "set-window-option", "-u", "mouse"],
                capture_output=True,
                stdin=subprocess.DEVNULL,
            )


_REMOTE_CONFIG_BASE = "$HOME/.config/colette"


def _ssh_write(machine, remote_path, content_bytes):
    """Write *content_bytes* to a path on a remote machine via SSH. Returns True on success."""
    base = _ssh_base_args(machine)
    args = base[:-1] + _SSH_BATCH_MODE_OPTS + [base[-1], f"cat > {remote_path}"]
    result = subprocess.run(
        args,
        input=content_bytes,
        capture_output=True,
    )
    return result.returncode == 0


def _ssh_mkdir(machine, remote_path):
    """mkdir -p a path on a remote machine via SSH. Returns True on success."""
    result = ssh_run(machine, f"mkdir -p {remote_path}")
    return result.returncode == 0


def _ssh_read_json(machine, remote_path, default):
    """Read and parse a JSON file from a remote machine. Returns *default* on
    a missing file, empty output, or parse failure."""
    result = ssh_run(machine, f"cat {remote_path} 2>/dev/null")
    if not (result.stdout or "").strip():
        return default
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return default


def _ssh_write_json(machine, remote_path, data):
    """Write *data* as JSON to a path on a remote machine via SSH. Returns True on success."""
    return _ssh_write(machine, remote_path, (json.dumps(data, indent=2) + "\n").encode())


def _remote_self_machine_name(machine):
    """Determine the machine name a remote uses for itself in its own config.json.

    Prefers the `type: "local"` entry matching the remote's own default_machine,
    else the first `type: "local"` entry, else None.
    """
    remote_cfg = _ssh_read_json(machine, f"{_REMOTE_CONFIG_BASE}/config.json", {})
    if not isinstance(remote_cfg, dict):
        return None
    machines = remote_cfg.get("machines", {})
    default_name = remote_cfg.get("default_machine")
    if default_name and machines.get(default_name, {}).get("type") == "local":
        return default_name
    return next((n for n, m in machines.items() if m.get("type") == "local"), None)


def push_project_entry(machine, machine_name, project):
    """Write *project* into a remote machine's own projects.json (merge by name).

    The pushed record's "machine" field is rewritten to the remote's own
    self-name (not the controller's connection name for it), so the record is
    meaningful when colette runs directly on the remote. Warns and returns
    False on any failure.
    """
    from colette_cli.utils.formatting import warn

    self_name = _remote_self_machine_name(machine)
    if not self_name:
        warn(f"'{machine_name}' has no local machine entry in its own config; cannot push project record.")
        return False

    record = dict(project)
    record["machine"] = self_name

    if not _ssh_mkdir(machine, _REMOTE_CONFIG_BASE):
        warn(f"failed to create remote config dir on '{machine_name}'")
        return False

    remote_projects = _ssh_read_json(machine, f"{_REMOTE_CONFIG_BASE}/projects.json", [])
    remote_projects = [p for p in remote_projects if p.get("name") != record["name"]]
    remote_projects.append(record)
    if not _ssh_write_json(machine, f"{_REMOTE_CONFIG_BASE}/projects.json", remote_projects):
        warn(f"failed to write projects.json on '{machine_name}'")
        return False
    return True


def remove_remote_project_entry(machine, machine_name, name):
    """Remove a project entry (by name) from a remote machine's own projects.json."""
    from colette_cli.utils.formatting import warn

    remote_projects = _ssh_read_json(machine, f"{_REMOTE_CONFIG_BASE}/projects.json", [])
    remote_projects = [p for p in remote_projects if p.get("name") != name]
    if not _ssh_write_json(machine, f"{_REMOTE_CONFIG_BASE}/projects.json", remote_projects):
        warn(f"failed to remove '{name}' from projects.json on '{machine_name}'")
        return False
    return True


def push_project_hooks(machine, machine_name, project_name):
    """Push a project's own hook-override files to a remote machine, verbatim.

    Unlike push_template_hooks, this does not flatten $SUPER chains — a
    project hook's `source "$SUPER"` is left intact and resolves dynamically
    at remote execution time against whatever's currently in that machine's
    templates/<template>/ directory (kept fresh by push_template_hooks).
    """
    from colette_cli.utils.config import PROJECT_HOOKS_DIR
    from colette_cli.utils.formatting import warn

    project_hooks_dir = PROJECT_HOOKS_DIR / project_name
    if not project_hooks_dir.exists():
        return True

    remote_project_dir = f"{_REMOTE_CONFIG_BASE}/projects/{project_name}"
    if not _ssh_mkdir(machine, remote_project_dir):
        warn(f"failed to create remote project hooks dir on '{machine_name}'")
        return False

    ok = True
    for hook_file in project_hooks_dir.iterdir():
        if hook_file.is_file():
            remote_path = f"{remote_project_dir}/{hook_file.name}"
            if not _ssh_write(machine, remote_path, hook_file.read_bytes()):
                warn(f"failed to push '{hook_file.name}' for project '{project_name}' to '{machine_name}'")
                ok = False
    return ok


def push_template_hooks(machine, machine_name, template_name):
    """Push the effective (flattened) hook scripts for a template to a remote machine.

    For each hook, the machine-scoped override is used if effective, else the
    shared template hook — with any `source "$SUPER"` chain between them
    inlined, so the remote ends up with one self-contained script per hook.
    """
    from colette_cli.template.executor import compute_effective_template_hook
    from colette_cli.utils.config import TEMPLATE_HOOK_FILENAMES
    from colette_cli.utils.formatting import warn

    remote_template_dir = f"{_REMOTE_CONFIG_BASE}/templates/{template_name}"
    if not _ssh_mkdir(machine, remote_template_dir):
        warn(f"failed to create remote template hooks dir on '{machine_name}'")
        return False

    ok = True
    for hook_name, filename in TEMPLATE_HOOK_FILENAMES.items():
        content = compute_effective_template_hook(template_name, hook_name, machine_name)
        if content is None:
            continue
        remote_path = f"{remote_template_dir}/{filename}"
        if not _ssh_write(machine, remote_path, content.encode()):
            warn(f"failed to push hook '{hook_name}' for template '{template_name}' to '{machine_name}'")
            ok = False
    return ok


def ssh_read_hook_files(machine, project_name, template_name):
    """Fetch a remote project's hook-resolution inputs in one SSH round-trip.

    Returns {hook_name: {"project": content_or_None, "template": content_or_None}}
    for every hook name (including "coletterc"), reading from the remote's own
    projects/<project_name>/.<hook> and templates/<template_name>/.<hook>
    paths (kept current by push_project_hooks/push_template_hooks).
    """
    from colette_cli.utils.config import TEMPLATE_HOOK_FILENAMES

    keys = []
    paths = []
    for hook_name, filename in TEMPLATE_HOOK_FILENAMES.items():
        keys.append(("project", hook_name))
        paths.append(f"{_REMOTE_CONFIG_BASE}/projects/{project_name}/{filename}")
        if template_name:
            keys.append(("template", hook_name))
            paths.append(f"{_REMOTE_CONFIG_BASE}/templates/{template_name}/{filename}")

    marker_tpl = "__COLETTE_HOOK_%d__"
    segments = [
        f'printf "{marker_tpl % i}\\n"; cat {shlex.quote(path)} 2>/dev/null'
        for i, path in enumerate(paths)
    ]
    result = ssh_run(machine, " ; ".join(segments))
    output = result.stdout or ""

    contents = {}
    for i, key in enumerate(keys):
        tag = marker_tpl % i
        start = output.find(tag)
        if start == -1:
            contents[key] = None
            continue
        start += len(tag) + 1
        end = output.find(marker_tpl % (i + 1), start) if (i + 1) < len(keys) else len(output)
        if end == -1:
            end = len(output)
        chunk = output[start:end]
        contents[key] = chunk if chunk else None

    resolved = {}
    for hook_name in TEMPLATE_HOOK_FILENAMES:
        resolved[hook_name] = {
            "project": contents.get(("project", hook_name)),
            "template": contents.get(("template", hook_name)) if template_name else None,
        }
    return resolved


def fetch_self_report(machine, machine_name):
    """Run `colette debug self-report` on a remote machine over SSH and parse its JSON output.

    Passes this connection's own configured `projects_dir` through so the
    remote can disambiguate when it hosts more than one logical `type:
    "local"` machine out of one shared config dir (e.g. separate prod/dev
    workspaces on one server, each with its own projects directory) — see
    `cmd_debug_self_report`'s docstring. Harmless when the remote has only
    one local machine, when this connection has no `projects_dir` set, or
    when it doesn't match any of the remote's local entries (the remote
    falls back to its default heuristic either way). *machine_name* is only
    used for warning/status messages, not sent to the remote.

    Returns the parsed dict, or None on any failure (no colette_path
    configured, SSH error, non-zero exit, or malformed JSON).
    """
    remote_path = machine.get("colette_path")
    if not remote_path:
        return None
    projects_dir = machine.get("projects_dir", "")
    result = ssh_run(
        machine,
        f"{shlex.quote(remote_path)} debug self-report {shlex.quote(projects_dir)}",
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
