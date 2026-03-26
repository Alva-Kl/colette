"""Screen builders for the Colette TUI.

Each public function returns a list[MenuItem] for a particular screen.
Actions that need to leave curses (open nano, launch tmux) are wrapped so
curses is suspended/resumed around them.  Actions that only need text input
use in-TUI overlay forms from ``tui.forms`` instead.
"""

import shlex
import subprocess
from pathlib import Path

from argparse import Namespace

from colette_cli.template import SCRIPT_KEYS
from colette_cli.utils.config import (
    get_template_hook_path,
    get_project_hook_path,
    load_config,
    load_hook_failures,
    clear_hook_failures,
    load_projects,
    load_templates,
    save_config,
    save_projects,
    save_templates,
    scaffold_project_hook_files,
)
from colette_cli.template import (
    get_project_template_name,
    get_template_metadata,
    list_machine_template_names,
    normalize_machine_templates,
    upsert_template_metadata,
)
from colette_cli.utils.tmux import local_tmux_session
from colette_cli.template import build_project_bootstrap

from .menu import MenuItem


def _suspend(fn):
    """Return a wrapper that suspends curses, runs fn, then resumes.

    Catches SystemExit (raised by err()) so a failing command never crashes
    the TUI — the user sees the error and presses Enter to return.
    """
    import curses

    def wrapper(*args, **kwargs):
        curses.endwin()
        try:
            fn(*args, **kwargs)
        except SystemExit:
            input("\nPress Enter to continue…")
        finally:
            curses.doupdate()

    return wrapper


def _suspend_with_pause(fn):
    """Like _suspend but also prompts 'Press Enter to continue…' after fn returns."""
    import curses

    def wrapper(*args, **kwargs):
        curses.endwin()
        try:
            fn(*args, **kwargs)
            input("\nPress Enter to continue…")
        except SystemExit:
            input("\nPress Enter to continue…")
        finally:
            curses.doupdate()

    return wrapper


def _popup(fn):
    """Return a wrapper that captures stdout/stderr from fn and shows it in a popup overlay.

    Use for commands that only print text (start, stop, create, delete).
    For interactive terminal takeovers (tmux, editor), use _suspend instead.
    Catches SystemExit so a failing command never crashes the TUI.
    """
    import io
    import sys

    def wrapper(*args, **kwargs):
        from .forms import show_output, show_running
        show_running()
        buf = io.StringIO()
        try:
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = buf
            try:
                fn(*args, **kwargs)
            except SystemExit:
                pass
            finally:
                sys.stdout, sys.stderr = old_out, old_err
        except Exception:
            sys.stdout, sys.stderr = old_out, old_err
        import re
        captured = buf.getvalue().strip()
        # Strip ANSI escape sequences so curses doesn't render them literally
        captured = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", captured)
        if captured:
            show_output(captured)

    return wrapper


def _open_nano(path):
    subprocess.run(["nano", str(path)])


# ---------------------------------------------------------------------------
# In-TUI interactive helpers (collect input via overlay forms, no suspension)
# ---------------------------------------------------------------------------

def _add_machine_interactive():
    """Collect machine details via TUI forms and save to config."""
    from .forms import ask, confirm
    from colette_cli.template.registry import scaffold_template_hook_files

    name = ask("Machine name")
    if not name:
        return
    name = name.strip()

    cfg = load_config()
    if name in cfg.get("machines", {}):
        return

    mtype = ask("Type (local/ssh)", default="local") or "local"
    if mtype not in ("local", "ssh"):
        mtype = "local"

    machine: dict = {"type": mtype}

    if mtype == "ssh":
        host = ask("SSH host (user@hostname or alias)")
        if not host:
            return
        machine["host"] = host.strip()
        key = ask("SSH private key path (leave empty for default)") or ""
        if key:
            machine["ssh_key"] = str(Path(key.strip()).expanduser())

    template_name = ask("Initial template name (leave empty to skip)") or ""
    if template_name:
        ttype = ask("Template type (directory/git)", default="directory") or "directory"
        if ttype not in ("directory", "git"):
            ttype = "directory"
        source_label = "Template path" if ttype == "directory" else "Template git URL"
        source = ask(source_label)
        if not source:
            return
        entry: dict = {"name": template_name, "type": ttype}
        if ttype == "directory":
            entry["path"] = source
        else:
            entry["url"] = source
        machine["templates"] = [entry]

    projects_dir = ask("Projects directory (on the target machine)")
    if not projects_dir:
        return
    machine["projects_dir"] = projects_dir.strip()

    cfg.setdefault("machines", {})[name] = machine
    if not cfg.get("default_machine"):
        cfg["default_machine"] = name
    elif confirm(f"Set '{name}' as the default machine?", default=False):
        cfg["default_machine"] = name

    save_config(cfg)
    if template_name:
        templates_cfg = load_templates()
        upsert_template_metadata(templates_cfg, template_name)
        save_templates(templates_cfg)
        scaffold_template_hook_files(template_name)


