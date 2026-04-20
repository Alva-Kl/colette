"""Project sub-commands: create, delete, list, attach, code, copilot."""

import shlex
import shutil
import subprocess
from pathlib import Path

from colette_cli.template import (
    build_project_bootstrap,
    get_machine_template,
    get_project_template_name,
    get_template_metadata,
    list_machine_template_names,
    run_template_hook,
)
from colette_cli.utils.config import (
    get_machine,
    get_project,
    load_config,
    load_projects,
    require_machine,
    save_projects,
)
from colette_cli.utils.formatting import bold, cyan, dim, err, info, red
from colette_cli.utils.helpers import build_projects_by_machine, is_remote_machine
from colette_cli.utils.ssh import ssh_interactive, ssh_run
from colette_cli.utils.tmux import get_sessions, local_tmux_session
from colette_cli.utils.validation import validate_project_name


def require_project(name):
    """Get a project or error if not found."""
    project = get_project(name)
    if not project:
        err(
            f"project '{name}' not found. Run 'colette list' to see available projects."
        )
    return project


def cmd_create(args):
    """Create a new project from template on a machine."""
    name = args.name
    if not validate_project_name(name):
        err(
            f"'{name}' is not a valid project name. "
            "Use only lowercase letters, numbers, and hyphens "
            "(must start and end with alphanumeric)."
        )

    cfg = load_config()
    projects = load_projects()

    if any(project["name"] == name for project in projects):
        err(f"project '{name}' already exists.")

    machine_name = args.machine or cfg.get("default_machine")
    if not machine_name:
        err(
            "no machine specified and no default machine set. "
            "Run 'colette config add-machine' first."
        )

    machine = require_machine(cfg, machine_name)
    projects_dir = machine.get("projects_dir", "")
    template_names = list_machine_template_names(machine)
    if not template_names or not projects_dir:
        err(f"machine '{machine_name}' is missing templates or 'projects_dir'.")

    template_name = args.template
    if template_name and template_name not in template_names:
        err(
            f"template '{template_name}' is not available on machine '{machine_name}'. "
            f"Available templates: {', '.join(template_names)}"
        )
    if not template_name:
        print(f"Available templates for '{machine_name}':")
        for template_option in template_names:
            print(f"  - {template_option}")
        template_name = input("Template name: ").strip()
        if not template_name:
            err("template name cannot be empty.")
        if template_name not in template_names:
            err(
                f"template '{template_name}' is not available on machine '{machine_name}'."
            )

    template_source = get_machine_template(machine, template_name)
    if template_source["type"] == "directory" and not (template_source.get("path") or "").strip():
        err(f"template '{template_name}' has no source path configured.")
    if template_source["type"] == "git" and not (template_source.get("url") or "").strip():
        err(f"template '{template_name}' has no git URL configured.")
    template_metadata = get_template_metadata(machine, machine_name, template_name)

    is_remote = is_remote_machine(machine)
    project_path = str(Path(projects_dir) / name)

    info(
        f"Creating project '{name}' on machine '{machine_name}' at '{project_path}' ..."
    )

    if is_remote:
        if template_source["type"] == "directory":
            source_path = template_source["path"]
            result = ssh_run(machine, f"test -d {shlex.quote(source_path)} && echo ok")
            if result.stdout.strip() != "ok":
                err(
                    f"template '{source_path}' not found on remote machine '{machine_name}'."
                )
        else:
            source_path = template_source["url"]

        result = ssh_run(machine, f"test -e {shlex.quote(project_path)} && echo exists")
        if result.stdout.strip() == "exists":
            err(f"path '{project_path}' already exists on remote machine.")

        if template_source["type"] == "directory":
            result = ssh_run(
                machine,
                f"cp -r {shlex.quote(source_path)} {shlex.quote(project_path)}",
            )
        else:
            result = ssh_run(
                machine,
                f"git clone {shlex.quote(source_path)} {shlex.quote(project_path)}",
            )
        if result.returncode != 0:
            err(
                f"failed to create project from template on remote: {result.stderr.strip()}"
            )
    else:
        destination = Path(project_path).expanduser()
        if destination.exists():
            err(f"path '{destination}' already exists.")
        if template_source["type"] == "directory":
            template_path = Path(template_source["path"]).expanduser()
            if not template_path.exists():
                err(f"template '{template_path}' not found.")
            shutil.copytree(str(template_path), str(destination))
        else:
            clone_result = subprocess.run(
                ["git", "clone", template_source["url"], str(destination)],
                capture_output=True,
                text=True,
            )
            if clone_result.returncode != 0:
                err(f"failed to clone template: {clone_result.stderr.strip()}")

    project = {
        "name": name,
        "machine": machine_name,
        "path": project_path,
        "template": template_name,
    }
    run_template_hook(
        project,
        machine,
        machine_name,
        is_remote,
        template_metadata,
        "oncreate",
        fail_on_error=True,
    )
    projects.append(project)
    save_projects(projects)
    info(f"Project '{name}' created.")


