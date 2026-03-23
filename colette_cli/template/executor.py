"""Template lifecycle execution helpers."""

import base64
import os
import shlex
import subprocess

from colette_cli.utils.config import (
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
        if stripped == "#!/usr/bin/env bash":
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


def _prepend_coletterc(project_name, template_name, command):
    """Prepend coletterc sourcing to a hook command.

    When a project-level coletterc is active, SUPER is set to the template
    coletterc path before the content runs, enabling `source $SUPER`.
    Returns the unmodified command if no effective coletterc is found.
    """
    coletterc, super_path = _resolve_hook_with_super(
        project_name, template_name, "coletterc"
    )
    if not coletterc:
        return command
    prefix_lines = []
    if super_path:
        prefix_lines.append(f"SUPER={shlex.quote(str(super_path))}")
    prefix_lines.append(coletterc.strip())
    return "\n".join(prefix_lines) + "\n" + command


def build_project_bootstrap(project, machine_name, template_metadata):
    """Build the shell bootstrap command for a project tmux session.

    Uses `bash --rcfile` to source ~/.bashrc first, then coletterc, so that
    venv activations in coletterc persist after the shell's rc file runs.
    When a project-level coletterc is active, SUPER is set to the template
    coletterc path so it can call `source $SUPER` for inheritance.
    """
    template_name = (template_metadata or {}).get("name")
    coletterc, super_path = _resolve_hook_with_super(
        project["name"], template_name, "coletterc"
    )
    if not _has_effective_script(coletterc):
        return "exec bash"
    rc_lines = [". ~/.bashrc 2>/dev/null"]
    if super_path:
        rc_lines.append(f"SUPER={shlex.quote(str(super_path))}")
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

    command = _prepend_coletterc(project["name"], template_name, command)

    env = _hook_environment(
        project, machine_name, template_name, machine, template_metadata, super_path
    )

    if is_remote:
        assignments = " ".join(
            f"{key}={shlex.quote(value)}"
            for key, value in env.items()
            if key.startswith("COLETTE_") or key == "SUPER"
        )
        remote_cmd = f"cd {shlex.quote(project['path'])} && env {assignments} bash -lc {shlex.quote(command)}"
        result = ssh_run(machine, remote_cmd)
    else:
        result = subprocess.run(
            ["bash", "-lc", command],
            cwd=project["path"],
            env=env,
            capture_output=True,
            text=True,
        )

    if result.returncode == 0:
        return True

    details = (
        result.stderr.strip()
        or result.stdout.strip()
        or f"exit code {result.returncode}"
    )
    message = (
        f"template hook '{hook_name}' failed for project '{project['name']}' "
        f"({template_name}): {details}"
    )
    if fail_on_error:
        err(message)
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

    command = _prepend_coletterc(project["name"], template_name, command)

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