def _edit_machine_interactive(machine_name):
    """Edit machine fields via TUI forms and save to config."""
    from .forms import ask

    cfg = load_config()
    machine = cfg.get("machines", {}).get(machine_name)
    if not machine:
        return

    cur_type = machine.get("type", "local")
    mtype = ask("Type (local/ssh)", default=cur_type)
    if mtype is None:
        return
    mtype = mtype or cur_type
    if mtype not in ("local", "ssh"):
        mtype = cur_type
    machine["type"] = mtype

    if mtype == "ssh":
        cur_host = machine.get("host", "")
        host = ask("SSH host", default=cur_host)
        if host is None:
            return
        machine["host"] = host or cur_host
        cur_key = machine.get("ssh_key", "")
        key = ask("SSH key path (leave empty to keep current)", default=cur_key)
        if key is None:
            return
        if key:
            machine["ssh_key"] = str(Path(key.strip()).expanduser())
    else:
        machine.pop("host", None)
        machine.pop("ssh_key", None)

    cur_pdir = machine.get("projects_dir", "")
    pdir = ask("Projects directory", default=cur_pdir)
    if pdir is None:
        return
    machine["projects_dir"] = pdir or cur_pdir

    save_config(cfg)


def _remove_machine_interactive(machine_name):
    """Confirm removal via TUI form and delete machine from config."""
    from .forms import confirm

    if not confirm(f"Remove machine '{machine_name}'?", default=False):
        return

    cfg = load_config()
    if machine_name not in cfg.get("machines", {}):
        return
    del cfg["machines"][machine_name]
    if cfg.get("default_machine") == machine_name:
        cfg["default_machine"] = next(iter(cfg.get("machines", {})), None)
    save_config(cfg)


def _add_template_interactive(machine_name):
    """Collect template details via TUI forms and add to machine config."""
    from .forms import ask
    from colette_cli.template.registry import scaffold_template_hook_files

    name = ask("Template name")
    if not name:
        return
    name = name.strip()

    cfg = load_config()
    machine = cfg.get("machines", {}).get(machine_name)
    if not machine:
        return
    if name in list_machine_template_names(machine):
        return

    ttype = ask("Template type (directory/git)", default="directory") or "directory"
    if ttype not in ("directory", "git"):
        ttype = "directory"
    source_label = "Template path" if ttype == "directory" else "Template git URL"
    source = ask(source_label)
    if not source:
        return

    description = ask("Description (optional)") or None

    entry: dict = {"name": name, "type": ttype}
    if ttype == "directory":
        entry["path"] = source
    else:
        entry["url"] = source

    machine_templates = normalize_machine_templates(machine)
    machine_templates.append(entry)
    machine["templates"] = machine_templates
    save_config(cfg)

    templates_cfg = load_templates()
    upsert_template_metadata(templates_cfg, name, description)
    save_templates(templates_cfg)
    scaffold_template_hook_files(name)


