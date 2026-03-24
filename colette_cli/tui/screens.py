"""Screen builders for the Colette TUI.

Each public function returns a list[MenuItem] for a particular screen.
Actions that need to leave curses (open nano, launch tmux) are wrapped so
curses is suspended/resumed around them.  Actions that only need text input
use in-TUI overlay forms from ``tui.forms`` instead.
"""

import shlex
import subprocess
import threading
from pathlib import Path

from argparse import Namespace

from colette_cli.template import SCRIPT_KEYS
from colette_cli.utils.config import (
    get_template_hook_path,
    get_project_hook_path,
    load_config,
    load_projects,
    load_templates,
    scaffold_project_hook_files,
)
from colette_cli.template import (
    get_project_template_name,
    get_template_metadata,
    list_machine_template_names,
    normalize_machine_templates,
)
from colette_cli.utils.tmux import local_tmux_session
from colette_cli.template import build_project_bootstrap
from colette_cli.utils.notify import send_notification
from . import state as _state

from .menu import MenuItem


def _suspend(fn):
    """Return a wrapper that suspends curses, runs fn, then resumes."""
    import curses

    def wrapper(*args, **kwargs):
        curses.endwin()
        try:
            fn(*args, **kwargs)
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
        finally:
            curses.doupdate()

    return wrapper


