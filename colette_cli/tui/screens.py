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
    get_machine_template_hook_path,
    get_project_hook_path,
    load_config,
    load_hook_failures,
    clear_hook_failures,
    load_projects,
    save_config,
    save_projects,
    scaffold_project_hook_files,
)
from colette_cli.template import (
    get_project_template_name,
    get_template_metadata,
    list_machine_template_names,
    normalize_machine_templates,
    scaffold_template_hook_files,
)
from colette_cli.utils.helpers import is_remote_machine
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


def _async_popup(fn, label: str):
    """Return a wrapper that runs fn in a background thread.

    Captures stdout/stderr, appends a Notification to shared state when done,
    and fires a desktop notification. The TUI remains responsive throughout.
    """
    import io
    import re
    import threading
    import traceback
    import sys
    from colette_cli.utils.notify import send_notification
    from . import state

    def wrapper(*args, **kwargs):
        from .forms import show_running
        show_running(f"{label}…")

        def _run():
            with state.running_tasks_lock:
                state.running_tasks += 1
            buf = io.StringIO()
            success = True
            try:
                old_out, old_err = sys.stdout, sys.stderr
                sys.stdout = sys.stderr = buf
                try:
                    fn(*args, **kwargs)
                except SystemExit:
                    success = False
                except Exception:
                    success = False
                    print(traceback.format_exc(), file=sys.stderr)
                finally:
                    sys.stdout, sys.stderr = old_out, old_err
            except Exception:
                sys.stdout, sys.stderr = old_out, old_err
                success = False
            finally:
                with state.running_tasks_lock:
                    state.running_tasks -= 1

            captured = buf.getvalue().strip()
            captured = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", captured)

            notif = state.Notification(
                label=label,
                success=success,
                output=captured,
            )
            with state.notifications_lock:
                state.notifications.append(notif)

            title = f"✓ {label}" if success else f"✗ {label} failed"
            body = "" if success else (captured[:120] if captured else "See notification log")
            send_notification(title, body)

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    return wrapper


def _open_nano(path):
    subprocess.run(["nano", str(path)])


# ---------------------------------------------------------------------------
# Notifications screen
# ---------------------------------------------------------------------------

def notifications_screen_items():
    """Screen listing completed background task notifications."""
    from . import state

    # Mark all current notifications as seen when this screen opens
    with state.notifications_lock:
        for n in state.notifications:
            n.seen = True
        snapshot = list(state.notifications)

    def _clear():
        with state.notifications_lock:
            state.notifications.clear()

    items = [MenuItem("Clear all", action=_clear)]

    if not snapshot:
        items.append(MenuItem("(no notifications)", action=lambda: None))
        return items

    for notif in reversed(snapshot):
        prefix = "✓" if notif.success else "✗"
        label = f"{prefix} {notif.label}"
        detail = notif.timestamp

        if not notif.success and notif.output:
            def _view_output(out=notif.output, lbl=notif.label):
                from .forms import show_output
                show_output(out, title=lbl)
            items.append(MenuItem(label, detail=detail, action=_view_output))
        else:
            items.append(MenuItem(label, detail=detail, action=lambda: None))

    return items


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
        port = ask("SSH port (leave empty for default 22)") or ""
        if port.strip():
            machine["port"] = int(port.strip())
        key = ask("SSH private key path (leave empty for default)") or ""
        if key:
            machine["ssh_key"] = str(Path(key.strip()).expanduser())
        colette_path = ask("Path to colette binary on this machine (leave empty to skip auto-sync)") or ""
        if colette_path:
            machine["colette_path"] = colette_path.strip()

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
        scaffold_template_hook_files(template_name, name)


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
        cur_port = str(machine.get("port", ""))
        port = ask("SSH port (leave empty for default 22)", default=cur_port)
        if port is None:
            return
        if port.strip():
            machine["port"] = int(port.strip())
        elif "port" in machine and not port.strip():
            pass  # keep existing port
        cur_key = machine.get("ssh_key", "")
        key = ask("SSH key path (leave empty to keep current)", default=cur_key)
        if key is None:
            return
        if key:
            machine["ssh_key"] = str(Path(key.strip()).expanduser())
        cur_cp = machine.get("colette_path", "")
        colette_path = ask("Path to colette binary on this machine (leave empty to keep)", default=cur_cp)
        if colette_path is None:
            return
        if colette_path.strip():
            machine["colette_path"] = colette_path.strip()
    else:
        machine.pop("host", None)
        machine.pop("port", None)
        machine.pop("ssh_key", None)
        machine.pop("colette_path", None)

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
    if not source.strip():
        return

    description = ask("Description (optional)") or None

    entry: dict = {"name": name, "type": ttype}
    if ttype == "directory":
        entry["path"] = source
    else:
        entry["url"] = source
    if description:
        entry["description"] = description

    machine_templates = normalize_machine_templates(machine)
    machine_templates.append(entry)
    machine["templates"] = machine_templates
    save_config(cfg)

    scaffold_template_hook_files(name, machine_name)