def _edit_template_interactive(machine_name, template_name):
    """Edit template source and description via TUI forms."""
    from .forms import ask
    from colette_cli.template.registry import scaffold_template_hook_files

    cfg = load_config()
    machine = cfg.get("machines", {}).get(machine_name)
    if not machine:
        return

    machine_templates = normalize_machine_templates(machine)
    template = next((t for t in machine_templates if t["name"] == template_name), None)
    if not template:
        return

    current_type = template.get("type", "directory")
    ttype = ask("Template type (directory/git)", default=current_type)
    if ttype is None:
        return
    ttype = ttype or current_type
    if ttype not in ("directory", "git"):
        ttype = current_type

    current_source = template.get("path") or template.get("url", "")
    source_label = "Template path" if ttype == "directory" else "Template git URL"
    source = ask(source_label, default=current_source)
    if source is None:
        return
    source = source or current_source

    templates_cfg = load_templates()
    metadata = next(
        (t for t in templates_cfg.get("templates", []) if t.get("name") == template_name),
        {},
    )
    cur_desc = metadata.get("description", "")
    description = ask("Description", default=cur_desc)
    if description is None:
        return
    description = description or cur_desc or None

    template.clear()
    template.update({"name": template_name, "type": ttype})
    if ttype == "directory":
        template["path"] = source
    else:
        template["url"] = source
    machine["templates"] = machine_templates
    save_config(cfg)

    upsert_template_metadata(templates_cfg, template_name, description, metadata.get("params"))
    save_templates(templates_cfg)
    scaffold_template_hook_files(template_name)


def _remove_template_interactive(machine_name, template_name):
    """Confirm removal via TUI form and remove template from machine config."""
    from .forms import confirm
    from colette_cli.config import cmd_config_remove_template

    if not confirm(f"Remove template '{template_name}' from '{machine_name}'?", default=False):
        return
    cmd_config_remove_template(Namespace(machine_name=machine_name, template_name=template_name))


def _unlink_interactive(name, project):
    """Confirm unlink via TUI form and remove project from config."""
    from .forms import confirm

    if not confirm(
        f"Unlink '{name}' from '{project['machine']}'? Files will NOT be deleted.",
        default=False,
    ):
        return
    save_projects([p for p in load_projects() if p["name"] != name])


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def main_menu_items():
    def _run_monitor(copilot=False, all=False):
        from colette_cli.session import cmd_monitor
        cmd_monitor(Namespace(machine=None, projects=[], copilot=copilot, all=all))

    def _monitor_items():
        return [
            MenuItem("Standard", action=_suspend(lambda: _run_monitor())),
            MenuItem("Copilot", action=_suspend(lambda: _run_monitor(copilot=True))),
            MenuItem("All", action=_suspend(lambda: _run_monitor(all=True))),
        ]

    return [
        MenuItem("Projects", children=project_list_items),
        MenuItem("Templates", children=template_list_items),
        MenuItem("Config", children=config_menu_items),
        MenuItem("Debug", children=debug_menu_items),
        MenuItem("Monitor", children=_monitor_items),
    ]


# ---------------------------------------------------------------------------
# Project screens
# ---------------------------------------------------------------------------

def _create_project_interactive():
    """Collect project details via TUI forms and create the project async."""
    from .forms import ask
    cfg = load_config()
    machines = list(cfg.get("machines", {}).keys())
    default_machine = cfg.get("default_machine") or (machines[0] if machines else "")

    name = ask("Project name")
    if not name:
        return

    machine = ask(f"Machine", default=default_machine) or default_machine
    template = ask("Template (leave empty for none)") or None

    from colette_cli.project import cmd_create
    args = Namespace(name=name, machine=machine, template=template)
    _popup(cmd_create)(args)


def _link_directory_interactive():
    """Collect link details via TUI forms and call cmd_link."""
    from colette_cli.project import cmd_link
    from .forms import ask
    cfg = load_config()
    default_machine = cfg.get("default_machine", "")

    path = ask("Directory path")
    if not path:
        return

    machine = ask("Machine", default=default_machine) or default_machine
    name = ask("Project name (leave empty for directory name)") or None

    cmd_link(Namespace(path=path, machine=machine, name=name))