def _open_nano(path):
    subprocess.run(["nano", str(path)])


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def main_menu_items():
    def _run_monitor():
        from colette_cli.session import cmd_monitor
        cmd_monitor(Namespace(machine=None, projects=[]))

    return [
        MenuItem("Projects", children=project_list_items),
        MenuItem("Templates", children=template_list_items),
        MenuItem("Config", children=config_menu_items),
        MenuItem("Monitor", action=_suspend(_run_monitor)),
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

    args = Namespace(name=name, machine=machine, template=template)
    _run_create_async(args)


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


def _run_create_async(args: Namespace) -> None:
    """Launch cmd_create in a background thread and notify on completion."""
    from colette_cli.project import cmd_create
    label = f"Creating '{args.name}'"
    _state.add_job(label)

    def _worker():
        try:
            cmd_create(args)
            send_notification("Colette", f"Project '{args.name}' created.")
        except SystemExit:
            send_notification("Colette", f"Failed to create '{args.name}'.")
        except Exception as exc:
            send_notification("Colette", f"Failed to create '{args.name}': {exc}")
        finally:
            _state.remove_job(label)

    threading.Thread(target=_worker, daemon=True).start()


def project_list_items():
    from colette_cli.session import cmd_start, cmd_stop

    projects = load_projects()
    cfg = load_config()
    default = cfg.get("default_machine", "")

    def _start_all():
        cmd_start(Namespace(machine=None, projects=[]))

    def _stop_all():
        cmd_stop(Namespace(machine=None, projects=[]))

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
                cmd_start(Namespace(machine=mn, projects=[]))

            def _stop_machine(mn=machine_name):
                cmd_stop(Namespace(machine=mn, projects=[]))

            items.append(MenuItem(f"Start All — {machine_name}", action=_suspend_with_pause(_start_machine)))
            items.append(MenuItem(f"Stop All — {machine_name}", action=_suspend_with_pause(_stop_machine)))

    # ── Separator ────────────────────────────────────────────────────────────
    items.append(MenuItem("─" * 30, selectable=False))

    # ── Global actions ───────────────────────────────────────────────────────
    items.append(MenuItem("Start All", action=_suspend_with_pause(_start_all)))
    items.append(MenuItem("Stop All", action=_suspend_with_pause(_stop_all)))

    # ── Project management ───────────────────────────────────────────────────
    items.append(MenuItem("Create project", action=_create_project_interactive))
    items.append(MenuItem("Link project", action=_link_directory_interactive))

    return items


def project_action_items(project):
    from colette_cli.session import cmd_start, cmd_stop
    from colette_cli.project import cmd_delete, cmd_unlink

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
        cmd_start(Namespace(machine=None, projects=[name]))

    def _stop():
        cmd_stop(Namespace(machine=None, projects=[name]))

    def _open_code():
        if is_remote:
            host = machine.get("host", "")
            uri = f"vscode-remote://ssh-remote+{host}{project['path']}"
            subprocess.run(["code", "--folder-uri", uri])
        else:
            subprocess.run(["code", str(Path(project["path"]).expanduser())])

    def _open_logs():
        from colette_cli.session import cmd_logs
        cmd_logs(Namespace(name=name, machine=None))

    def _delete():
        from .forms import type_to_confirm
        if not type_to_confirm(
            f"Delete '{name}' on '{project['machine']}'?",
            expected=name,
        ):
            return
        label = f"Deleting '{name}'"
        _state.add_job(label)

        def _worker():
            try:
                cmd_delete(Namespace(name=name), skip_confirmation=True)
                send_notification("Colette", f"Project '{name}' deleted.")
            except SystemExit:
                send_notification("Colette", f"Failed to delete '{name}'.")
            except Exception as exc:
                send_notification("Colette", f"Failed to delete '{name}': {exc}")
            finally:
                _state.remove_job(label)

        threading.Thread(target=_worker, daemon=True).start()

    def _unlink():
        cmd_unlink(Namespace(name=name))

    return [
        MenuItem("Open session", action=_suspend(_open_session)),
        MenuItem("Code", action=_suspend(_open_code)),
        MenuItem("Logs", action=_suspend(_open_logs)),
        MenuItem("Start", action=_suspend_with_pause(_start)),
        MenuItem("Stop", action=_suspend_with_pause(_stop)),
        MenuItem("Edit hooks", children=lambda: project_hook_items(project)),
        MenuItem("Unlink", action=_suspend_with_pause(_unlink)),
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
        _run_create_async(args)

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
    from colette_cli.template import upsert_template_metadata
    from colette_cli.utils.config import save_templates

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
    from colette_cli.config import (
        cmd_config_add_machine,
        cmd_config_edit_machine,
        cmd_config_remove_machine,
        cmd_config_set_default,
    )

    cfg = load_config()
    machines = cfg.get("machines", {})
    default = cfg.get("default_machine", "")

    items = [MenuItem("Add machine", action=_suspend(lambda: cmd_config_add_machine(Namespace())))]

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
    from colette_cli.config import (
        cmd_config_edit_machine,
        cmd_config_remove_machine,
        cmd_config_set_default,
    )

    def _edit():
        cmd_config_edit_machine(Namespace(machine_name=machine_name))

    def _set_default():
        cmd_config_set_default(Namespace(machine_name=machine_name))

    def _remove():
        cmd_config_remove_machine(Namespace(machine_name=machine_name))

    return [
        MenuItem("Edit", action=_suspend_with_pause(_edit)),
        MenuItem("Set as default", action=_suspend_with_pause(_set_default)),
        MenuItem("Templates", children=lambda: machine_template_items(machine_name)),
        MenuItem("Remove", action=_suspend_with_pause(_remove)),
    ]


def machine_template_items(machine_name):
    from colette_cli.config import (
        cmd_config_add_template,
        cmd_config_edit_template,
        cmd_config_remove_template,
    )

    cfg = load_config()
    machine = cfg.get("machines", {}).get(machine_name, {})
    template_names = list_machine_template_names(machine)

    def _add():
        from .forms import ask
        name = ask(f"Template name to add to '{machine_name}'")
        if not name:
            return
        cmd_config_add_template(Namespace(machine_name=machine_name, template_name=name, params=[]))

    items = [MenuItem("Add template", action=_add)]

    for tmpl_name in template_names:
        def _edit(tn=tmpl_name):
            cmd_config_edit_template(Namespace(machine_name=machine_name, template_name=tn, params=None))

        def _remove(tn=tmpl_name):
            cmd_config_remove_template(Namespace(machine_name=machine_name, template_name=tn))

        items.append(MenuItem(
            tmpl_name,
            children=lambda tn=tmpl_name, e=_edit, r=_remove: [
                MenuItem("Edit", action=_suspend_with_pause(e)),
                MenuItem("Edit hooks", children=lambda: template_hook_items(tn)),
                MenuItem("Remove", action=_suspend_with_pause(r)),
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