def cmd_delete(args, skip_confirmation: bool = False):
    """Delete a project (remove files and record)."""
    name = args.name
    project = require_project(name)

    if not skip_confirmation:
        answer = input(
            f"Delete project '{name}' at '{project['path']}' on '{project['machine']}'?\n"
            f"This {red('cannot be undone')}. Type the project name to confirm: "
        ).strip()
        if answer != name:
            print("Aborted.")
            return

    cfg = load_config()
    machine = get_machine(cfg, project["machine"])
    machine_name = project["machine"]
    is_remote = is_remote_machine(machine)
    template_metadata = get_template_metadata(machine, machine_name, get_project_template_name(project))

    run_template_hook(
        project,
        machine,
        machine_name,
        is_remote,
        template_metadata,
        "ondelete",
        fail_on_error=False,
    )

    if is_remote:
        remote_path = project.get("path", "").strip()
        if not remote_path:
            err("refusing to delete: project path is empty")
        if not remote_path.startswith("/"):
            err(f"refusing to delete: remote path is not absolute: '{remote_path}'")
        parts = [p for p in remote_path.split("/") if p]
        if len(parts) < 3:
            err(f"refusing to delete: remote path is too shallow (must have at least 3 components): '{remote_path}'")
        result = ssh_run(machine, f"rm -rf {shlex.quote(remote_path)}")
        if result.returncode != 0:
            err(f"failed to remove remote directory: {result.stderr.strip()}")
    else:
        path = Path(project["path"]).expanduser()
        if path.exists():
            shutil.rmtree(str(path))

    save_projects([item for item in load_projects() if item["name"] != name])
    info(f"Project '{name}' deleted.")


def cmd_list(args):
    """List all projects grouped by machine."""
    projects = load_projects()
    if not projects:
        print(
            "No projects. Create one with 'colette create' or link one with 'colette link'."
        )
        return

    by_machine = build_projects_by_machine(projects)

    for machine_name in sorted(by_machine):
        print(f"\n{bold(f'[{machine_name}]')}")
        for project in sorted(by_machine[machine_name], key=lambda x: x["name"]):
            pname = project["name"]
            template = project.get("template") or dim("--")
            print(f"  {cyan(f'{pname:<30}')}  {template:<20}  {dim(project['path'])}")
    print()


def cmd_attach(args):
    """Attach to or create a project's tmux session."""
    name = args.name
    project = require_project(name)

    cfg = load_config()
    machine = get_machine(cfg, project["machine"])
    is_remote = is_remote_machine(machine)
    template_name = get_project_template_name(project)
    template_metadata = get_template_metadata(machine, project["machine"], template_name)
    startup_command = build_project_bootstrap(
        project, project["machine"], template_metadata, is_remote
    )

    tmux_cmd = (
        f"tmux set-option -g mouse on \\; new-session -A -s {shlex.quote(name)} -c {shlex.quote(project['path'])} "
        f"bash -lc {shlex.quote(startup_command)}"
    )

    if is_remote:
        ssh_interactive(machine, tmux_cmd)
    else:
        project_path = str(Path(project["path"]).expanduser())
        local_tmux_session(name, project_path, startup_command)