def project_list_items():
    projects = load_projects()
    cfg = load_config()
    default = cfg.get("default_machine", "")

    def _start_all():
        from colette_cli.session import cmd_start
        _popup(cmd_start)(Namespace(machine=None, projects=[]))

    def _stop_all():
        from colette_cli.session import cmd_stop
        _popup(cmd_stop)(Namespace(machine=None, projects=[]))

    items = []

    # ── Projects grouped under machine section titles ────────────────────────
    if not projects:
        items.append(MenuItem("(no projects)", action=lambda: None))
    else:
        by_machine = {}
        for p in projects:
            by_machine.setdefault(p["machine"], []).append(p)

        def _machine_label(name):
            return f"── {name}" + (" (default)" if name == default else "") + " ──"

        for machine_name in sorted(by_machine, key=lambda m: (m != default, m)):
            items.append(MenuItem(_machine_label(machine_name), selectable=False))
            for project in sorted(by_machine[machine_name], key=lambda p: p["name"]):
                tmpl = project.get("template") or "—"
                items.append(MenuItem(
                    project["name"],
                    detail=tmpl,
                    children=lambda p=project: project_action_items(p),
                ))

            def _start_machine(mn=machine_name):
                from colette_cli.session import cmd_start
                _popup(cmd_start)(Namespace(machine=mn, projects=[]))

            def _stop_machine(mn=machine_name):
                from colette_cli.session import cmd_stop
                _popup(cmd_stop)(Namespace(machine=mn, projects=[]))

            items.append(MenuItem(f"Start All — {machine_name}", action=_start_machine))
            items.append(MenuItem(f"Stop All — {machine_name}", action=_stop_machine))

    # ── Separator ────────────────────────────────────────────────────────────
    items.append(MenuItem("─" * 30, selectable=False))

    # ── Global actions ───────────────────────────────────────────────────────
    items.append(MenuItem("Start All", action=_start_all))
    items.append(MenuItem("Stop All", action=_stop_all))

    # ── Project management ───────────────────────────────────────────────────
    items.append(MenuItem("Create project", action=_create_project_interactive))
    items.append(MenuItem("Link project", action=_link_directory_interactive))

    return items


def project_action_items(project):
    from colette_cli.project import cmd_delete

    name = project["name"]
    cfg = load_config()
    machine = cfg.get("machines", {}).get(project["machine"], {})
    is_remote = machine.get("type") == "ssh"

    def _open_session():
        if is_remote:
            from colette_cli.utils.ssh import ssh_interactive
            template_name = get_project_template_name(project)
            template_metadata = get_template_metadata(load_templates(), template_name)
            startup_command = build_project_bootstrap(
                project, project["machine"], template_metadata
            )
            tmux_cmd = (
                f"tmux new-session -A -s {shlex.quote(name)} "
                f"-c {shlex.quote(project['path'])} "
                f"bash -lc {shlex.quote(startup_command)}"
            )
            ssh_interactive(machine, tmux_cmd)
        else:
            template_name = get_project_template_name(project)
            template_metadata = get_template_metadata(load_templates(), template_name)
            startup_command = build_project_bootstrap(
                project, project["machine"], template_metadata
            )
            project_path = str(Path(project["path"]).expanduser())
            local_tmux_session(name, project_path, startup_command)

    def _start():
        from colette_cli.session import cmd_start
        _popup(cmd_start)(Namespace(machine=None, projects=[name]))

    def _stop():
        from colette_cli.session import cmd_stop
        _popup(cmd_stop)(Namespace(machine=None, projects=[name]))

    def _open_code():
        if is_remote:
            host = machine.get("host", "")
            uri = f"vscode-remote://ssh-remote+{host}{project['path']}"
            subprocess.Popen(["code", "--folder-uri", uri])
        else:
            subprocess.Popen(["code", str(Path(project["path"]).expanduser())])

    def _open_copilot():
        from colette_cli.project.commands import _open_copilot_session
        project_path = project["path"] if is_remote else str(Path(project["path"]).expanduser())
        _open_copilot_session(name, project_path, machine=machine, is_remote=is_remote)

    def _open_logs():
        from colette_cli.session import cmd_logs
        cmd_logs(Namespace(name=name, machine=None))

    def _monitor_all():
        from colette_cli.session import cmd_monitor
        cmd_monitor(Namespace(machine=None, projects=[name], copilot=False, all=True))

    def _delete():
        from .forms import type_to_confirm
        if not type_to_confirm(
            f"Delete '{name}' on '{project['machine']}'?",
            expected=name,
        ):
            return
        _popup(lambda: cmd_delete(Namespace(name=name), skip_confirmation=True))()

    return [
        MenuItem("Open session", action=_suspend(_open_session)),
        MenuItem("Code", action=_open_code),
        MenuItem("Copilot", action=_suspend(_open_copilot)),
        MenuItem("Logs", action=_suspend(_open_logs)),
        MenuItem("Monitor", action=_suspend(_monitor_all)),
        MenuItem("Start", action=_start),
        MenuItem("Stop", action=_stop),
        MenuItem("Edit hooks", children=lambda: project_hook_items(project)),
        MenuItem("Unlink", action=lambda: _unlink_interactive(name, project)),
        MenuItem("Delete", action=_delete),
    ]


