"""Template lifecycle execution helpers."""

import base64
import os
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from colette_cli.utils.config import (
    append_hook_failure,
    get_template_hook_path,
    read_project_hook,
    read_template_hook,
)
from colette_cli.utils.formatting import err, warn
from colette_cli.utils.ssh import ssh_run


def _has_effective_script(content):
    if not content:
        return False
    lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return bool(lines)


def _super_assignment(super_path, is_remote: bool = False) -> str:
    """Return a bash assignment statement for the SUPER variable.

    Local: ``SUPER=/absolute/local/path``
    Remote: inlines the file content via a base64-encoded tempfile so the path
    exists on the remote machine.
    """
    if not is_remote:
        return f"SUPER={shlex.quote(str(super_path))}"
    content = Path(super_path).read_text()
    b64 = base64.b64encode(content.encode()).decode()
    return f"SUPER=$(mktemp) && printf '%s' {shlex.quote(b64)} | base64 -d > \"$SUPER\""


def _has_effective_script(content):
    if not content:
        return False
    lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return bool(lines)


def _resolve_hook_with_super(project_name, template_name, hook_name):
    """Resolve a hook for a project, returning (content, super_path).

    Checks the project-specific hook first, then falls back to the template hook.
    When a project-level override is active, super_path is set to the template
    hook file path so the project hook can call `source $SUPER` to inherit the
    template hook. Returns (None, None) if no effective hook is found.
    """
    project_hook = read_project_hook(project_name, hook_name)
    if _has_effective_script(project_hook):
        super_path = (
            get_template_hook_path(template_name, hook_name) if template_name else None
        )
        return project_hook, super_path
    if template_name:
        template_hook = read_template_hook(template_name, hook_name)
        if _has_effective_script(template_hook):
            return template_hook, None
    return None, None


def _hook_environment(
    project, machine_name, template_name, machine, template_metadata=None, super_path=None
):
    env = dict(os.environ)
    env.update(
        {
            "COLETTE_PROJECT_NAME": project["name"],
            "COLETTE_PROJECT_PATH": project["path"],
            "COLETTE_MACHINE_NAME": machine_name,
            "COLETTE_TEMPLATE_NAME": template_name or "",
        }
    )
    for key, value in ((template_metadata or {}).get("params") or {}).items():
        env[f"COLETTE_PARAM_{key.upper()}"] = str(value)
    if super_path:
        env["SUPER"] = str(super_path)
    return env


def _prepend_coletterc(project_name, template_name, command, hook_super_path=None, is_remote: bool = False):
    """Prepend coletterc sourcing to a hook command.

    When a project-level coletterc is active, SUPER is set to the template
    coletterc path before the content runs, enabling `source $SUPER`.
    If hook_super_path is provided it is restored after coletterc runs so that
    the following hook script sees the correct $SUPER value.
    Returns the unmodified command if no effective coletterc is found.
    """
    coletterc, super_path = _resolve_hook_with_super(
        project_name, template_name, "coletterc"
    )
    if not coletterc:
        return command
    prefix_lines = []
    if super_path:
        prefix_lines.append(_super_assignment(super_path, is_remote))
    prefix_lines.append(coletterc.strip())
    if hook_super_path:
        prefix_lines.append(_super_assignment(hook_super_path, is_remote))
    return "\n".join(prefix_lines) + "\n" + command


def build_project_bootstrap(project, machine_name, template_metadata, is_remote: bool = False):
    """Build the shell bootstrap command for a project tmux session.

    Uses `bash --rcfile` to source ~/.bashrc first, then coletterc, so that
    venv activations in coletterc persist after the shell's rc file runs.
    When a project-level coletterc is active, SUPER is set to the template
    coletterc path so it can call `source $SUPER` for inheritance.
    When *is_remote* is True, the template hook file is inlined as a base64
    tempfile so the remote machine doesn't need it at the local path.
    """
    template_name = (template_metadata or {}).get("name")
    coletterc, super_path = _resolve_hook_with_super(
        project["name"], template_name, "coletterc"
    )
    if not _has_effective_script(coletterc):
        return "exec bash"
    rc_lines = [". ~/.bashrc 2>/dev/null"]
    if super_path:
        rc_lines.append(_super_assignment(super_path, is_remote))
    rc_lines.append(coletterc.strip())
    rc_content = "\n".join(rc_lines) + "\n"
    rc_b64 = base64.b64encode(rc_content.encode()).decode()
    return f"exec bash --rcfile <(echo {shlex.quote(rc_b64)} | base64 -d)"