def cmd_code(args):
    """Open a project in VS Code (supports Remote SSH)."""
    name = args.name
    project = require_project(name)

    cfg = load_config()
    machine = get_machine(cfg, project["machine"])
    is_remote = is_remote_machine(machine)

    if is_remote:
        host = machine.get("host", "")
        uri = f"vscode-remote://ssh-remote+{host}{project['path']}"
        subprocess.run(["code", "--folder-uri", uri])
    else:
        subprocess.run(["code", str(Path(project["path"]).expanduser())])


def cmd_unlink(args):
    """Unlink a project from colette without deleting its files."""
    name = args.name
    project = require_project(name)

    answer = input(
        f"Unlink project '{name}' (path '{project['path']}' on '{project['machine']}' will NOT be deleted)? [y/N]: "
    ).strip().lower()
    if answer != "y":
        print("Aborted.")
        return

    save_projects([p for p in load_projects() if p["name"] != name])
    info(f"Project '{name}' unlinked (files not deleted).")


def _open_copilot_session(name, project_path, machine=None, is_remote=False):
    """Attach to the existing <name>-copilot tmux session, or start a new one."""
    tmux_session_name = f"{name}-copilot"
    sessions = get_sessions(machine or {}, is_remote)

    if tmux_session_name in sessions:
        if is_remote:
            ssh_interactive(machine, f"tmux set-option -g mouse on \\; attach-session -t {shlex.quote(tmux_session_name)}")
        else:
            local_tmux_session(tmux_session_name, project_path, "exec bash")
    else:
        if is_remote:
            tmux_cmd = (
                f"tmux set-option -g mouse on \\; new-session -A -s {shlex.quote(tmux_session_name)} "
                f"-c {shlex.quote(project_path)} bash -lc copilot"
            )
            ssh_interactive(machine, tmux_cmd)
        else:
            local_tmux_session(tmux_session_name, project_path, "copilot")


def cmd_copilot(args):
    """Open a project in GitHub Copilot in a dedicated tmux session."""
    name = args.name
    project = require_project(name)

    cfg = load_config()
    machine = get_machine(cfg, project["machine"])
    is_remote = is_remote_machine(machine)

    project_path = project["path"]
    if not is_remote:
        project_path = str(Path(project_path).expanduser())
    _open_copilot_session(name, project_path, machine=machine, is_remote=is_remote)


def cmd_link(args):
    """Link an existing project directory to colette without a template."""
    cfg = load_config()
    machine_name = args.machine or cfg.get("default_machine")
    if not machine_name:
        err(
            "no machine specified and no default machine set. "
            "Run 'colette config add-machine' first."
        )

    machine = require_machine(cfg, machine_name)
    is_remote = is_remote_machine(machine)

    path = args.path
    name = args.name or Path(path).name

    if not validate_project_name(name):
        err(
            f"'{name}' is not a valid project name. "
            "Use only lowercase letters, numbers, and hyphens "
            "(must start and end with alphanumeric)."
        )

    projects = load_projects()
    if any(p["name"] == name for p in projects):
        err(f"project '{name}' already exists.")

    if is_remote:
        result = ssh_run(machine, f"test -d {shlex.quote(path)} && echo ok")
        if result.stdout.strip() != "ok":
            err(f"path '{path}' does not exist on remote machine '{machine_name}'.")
    else:
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            err(f"path '{path}' does not exist.")
        path = str(resolved)

    project = {
        "name": name,
        "machine": machine_name,
        "path": path,
        "template": None,
    }
    projects.append(project)
    save_projects(projects)
    info(f"Project '{name}' linked from '{path}' on machine '{machine_name}'.")