def _edit_template_interactive(machine_name, template_name):
    """Edit template source and description via TUI forms."""
    from .forms import ask

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
    if not source.strip():
        return

    cur_desc = template.get("description") or ""
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
    if description:
        template["description"] = description
    machine["templates"] = machine_templates
    save_config(cfg)

    scaffold_template_hook_files(template_name, machine_name)


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
    from colette_cli.template.registry import list_machine_template_names
    cfg = load_config()
    machines = list(cfg.get("machines", {}).keys())
    default_machine = cfg.get("default_machine") or (machines[0] if machines else "")

    name = ask("Project name")
    if not name:
        return

    machine = ask("Machine", default=default_machine, choices=machines or None) or default_machine

    # Load templates available for the selected machine
    machine_cfg = cfg.get("machines", {}).get(machine, {})
    template_names = list_machine_template_names(machine_cfg)
    template_choices = ["(none)"] + template_names
    raw_template = ask("Template", choices=template_choices)
    template = raw_template if raw_template and raw_template != "(none)" else None

    from colette_cli.project import cmd_create
    args = Namespace(name=name, machine=machine, template=template)
    _async_popup(cmd_create, f"Create {name}")(args)


def _link_directory_interactive():
    """Collect link details via TUI forms and call cmd_link."""
    from colette_cli.project import cmd_link
    from .forms import ask
    cfg = load_config()
    machines = list(cfg.get("machines", {}).keys())
    default_machine = cfg.get("default_machine", "")

    path = ask("Directory path")
    if not path:
        return

    machine = ask("Machine", default=default_machine, choices=machines or None) or default_machine
    name = ask("Project name (leave empty for directory name)") or None

    cmd_link(Namespace(path=path, machine=machine, name=name))