def run_template_hook(
    project,
    machine,
    machine_name,
    is_remote,
    template_metadata,
    hook_name,
    fail_on_error=False,
):
    """Run a configured template hook in the project directory.

    coletterc is sourced before the hook script so the common environment is
    always available. When a project-level hook is active, $SUPER is set to
    the template hook file path so the project hook can call `source $SUPER`.
    """
    template_name = (template_metadata or {}).get("name")

    command, super_path = _resolve_hook_with_super(
        project["name"], template_name, hook_name
    )
    if command is None:
        return True

    command = _prepend_coletterc(project["name"], template_name, command, hook_super_path=super_path, is_remote=is_remote)

    env = _hook_environment(
        project, machine_name, template_name, machine, template_metadata,
        super_path=None if is_remote else super_path,
    )

    if is_remote:
        assignments = " ".join(
            f"{key}={shlex.quote(value)}"
            for key, value in env.items()
            if key.startswith("COLETTE_")
        )
        remote_cmd = f"cd {shlex.quote(project['path'])} && env {assignments} bash -lc {shlex.quote(command)}"
        result = ssh_run(machine, remote_cmd)
    else:
        result = subprocess.run(
            ["bash", "-lc", command],
            cwd=project["path"],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            start_new_session=True,
        )

    if result.returncode == 0:
        return True

    stderr = result.stderr.strip()
    stdout = result.stdout.strip()
    details = stderr or stdout or f"exit code {result.returncode}"
    output = "\n".join(filter(None, [stderr, stdout])) or f"exit code {result.returncode}"
    message = (
        f"template hook '{hook_name}' failed for project '{project['name']}' "
        f"({template_name}): {details}"
    )
    append_hook_failure({
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project": project["name"],
        "template": template_name or "",
        "hook": hook_name,
        "exit_code": result.returncode,
        "output": output,
    })
    if fail_on_error:
        err(message)
    else:
        warn(message)
    return False


def build_hook_command(project, machine_name, template_metadata, machine, hook_name):
    """Build a shell command string for running a hook interactively.

    coletterc is prepended to the hook command. $SUPER is set when a
    project-level hook is active. Returns None if no effective hook is defined.
    """
    template_name = (template_metadata or {}).get("name")
    command, super_path = _resolve_hook_with_super(
        project["name"], template_name, hook_name
    )
    if command is None:
        return None

    command = _prepend_coletterc(project["name"], template_name, command, hook_super_path=super_path)

    env = _hook_environment(
        project, machine_name, template_name, machine, template_metadata, super_path
    )
    assignments = " ".join(
        f"{key}={shlex.quote(str(value))}"
        for key, value in env.items()
        if key.startswith("COLETTE_") or key == "SUPER"
    )
    return (
        f"cd {shlex.quote(project['path'])} && "
        f"env {assignments} bash -lc {shlex.quote(command)}"
    )


def run_onupdate_for_template(
    template_name,
    machine,
    machine_name,
    is_remote,
    template_metadata,
    template_path=None,
    fail_on_error=False,
):
    """Run the onupdate hook directly for a template (without a project context).

    Unlike run_template_hook, this targets the template itself rather than a
    project. Only the template hook is consulted — there is no project-level
    override. The template's coletterc is prepended before the hook runs.
    The working directory is *template_path* when provided, or the template
    hooks directory otherwise.
    """
    command = read_template_hook(template_name, "onupdate")
    if not _has_effective_script(command):
        return True

    # Prepend the template's coletterc (no project override possible here)
    coletterc = read_template_hook(template_name, "coletterc")
    if _has_effective_script(coletterc):
        command = coletterc.strip() + "\n" + command

    env = dict(os.environ)
    env.update(
        {
            "COLETTE_TEMPLATE_NAME": template_name,
            "COLETTE_MACHINE_NAME": machine_name or "",
        }
    )
    for key, value in ((template_metadata or {}).get("params") or {}).items():
        env[f"COLETTE_PARAM_{key.upper()}"] = str(value)
    if template_path:
        env["COLETTE_TEMPLATE_PATH"] = str(template_path)

    hooks_dir = str(get_template_hook_path(template_name, "onupdate").parent)
    cwd = template_path or hooks_dir

    if is_remote:
        assignments = " ".join(
            f"{key}={shlex.quote(value)}"
            for key, value in env.items()
            if key.startswith("COLETTE_")
        )
        remote_cmd = f"cd {shlex.quote(str(cwd))} && env {assignments} bash -lc {shlex.quote(command)}"
        result = ssh_run(machine, remote_cmd)
    else:
        result = subprocess.run(
            ["bash", "-lc", command],
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            start_new_session=True,
        )

    if result.returncode == 0:
        return True

    stderr = result.stderr.strip()
    stdout = result.stdout.strip()
    details = stderr or stdout or f"exit code {result.returncode}"
    output = "\n".join(filter(None, [stderr, stdout])) or f"exit code {result.returncode}"
    message = (
        f"template hook 'onupdate' failed for template '{template_name}': {details}"
    )
    append_hook_failure({
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project": "",
        "template": template_name,
        "hook": "onupdate",
        "exit_code": result.returncode,
        "output": output,
    })
    if fail_on_error:
        err(message)
    else:
        warn(message)
    return False
