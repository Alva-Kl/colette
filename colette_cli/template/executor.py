"""Template lifecycle execution helpers."""

import os
import shlex
import subprocess

from colette_cli.utils.config import read_project_hook, read_template_hook
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


def build_project_bootstrap(project, machine_name, template_metadata):
    """Build the shell bootstrap for project tmux sessions."""
    parts = []
    template_name = (template_metadata or {}).get("name")
    if template_name:
        coletterc = read_template_hook(template_name, "coletterc")
        if _has_effective_script(coletterc):
            parts.append(coletterc)
    parts.append("exec bash")
    return "; ".join(parts)


def _hook_environment(
    project, machine_name, template_name, machine, template_metadata=None
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
    return env


def _resolve_hook(project_name, template_name, hook_name):
    """Resolve a hook script for a project, with project-specific override support.

    Returns the script content if effective, or None if no hook is defined.
    """
    command = read_project_hook(project_name, hook_name)
    if command is None and template_name:
        command = read_template_hook(template_name, hook_name)
    return command if _has_effective_script(command) else None


def run_template_hook(
    project,
    machine,
    machine_name,
    is_remote,
    template_metadata,
    hook_name,
    fail_on_error=False,
):
    """Run a configured template hook in the project directory."""
    template_name = (template_metadata or {}).get("name")

    command = _resolve_hook(project["name"], template_name, hook_name)
    if command is None:
        return True

    env = _hook_environment(
        project, machine_name, template_name, machine, template_metadata
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

    Returns None if no effective hook is defined for the project.
    """
    template_name = (template_metadata or {}).get("name")
    command = _resolve_hook(project["name"], template_name, hook_name)
    if command is None:
        return None
    env = _hook_environment(
        project, machine_name, template_name, machine, template_metadata
    )
    assignments = " ".join(
        f"{key}={shlex.quote(str(value))}"
        for key, value in env.items()
        if key.startswith("COLETTE_")
    )
    return (
        f"cd {shlex.quote(project['path'])} && "
        f"env {assignments} bash -lc {shlex.quote(command)}"
    )