def project_hook_items(project):
    scaffold_project_hook_files(project["name"])
    items = []
    for hook_name in SCRIPT_KEYS:
        hook_path = get_project_hook_path(project["name"], hook_name)
        items.append(MenuItem(
            hook_name,
            detail=str(hook_path),
            action=_suspend(lambda p=hook_path: _open_nano(p)),
        ))
    return items


# ---------------------------------------------------------------------------
# Template screens
# ---------------------------------------------------------------------------

def template_list_items():
    cfg = load_config()
    templates_cfg = load_templates()
    seen = set()
    items = []

    for machine_name, machine in sorted(cfg.get("machines", {}).items()):
        for tmpl_name in list_machine_template_names(machine):
            if tmpl_name in seen:
                continue
            seen.add(tmpl_name)
            metadata = get_template_metadata(templates_cfg, tmpl_name)
            desc = (metadata or {}).get("description", "")
            items.append(MenuItem(
                tmpl_name,
                detail=desc,
                children=lambda t=tmpl_name: template_action_items(t),
            ))

    if not items:
        return [MenuItem("(no templates)", action=lambda: None)]
    return items


def template_action_items(template_name):
    def _create_project():
        from .forms import ask
        name = ask(f"New project name for '{template_name}'")
        if not name:
            return
        cfg = load_config()
        args = Namespace(
            name=name,
            machine=cfg.get("default_machine"),
            template=template_name,
        )
        from colette_cli.project import cmd_create
        _popup(cmd_create)(args)

    return [
        MenuItem("Create project", action=_create_project),
        MenuItem("Edit hooks", children=lambda: template_hook_items(template_name)),
        MenuItem("Edit parameters", children=lambda: template_param_items(template_name)),
    ]



def template_hook_items(template_name):
    from colette_cli.template.registry import scaffold_template_hook_files
    scaffold_template_hook_files(template_name)
    items = []
    for hook_name in SCRIPT_KEYS:
        hook_path = get_template_hook_path(template_name, hook_name)
        items.append(MenuItem(
            hook_name,
            detail=str(hook_path),
            action=_suspend(lambda p=hook_path: _open_nano(p)),
        ))
    return items


def template_param_items(template_name):
    """Screen for viewing and editing a template's custom parameters."""
    def _reload_metadata():
        return (get_template_metadata(load_templates(), template_name) or {}).get("params") or {}

    def _save_params(params):
        templates_cfg = load_templates()
        upsert_template_metadata(templates_cfg, template_name, params=params)
        save_templates(templates_cfg)

    def _add_param():
        from .forms import ask
        key = ask("Parameter name (e.g. PORT)")
        if not key:
            return
        key = key.strip().upper()
        if not key:
            return
        value = ask(f"Value for {key}") or ""
        params = _reload_metadata()
        params[key] = value
        _save_params(params)

    items = [MenuItem("Add parameter", action=_add_param)]

    params = _reload_metadata()
    for key, value in sorted(params.items()):
        def _edit(k=key):
            from .forms import ask
            new_val = ask(f"New value for {k}", default=params[k])
            if new_val is None:
                return
            p = _reload_metadata()
            p[k] = new_val
            _save_params(p)

        def _remove(k=key):
            from .forms import confirm
            if not confirm(f"Remove parameter '{k}'?", default=False):
                return
            p = _reload_metadata()
            p.pop(k, None)
            _save_params(p)

        items.append(MenuItem(
            key,
            detail=str(value),
            children=lambda k=key, e=_edit, r=_remove: [
                MenuItem("Edit value", action=e),
                MenuItem("Remove", action=r),
            ],
        ))

    if not params:
        items.append(MenuItem("(no parameters)", action=lambda: None))

    return items