def project_list_items():
    projects = load_projects()
    cfg = load_config()
    default = cfg.get("default_machine", "")

    def _start_all():
        from colette_cli.session import cmd_start
        _async_popup(cmd_start, "Start all")(Namespace(machine=None, projects=[]))

    def _stop_all():
        from colette_cli.session import cmd_stop
        _async_popup(cmd_stop, "Stop all")(Namespace(machine=None, projects=[]))

    def _update_all():
        from colette_cli.session import cmd_update
        _async_popup(cmd_update, "Update all")(Namespace(machine=None, projects=[]))

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
                _async_popup(cmd_start, f"Start {mn}")(Namespace(machine=mn, projects=[]))

            def _stop_machine(mn=machine_name):
                from colette_cli.session import cmd_stop
                _async_popup(cmd_stop, f"Stop {mn}")(Namespace(machine=mn, projects=[]))

            def _update_machine(mn=machine_name):
                from colette_cli.session import cmd_update
                _async_popup(cmd_update, f"Update {mn}")(Namespace(machine=mn, projects=[]))

            items.append(MenuItem(f"Start All — {machine_name}", action=_start_machine))
            items.append(MenuItem(f"Stop All — {machine_name}", action=_stop_machine))
            items.append(MenuItem(f"Update All — {machine_name}", action=_update_machine))

    # ── Separator ────────────────────────────────────────────────────────────
    items.append(MenuItem("─" * 30, selectable=False))

    # ── Global actions ───────────────────────────────────────────────────────
    items.append(MenuItem("Start All", action=_start_all))
    items.append(MenuItem("Stop All", action=_stop_all))
    items.append(MenuItem("Update All", action=_update_all))

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
            template_metadata = get_template_metadata(machine, project["machine"], template_name)
            startup_command = build_project_bootstrap(
                project, project["machine"], template_metadata, is_remote=True
            )
            tmux_cmd = (
                f"tmux new-session -A -s {shlex.quote(name)} "
                f"-c {shlex.quote(project['path'])} "
                f"bash -lc {shlex.quote(startup_command)}"
            )
            ssh_interactive(machine, tmux_cmd)
        else:
            template_name = get_project_template_name(project)
            template_metadata = get_template_metadata(machine, project["machine"], template_name)
            startup_command = build_project_bootstrap(
                project, project["machine"], template_metadata, is_remote=False
            )
            project_path = str(Path(project["path"]).expanduser())
            local_tmux_session(name, project_path, startup_command)

    def _start():
        from colette_cli.session import cmd_start
        _async_popup(cmd_start, f"Start {name}")(Namespace(machine=None, projects=[name]))

    def _stop():
        from colette_cli.session import cmd_stop
        _async_popup(cmd_stop, f"Stop {name}")(Namespace(machine=None, projects=[name]))

    def _update():
        from colette_cli.session import cmd_update
        _async_popup(cmd_update, f"Update {name}")(Namespace(machine=None, projects=[name]))

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
        from .forms import confirm, type_to_confirm
        if not type_to_confirm(
            f"Delete '{name}' on '{project['machine']}'?",
            expected=name,
        ):
            return
        if is_remote:
            if not confirm(f"Will delete: {project['path']}", default=False):
                return
        _async_popup(lambda: cmd_delete(Namespace(name=name), skip_confirmation=True), f"Delete {name}")()

    return [
        MenuItem("Open session", action=_suspend(_open_session)),
        MenuItem("Code", action=_open_code),
        MenuItem("Copilot", action=_suspend(_open_copilot)),
        MenuItem("Logs", action=_suspend(_open_logs)),
        MenuItem("Monitor", action=_suspend(_monitor_all)),
        MenuItem("Start", action=_start),
        MenuItem("Stop", action=_stop),
        MenuItem("Update", action=_update),
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
    default = cfg.get("default_machine")
    items = []

    by_machine = {}
    for machine_name, machine in cfg.get("machines", {}).items():
        tmpl_names = list_machine_template_names(machine)
        if tmpl_names:
            by_machine[machine_name] = (machine_name, machine)

    if not by_machine:
        return [MenuItem("(no templates)", action=lambda: None)]

    def _machine_label(name):
        return f"── {name}" + (" (default)" if name == default else "") + " ──"

    for machine_name in sorted(by_machine, key=lambda m: (m != default, m)):
        _, machine = by_machine[machine_name]
        items.append(MenuItem(_machine_label(machine_name), selectable=False))
        for tmpl in sorted(normalize_machine_templates(machine), key=lambda t: t["name"]):
            tmpl_name = tmpl["name"]
            source = tmpl.get("path") or tmpl.get("url") or ""
            items.append(MenuItem(
                tmpl_name,
                detail=source,
                children=lambda t=tmpl_name, mn=machine_name: template_action_items(t, mn),
            ))

    return items


def template_action_items(template_name, machine_name):
    def _create_project():
        from .forms import ask
        name = ask(f"New project name for '{template_name}'")
        if not name:
            return
        args = Namespace(
            name=name,
            machine=machine_name,
            template=template_name,
        )
        from colette_cli.project import cmd_create
        _async_popup(cmd_create, f"Create {name}")(args)

    def _run_update():
        from colette_cli.template import run_onupdate_for_template, get_template_metadata
        from colette_cli.template.registry import get_machine_template
        from colette_cli.utils.helpers import is_remote_machine
        cfg = load_config()
        machine = cfg.get("machines", {}).get(machine_name) or {}
        is_remote = is_remote_machine(machine)
        template_metadata = get_template_metadata(machine, machine_name, template_name)
        template_entry = get_machine_template(machine, template_name)
        template_path = (template_entry or {}).get("path")
        run_onupdate_for_template(
            template_name,
            machine,
            machine_name,
            is_remote,
            template_metadata,
            template_path=template_path,
            fail_on_error=False,
        )

    def _rename_template():
        from .forms import ask
        new_name = ask(f"New name for template '{template_name}'")
        if not new_name or not new_name.strip():
            return
        from colette_cli.config import cmd_config_rename_template
        cmd_config_rename_template(Namespace(
            machine_name=machine_name,
            old_name=template_name,
            new_name=new_name.strip(),
        ))

    def _change_path():
        from .forms import ask
        cfg = load_config()
        machine = cfg.get("machines", {}).get(machine_name) or {}
        machine_templates = normalize_machine_templates(machine)
        template = next((t for t in machine_templates if t["name"] == template_name), None)
        if not template:
            return
        ttype = template.get("type", "directory")
        current = template.get("path") if ttype == "directory" else template.get("url", "")
        label = "Template path" if ttype == "directory" else "Template git URL"
        new_val = ask(label, default=current or "")
        if not new_val or not new_val.strip():
            return
        if ttype == "directory":
            template["path"] = new_val.strip()
            template.pop("url", None)
        else:
            template["url"] = new_val.strip()
            template.pop("path", None)
        machine["templates"] = machine_templates
        save_config(cfg)

    return [
        MenuItem("Create project", action=_create_project),
        MenuItem("Run update", action=_async_popup(_run_update, f"Update template {template_name}")),
        MenuItem("Edit hooks", children=lambda: template_hook_items(template_name, machine_name)),
        MenuItem("Edit parameters", children=lambda: template_param_items(template_name, machine_name)),
        MenuItem("Rename", action=_rename_template),
        MenuItem("Change path", action=_change_path),
    ]



def template_hook_items(template_name, machine_name):
    scaffold_template_hook_files(template_name, machine_name)
    items = []
    for hook_name in SCRIPT_KEYS:
        hook_path = get_machine_template_hook_path(machine_name, template_name, hook_name)
        items.append(MenuItem(
            hook_name,
            detail=str(hook_path),
            action=_suspend(lambda p=hook_path: _open_nano(p)),
        ))
    return items


def template_param_items(template_name, machine_name):
    """Screen for viewing and editing a template's custom parameters."""
    def _reload_metadata():
        from colette_cli.utils.config import get_machine_template_params
        return get_machine_template_params(load_config().get("machines", {}).get(machine_name, {}), template_name)

    def _save_params(params):
        cfg = load_config()
        machines = cfg.setdefault("machines", {})
        machine = machines.setdefault(machine_name, {})
        templates_list = machine.setdefault("templates", [])
        for entry in templates_list:
            if entry.get("name") == template_name:
                entry["params"] = params
                break
        else:
            templates_list.append({"name": template_name, "params": params})
        save_config(cfg)

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
    _cfg = load_config()
    _machine = _cfg.get("machines", {}).get(machine_name) or {}
    _is_remote = is_remote_machine(_machine)

    def _set_default():
        cmd_config_set_default(Namespace(machine_name=machine_name))

    def _set_colette_path():
        from .forms import ask
        cfg = load_config()
        machine = cfg.get("machines", {}).get(machine_name) or {}
        if not is_remote_machine(machine):
            return
        current = machine.get("colette_path", "")
        new_val = ask("Path to colette binary on this machine (empty to clear)", default=current)
        if new_val is None:
            return
        new_val = new_val.strip()
        if new_val:
            machine["colette_path"] = new_val
        else:
            machine.pop("colette_path", None)
        cfg["machines"][machine_name] = machine
        save_config(cfg)

    def _sync_colette():
        from colette_cli.utils.ssh import sync_remote_colette
        cfg = load_config()
        machine = cfg.get("machines", {}).get(machine_name) or {}
        if not is_remote_machine(machine):
            return
        if not machine.get("colette_path"):
            print(f"No colette_path set for '{machine_name}'. Use 'Set colette path' first.")
            return

        def _do_sync():
            result = sync_remote_colette(machine, machine_name)
            if result is None:
                raise RuntimeError(f"sync failed for '{machine_name}'")
            from colette_cli.utils.ssh import inject_project_config
            from colette_cli.utils.config import load_projects
            for project in [p for p in load_projects() if p.get("machine") == machine_name]:
                inject_project_config(machine, machine_name, project)

        _async_popup(_do_sync, f"Sync colette → {machine_name}")()

    items = [
        MenuItem("Edit", action=lambda: _edit_machine_interactive(machine_name)),
        MenuItem("Set as default", action=_set_default),
    ]
    if _is_remote:
        items += [
            MenuItem("Set colette path", action=_set_colette_path),
            MenuItem("Sync colette", action=_sync_colette),
        ]
    items += [
        MenuItem("Templates", children=lambda: machine_template_items(machine_name)),
        MenuItem("Remove", action=lambda: _remove_machine_interactive(machine_name)),
    ]
    return items


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
                MenuItem("Edit hooks", children=lambda: template_hook_items(tn, machine_name)),
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
