"""SSH utilities for connecting to remote machines."""

import json
import shlex
import subprocess
import threading
from pathlib import Path

from colette_cli import __version__ as _local_version
from colette_cli.utils.notify import send_notification

def _find_local_bin() -> Path:
    """Resolve the local colette binary path.

    When running as a zipapp (e.g. build/beta/colette), Python sets __file__
    to a virtual path inside the zip archive, so navigating parent.parent.parent
    lands on the zip file itself rather than the repo root. Detect this by
    walking up __file__'s parents until we find one that is an actual file on
    disk (the zipapp boundary), then step past it to reach the repo root.
    Falls back to __file__-relative navigation for dev / editable installs.
    """
    src = Path(__file__).resolve()
    zipapp = next((p for p in src.parents if p.is_file()), None)
    if zipapp is not None:
        repo_root = zipapp.parent.parent.parent
    else:
        repo_root = src.parent.parent.parent
    return repo_root / "build" / "prod" / "colette"


_LOCAL_BIN = _find_local_bin()
_thread_local = threading.local()

# Extra SSH options used only for non-interactive sync calls:
# - BatchMode=yes  — fail immediately instead of prompting for passwords
# - ConnectTimeout — prevent background threads from hanging on unreachable hosts
_SYNC_SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=30"]


def _synced_machines() -> set:
    """Return the per-thread set of already-synced machine keys."""
    if not hasattr(_thread_local, "synced_machines"):
        _thread_local.synced_machines = set()
    return _thread_local.synced_machines


def _ssh_base_args(machine):
    """Build base SSH arguments from machine config."""
    args = ["ssh"]
    if "ssh_key" in machine:
        args += ["-i", machine["ssh_key"]]
    if "port" in machine:
        args += ["-p", str(machine["port"])]
    args.append(machine["host"])
    return args