# ---------------------------------------------------------------------------
# Config screens
# ---------------------------------------------------------------------------

def config_menu_items():
    return [
        MenuItem("Machines", children=machine_list_items),
        MenuItem("Projects", children=config_project_list_items),
    ]


def machine_list_items():
    cfg = load_config()
    machines = cfg.get("machines", {})
    default = cfg.get("default_machine", "")

    items = [MenuItem("Add machine", action=_add_machine_interactive)]

    for machine_name in sorted(machines, key=lambda m: (m != default, m)):
        detail = "default" if machine_name == default else machines[machine_name].get("type", "local")
        items.append(MenuItem(
            machine_name,
            detail=detail,
            children=lambda mn=machine_name: machine_action_items(mn),
        ))

    if not machines:
        items.append(MenuItem("(no machines configured)", action=lambda: None))

    return items


def machine_action_items(machine_name):
    from colette_cli.config import cmd_config_set_default

    def _set_default():
        cmd_config_set_default(Namespace(machine_name=machine_name))

    return [
        MenuItem("Edit", action=lambda: _edit_machine_interactive(machine_name)),
        MenuItem("Set as default", action=_set_default),
        MenuItem("Templates", children=lambda: machine_template_items(machine_name)),
        MenuItem("Remove", action=lambda: _remove_machine_interactive(machine_name)),
    ]


def machine_template_items(machine_name):
    cfg = load_config()
    machine = cfg.get("machines", {}).get(machine_name, {})
    template_names = list_machine_template_names(machine)

    items = [MenuItem("Add template", action=lambda: _add_template_interactive(machine_name))]

    for tmpl_name in template_names:
        items.append(MenuItem(
            tmpl_name,
            children=lambda tn=tmpl_name: [
                MenuItem("Edit", action=lambda: _edit_template_interactive(machine_name, tn)),
                MenuItem("Edit hooks", children=lambda: template_hook_items(tn)),
                MenuItem("Remove", action=lambda: _remove_template_interactive(machine_name, tn)),
            ],
        ))

    if not template_names:
        items.append(MenuItem("(no templates)", action=lambda: None))

    return items


def config_project_list_items():
    projects = load_projects()
    if not projects:
        return [MenuItem("(no projects)", action=lambda: None)]

    items = []
    for project in sorted(projects, key=lambda p: p["name"]):
        items.append(MenuItem(
            project["name"],
            detail=project.get("template") or "—",
            children=lambda p=project: project_hook_items(p),
        ))
    return items


# ---------------------------------------------------------------------------
# Debug screens
# ---------------------------------------------------------------------------

def hook_log_items():
    """Screen showing persisted hook failure entries."""
    def _clear():
        clear_hook_failures()

    items = [MenuItem("Clear log", action=_clear)]

    failures = load_hook_failures()
    if not failures:
        items.append(MenuItem("(no failures recorded)", action=lambda: None))
        return items

    for entry in reversed(failures):
        ts = entry.get("ts", "?")
        project = entry.get("project", "?")
        hook = entry.get("hook", "?")
        template = entry.get("template") or "—"
        exit_code = entry.get("exit_code", "?")
        output = entry.get("output", "")
        label = f"{project} — {hook}"
        detail = ts
        output_lines = output.splitlines() if output else [f"exit code {exit_code}"]
        items.append(MenuItem(
            label,
            detail=detail,
            children=lambda lines=output_lines, ec=exit_code, tmpl=template: (
                [MenuItem(f"template: {tmpl}  exit: {ec}", selectable=False)]
                + [MenuItem(line, selectable=False) for line in lines]
            ),
        ))

    return items


def debug_menu_items():
    return [
        MenuItem("Hook log", children=hook_log_items),
    ]
