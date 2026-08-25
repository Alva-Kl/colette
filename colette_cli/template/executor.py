"""Template lifecycle execution helpers."""

import base64
import os
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from colette_cli.utils.config import (
    append_hook_failure,
    get_machine_template_dir,
    get_machine_template_hook_path,
    get_machine_template_params,
    machine_template_hook_exists,
    read_machine_template_hook,
    read_project_hook,
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


def _template_name(template_metadata) -> str | None:
    """Return the template name from metadata, or None."""
    return (template_metadata or {}).get("name")


def _build_env_assignments(env, *, include_super: bool = False) -> str:
    """Build a shell ``key=value`` string from *env* for use with ``env …``.

    Includes all ``COLETTE_*`` keys, and optionally ``SUPER`` when
    *include_super* is True.
    """
    return " ".join(
        f"{key}={shlex.quote(str(value))}"
        for key, value in env.items()
        if key.startswith("COLETTE_") or (include_super and key == "SUPER")
    )


def _run_hook_subprocess(command, cwd, is_remote, machine, env):
    """Run *command* locally or via SSH and return a CompletedProcess-like object."""
    if is_remote:
        assignments = _build_env_assignments(env)
        remote_cmd = f"cd {shlex.quote(str(cwd))} && env {assignments} bash -lc {shlex.quote(command)}"
        return ssh_run(machine, remote_cmd)
    return subprocess.run(
        ["bash", "-lc", command],
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        start_new_session=True,
    )


def _handle_hook_failure(result, hook_name, project_name, template_name, fail_on_error):
    """Log a hook failure, emit a warning or error, and return False."""
    stderr = result.stderr.strip()
    stdout = result.stdout.strip()
    summary = stderr or stdout or f"exit code {result.returncode}"
    output = "\n".join(filter(None, [stderr, stdout])) or f"exit code {result.returncode}"
    if project_name:
        message = (
            f"template hook '{hook_name}' failed for project '{project_name}' "
            f"({template_name}): {summary}"
        )
    else:
        message = f"template hook '{hook_name}' failed for template '{template_name}': {summary}"
    append_hook_failure({
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project": project_name or "",
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


class _FetchedContent(str):
    """Marks a string as already-fetched hook content (e.g. from
    ssh_read_hook_files), as opposed to a path string — see _super_assignment.
    """


def _super_assignment_from_content(content: str) -> str:
    """Return a bash SUPER assignment that inlines *content* directly (no disk read)."""
    b64 = base64.b64encode(content.encode()).decode()
    return f"SUPER=$(mktemp) && printf '%s' {shlex.quote(b64)} | base64 -d > \"$SUPER\""


def _super_assignment(super_source, is_remote: bool = False) -> str:
    """Return a bash assignment statement for the SUPER variable.

    *super_source* is either a path (Path or str) to a local hook file, or a
    _FetchedContent instance carrying already-fetched hook content (e.g. from
    ssh_read_hook_files) — content is always inlined via a base64 tempfile
    regardless of *is_remote*, since there's no local path to reference either way.

    Local (path, not is_remote): ``SUPER=/absolute/local/path``
    Local (path, is_remote): inlines the local file's content via a
    base64-encoded tempfile so the path exists on the remote machine.
    """
    if isinstance(super_source, _FetchedContent):
        return _super_assignment_from_content(str(super_source))
    if not is_remote:
        return f"SUPER={shlex.quote(str(super_source))}"
    return _super_assignment_from_content(Path(super_source).read_text())


def _resolve_hook_with_super(project_name, template_name, hook_name, machine_name=None, remote_hooks=None):
    """Resolve a hook for a project, returning (content, super_source).

    Local resolution order (used when *remote_hooks* is None):
      1. Project-specific hook
      2. Machine-template hook (machine_name + template override)
    The project hook can call `source $SUPER` to delegate to the
    machine-template hook; super_source is a Path in this mode.

    When *remote_hooks* is provided (a dict from ssh_read_hook_files), this
    resolves against that pre-fetched remote snapshot instead of local disk,
    collapsing to two tiers: project hook, then template hook — both are
    already fully resolved/flattened remote copies (pushed by
    push_project_hooks/push_template_hooks), so there's no separate
    machine-scoped-override tier to consider remotely. super_source in this
    mode is the already-fetched template hook content (a str), not a path.

    Returns (None, None) if no effective hook is found.
    """
    if remote_hooks is not None:
        entry = remote_hooks.get(hook_name, {})
        project_hook = entry.get("project")
        template_hook = entry.get("template")
        if _has_effective_script(project_hook):
            return project_hook, (_FetchedContent(template_hook) if _has_effective_script(template_hook) else None)
        if _has_effective_script(template_hook):
            return template_hook, None
        return None, None

    machine_template_path = (
        get_machine_template_hook_path(machine_name, template_name, hook_name)
        if machine_name and template_name
        else None
    )

    project_hook = read_project_hook(project_name, hook_name) if project_name else None
    if _has_effective_script(project_hook):
        # super for project hook: the machine-template hook, if effective
        if machine_name and template_name and machine_template_hook_exists(machine_name, template_name, hook_name):
            machine_hook_content = read_machine_template_hook(machine_name, template_name, hook_name)
            if _has_effective_script(machine_hook_content):
                return project_hook, machine_template_path
        return project_hook, None

    if machine_name and template_name:
        machine_hook = read_machine_template_hook(machine_name, template_name, hook_name)
        if _has_effective_script(machine_hook):
            return machine_hook, None

    return None, None


def _hook_environment(
    project, machine_name, template_name, machine, template_metadata=None, super_path=None,
    machine_params=None,
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
    # Shared template params, then machine-specific params override them.
    merged_params = dict((template_metadata or {}).get("params") or {})
    merged_params.update(machine_params or {})
    for key, value in merged_params.items():
        env[f"COLETTE_PARAM_{key.upper()}"] = str(value)
    if super_path:
        env["SUPER"] = str(super_path)
    return env


def _prepend_coletterc(project_name, template_name, command, hook_super_path=None, is_remote: bool = False, remote_hooks=None, machine_name=None):
    """Prepend coletterc sourcing to a hook command.

    When a project-level coletterc is active, SUPER is set to the template
    coletterc path before the content runs, enabling `source $SUPER`.
    If hook_super_path is provided it is restored after coletterc runs so that
    the following hook script sees the correct $SUPER value.
    Returns the unmodified command if no effective coletterc is found.
    """
    coletterc, super_path = _resolve_hook_with_super(
        project_name, template_name, "coletterc", machine_name=machine_name, remote_hooks=remote_hooks
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


def build_project_bootstrap(project, machine_name, template_metadata, is_remote: bool = False, machine=None):
    """Build the shell bootstrap command for a project tmux session.

    Uses `bash --rcfile` to source ~/.bashrc first, then coletterc, so that
    venv activations in coletterc persist after the shell's rc file runs.
    When a project-level coletterc is active, SUPER is set to the template
    coletterc path so it can call `source $SUPER` for inheritance.
    When *is_remote* is True, coletterc content is fetched fresh from the
    remote machine's own config over SSH (via *machine*) and inlined as a
    base64 tempfile, rather than read from local disk.
    """
    tmpl_name = _template_name(template_metadata)

    remote_hooks = None
    if is_remote:
        from colette_cli.utils.ssh import ssh_read_hook_files
        remote_hooks = ssh_read_hook_files(machine or {}, project["name"], tmpl_name)

    coletterc, super_path = _resolve_hook_with_super(
        project["name"], tmpl_name, "coletterc", machine_name=machine_name, remote_hooks=remote_hooks
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
    tmpl_name = _template_name(template_metadata)

    remote_hooks = None
    if is_remote:
        from colette_cli.utils.ssh import ssh_read_hook_files
        remote_hooks = ssh_read_hook_files(machine, project["name"], tmpl_name)

    command, super_path = _resolve_hook_with_super(
        project["name"], tmpl_name, hook_name, machine_name=machine_name, remote_hooks=remote_hooks
    )
    if command is None:
        return True

    command = _prepend_coletterc(
        project["name"], tmpl_name, command, hook_super_path=super_path,
        is_remote=is_remote, remote_hooks=remote_hooks, machine_name=machine_name,
    )

    machine_params = get_machine_template_params(machine, tmpl_name) if tmpl_name else {}
    env = _hook_environment(
        project, machine_name, tmpl_name, machine, template_metadata,
        super_path=None if is_remote else super_path,
        machine_params=machine_params,
    )

    result = _run_hook_subprocess(command, project["path"], is_remote, machine, env)
    if result.returncode == 0:
        return True
    return _handle_hook_failure(result, hook_name, project["name"], tmpl_name, fail_on_error)


def build_hook_command(project, machine_name, template_metadata, machine, hook_name):
    """Build a shell command string for running a hook interactively.

    coletterc is prepended to the hook command. $SUPER is set when a
    project-level hook is active. Returns None if no effective hook is defined.
    """
    from colette_cli.utils.helpers import is_remote_machine
    is_remote = is_remote_machine(machine)
    tmpl_name = _template_name(template_metadata)

    remote_hooks = None
    if is_remote:
        from colette_cli.utils.ssh import ssh_read_hook_files
        remote_hooks = ssh_read_hook_files(machine, project["name"], tmpl_name)

    command, super_path = _resolve_hook_with_super(
        project["name"], tmpl_name, hook_name, machine_name=machine_name, remote_hooks=remote_hooks
    )
    if command is None:
        return None

    command = _prepend_coletterc(
        project["name"], tmpl_name, command, hook_super_path=super_path,
        is_remote=is_remote, remote_hooks=remote_hooks, machine_name=machine_name,
    )

    machine_params = get_machine_template_params(machine, tmpl_name) if tmpl_name else {}
    env = _hook_environment(
        project, machine_name, tmpl_name, machine, template_metadata,
        super_path=None if is_remote else super_path,
        machine_params=machine_params,
    )
    assignments = _build_env_assignments(env, include_super=True)
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
    command = read_machine_template_hook(machine_name, template_name, "onupdate") if machine_name else None
    if not _has_effective_script(command):
        return True

    # Prepend the template's coletterc (no project override possible here)
    coletterc = read_machine_template_hook(machine_name, template_name, "coletterc") if machine_name else None
    if _has_effective_script(coletterc):
        command = coletterc.strip() + "\n" + command

    env = dict(os.environ)
    env.update(
        {
            "COLETTE_TEMPLATE_NAME": template_name,
            "COLETTE_MACHINE_NAME": machine_name or "",
        }
    )
    # Merge shared template params with machine-specific overrides.
    merged_params = dict((template_metadata or {}).get("params") or {})
    merged_params.update(get_machine_template_params(machine, template_name))
    for key, value in merged_params.items():
        env[f"COLETTE_PARAM_{key.upper()}"] = str(value)
    if template_path:
        env["COLETTE_TEMPLATE_PATH"] = str(template_path)

    hooks_dir = str(get_machine_template_dir(machine_name, template_name))
    cwd = template_path or hooks_dir

    result = _run_hook_subprocess(command, cwd, is_remote, machine, env)
    if result.returncode == 0:
        return True
    return _handle_hook_failure(result, "onupdate", None, template_name, fail_on_error)


def compute_effective_template_hook(template_name, hook_name, machine_name):
    """Return the flattened, self-contained script for a template's hook on a
    specific machine (its machine-scoped override if effective, else the
    shared template hook), or None if neither exists.

    Used by push_template_hooks (colette_cli.utils.ssh) when pushing a
    template's hooks to a remote machine: the remote should end up with one
    canonical, already-resolved copy per hook, not a 3-tier override chain to
    re-resolve itself. Any `source "$SUPER"` chain from override to shared
    hook is inlined via a base64 tempfile (same trick used for genuine remote
    execution) so the pushed script has no dependency on a local file path.
    """
    content, super_source = _resolve_hook_with_super(None, template_name, hook_name, machine_name=machine_name)
    if not _has_effective_script(content):
        return None
    if not super_source:
        return content
    return _super_assignment(super_source, is_remote=True) + "\n" + content