def _scp_args(machine):
    """Build base SCP arguments from machine config. Note: scp uses -P for port."""
    args = ["scp"]
    if "ssh_key" in machine:
        args += ["-i", machine["ssh_key"]]
    if "port" in machine:
        args += ["-P", str(machine["port"])]
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
    """
    base = _ssh_base_args(machine)
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
    """Run a command on a remote machine with a TTY allocated."""
    base = _ssh_base_args(machine)
    # Insert -t right after "ssh" to force TTY allocation.
    cmd = [base[0], "-t"] + base[1:] + [remote_cmd]
    subprocess.run(cmd)


def inject_project_config(machine, machine_name, project):
    """Inject hook files and JSON config for a project onto a remote machine.

    Transfers project hooks and (if applicable) template hooks file-by-file via
    SSH without compression. Merges the project and template entries into the
    remote projects.json / templates.json. Warns and returns False on any failure.
    """
    from colette_cli.utils.config import (
        load_templates,
        PROJECT_HOOKS_DIR,
        TEMPLATE_SCRIPTS_DIR,
    )
    from colette_cli.utils.formatting import warn

    project_name = project["name"]
    template_name = project.get("template")
    remote_base = "$HOME/.config/colette"

    def _ssh_write(remote_path, content_bytes):
        result = subprocess.run(
            _ssh_base_args(machine) + [f"cat > {remote_path}"],
            input=content_bytes,
            capture_output=True,
        )
        return result.returncode == 0

    def _ssh_mkdir(remote_path):
        result = ssh_run(machine, f"mkdir -p {remote_path}")
        return result.returncode == 0

    # Create base config dir
    if not _ssh_mkdir(remote_base):
        warn(f"inject: failed to create remote config dir on '{machine_name}'")
        return False

    # Transfer project hook files
    project_hooks_dir = PROJECT_HOOKS_DIR / project_name
    if project_hooks_dir.exists():
        remote_project_dir = f"{remote_base}/projects/{project_name}"
        if not _ssh_mkdir(remote_project_dir):
            warn(f"inject: failed to create remote project hooks dir on '{machine_name}'")
            return False
        for hook_file in project_hooks_dir.iterdir():
            if hook_file.is_file():
                remote_path = f"{remote_project_dir}/{hook_file.name}"
                if not _ssh_write(remote_path, hook_file.read_bytes()):
                    warn(f"inject: failed to transfer '{hook_file.name}' to '{machine_name}'")

    # Transfer template hook files
    if template_name:
        template_hooks_dir = TEMPLATE_SCRIPTS_DIR / template_name
        if template_hooks_dir.exists():
            remote_template_dir = f"{remote_base}/templates/{template_name}"
            if not _ssh_mkdir(remote_template_dir):
                warn(f"inject: failed to create remote template hooks dir on '{machine_name}'")
                return False
            for hook_file in template_hooks_dir.iterdir():
                if hook_file.is_file():
                    remote_path = f"{remote_template_dir}/{hook_file.name}"
                    if not _ssh_write(remote_path, hook_file.read_bytes()):
                        warn(f"inject: failed to transfer '{hook_file.name}' to '{machine_name}'")

    # Merge projects.json on remote
    result = ssh_run(machine, f"cat {remote_base}/projects.json 2>/dev/null || echo '[]'")
    try:
        remote_projects = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        remote_projects = []
    remote_projects = [p for p in remote_projects if p.get("name") != project_name]
    remote_projects.append(project)
    projects_json = json.dumps(remote_projects, indent=2).encode()
    if not _ssh_write(f"{remote_base}/projects.json", projects_json):
        warn(f"inject: failed to write projects.json on '{machine_name}'")
        return False

    # Merge templates.json on remote (if template used)
    if template_name:
        all_templates = load_templates()
        template_meta = next(
            (t for t in all_templates.get("templates", []) if t.get("name") == template_name),
            None,
        )
        if template_meta:
            result = ssh_run(machine, f"cat {remote_base}/templates.json 2>/dev/null || echo '{{\"templates\":[]}}'")
            try:
                remote_tmpl_data = json.loads(result.stdout or '{"templates":[]}')
                if not isinstance(remote_tmpl_data, dict):
                    remote_tmpl_data = {"templates": []}
            except json.JSONDecodeError:
                remote_tmpl_data = {"templates": []}
            remote_tmpl_list = [
                t for t in remote_tmpl_data.get("templates", [])
                if t.get("name") != template_name
            ]
            remote_tmpl_list.append(template_meta)
            templates_json = json.dumps({"templates": remote_tmpl_list}, indent=2).encode()
            if not _ssh_write(f"{remote_base}/templates.json", templates_json):
                warn(f"inject: failed to write templates.json on '{machine_name}'")

    return True


def sync_remote_colette(machine, machine_name):
    """Sync the local colette binary to a remote machine.

    Compares the remote version (via `<colette_path> --version`) against
    _local_version. Syncs the binary via scp if they differ, creates the remote
    path if it does not exist. Fires a system notification for install/update
    events. Uses a per-thread cache to avoid redundant SSH round-trips within
    a single invocation (thread-local so TUI async operations are independent).
    Does nothing if machine has no 'colette_path' key.

    Returns:
        True  — binary was synced successfully
        False — already up to date or already processed this thread's invocation
        None  — error occurred (warning already emitted)
    """
    from colette_cli.utils.formatting import info, warn

    remote_path = machine.get("colette_path")
    if not remote_path:
        return False

    machine_key = machine.get("name") or machine.get("host", "")
    synced = _synced_machines()
    if machine_key in synced:
        return False

    if not _LOCAL_BIN.is_file():
        warn(f"binary sync skipped for '{machine_name}': local build not found at {_LOCAL_BIN}")
        send_notification("colette", f"Sync skipped for '{machine_name}': local build not found")
        synced.add(machine_key)
        return None

    info(f"Syncing colette to '{machine_name}'…")
    version_result = ssh_run(
        machine,
        f"{shlex.quote(remote_path)} --version 2>/dev/null || true",
        extra_opts=_SYNC_SSH_OPTS,
    )
    remote_output = (version_result.stdout or "").strip()

    remote_version = None
    if remote_output:
        parts = remote_output.split()
        if len(parts) >= 2:
            remote_version = parts[-1]

    need_sync = remote_version != _local_version
    was_absent = remote_version is None

    if need_sync:
        remote_dir = shlex.quote(str(Path(remote_path).parent))
        ssh_run(machine, f"mkdir -p {remote_dir}", extra_opts=_SYNC_SSH_OPTS)

        dest = f"{machine['host']}:{remote_path}"
        cp_result = subprocess.run(
            _scp_args(machine) + _SYNC_SSH_OPTS + [str(_LOCAL_BIN), dest],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
        if cp_result.returncode != 0:
            details = cp_result.stderr.strip() or f"exit {cp_result.returncode}"
            warn(f"failed to copy colette to '{machine_name}': {details}")
            send_notification("colette", f"Failed to sync binary to '{machine_name}'")
            return None

        chmod_result = ssh_run(
            machine,
            f"chmod +x {shlex.quote(remote_path)}",
            extra_opts=_SYNC_SSH_OPTS,
        )
        if chmod_result.returncode != 0:
            warn(f"copied colette to '{machine_name}' but chmod +x failed (exit {chmod_result.returncode})")

        if was_absent:
            info(f"Installed colette on '{machine_name}' at {remote_path}")
            send_notification("colette", f"Installed colette on '{machine_name}'")
        else:
            info(f"Updated colette on '{machine_name}' to {_local_version}")
            send_notification("colette", f"Updated colette on '{machine_name}'")

    synced.add(machine_key)
    return need_sync
