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
    DEFAULT_AGENT_COMMAND,
    DEFAULT_IDE_COMMAND_LOCAL,
    DEFAULT_IDE_COMMAND_REMOTE,
    get_machine_template_hook_path,
    get_project_hook_path,
    load_config,
    load_hook_failures,
    clear_hook_failures,
    load_projects,
    save_config,
    scaffold_project_hook_files,
)
from colette_cli.template import (
    get_project_template_name,
    get_template_metadata,
    list_machine_template_names,
    normalize_machine_templates,
    scaffold_template_hook_files,
)
from colette_cli.utils.helpers import all_template_names, is_remote_machine, resolve_ide_command
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
            except Exception:
                import traceback
                print(traceback.format_exc(), file=sys.stderr)
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
    """Collect machine details via a single multi-field form and save to config."""
    from .forms import form, FormField

    cfg = load_config()
    has_default = bool(cfg.get("default_machine"))

    fields = [
        FormField(
            name="name", label="Machine name",
            validator=lambda s: (True, "") if (
                s.strip() and s.strip() not in cfg.get("machines", {})
                and s.strip() not in all_template_names(cfg)
                and s.strip() not in {p["name"] for p in load_projects()}
            ) else (False, "name required and must not collide with a machine, template, or project name"),
        ),
        FormField(name="type", label="Type", kind="choice", choices=["local", "ssh"], default="local"),
        FormField(
            name="host", label="SSH host (user@hostname or alias)",
            visible_if=lambda v: v["type"] == "ssh",
            validator=lambda s: (True, "") if s.strip() else (False, "SSH host cannot be empty"),
        ),
        FormField(
            name="port", label="SSH port (empty = default 22)",
            visible_if=lambda v: v["type"] == "ssh",
            validator=lambda s: (True, "") if (not s.strip() or s.strip().isdigit())
                else (False, "Port must be a number"),
        ),
        FormField(
            name="ssh_key", label="SSH private key path (empty = default)",
            visible_if=lambda v: v["type"] == "ssh",
        ),
        FormField(
            name="colette_path", label="Path to colette binary (empty = skip auto-sync)",
            visible_if=lambda v: v["type"] == "ssh",
        ),
        FormField(
            name="projects_dir", label="Projects directory (on the target machine)",
            validator=lambda s: (True, "") if s.strip() else (False, "cannot be empty"),
        ),
        FormField(name="add_template", label="Add an initial template?", kind="choice", choices=["no", "yes"], default="no"),
        FormField(name="template_name", label="Template name", visible_if=lambda v: v["add_template"] == "yes"),
        FormField(
            name="template_type", label="Template type", kind="choice",
            choices=["directory", "git"], default="directory",
            visible_if=lambda v: v["add_template"] == "yes",
        ),
        FormField(
            name="template_source",
            label=lambda v: "Template path" if v.get("template_type") == "directory" else "Template git URL",
            visible_if=lambda v: v["add_template"] == "yes",
            validator=lambda s: (True, "") if s.strip() else (False, "cannot be empty"),
        ),
    ]
    if has_default:
        fields.append(FormField(
            name="set_default", label="Set as the default machine?", kind="choice",
            choices=["no", "yes"], default="no",
        ))

    values = form(fields, title="Add machine")
    if values is None:
        return

    name = values["name"].strip()
    machine: dict = {"type": values["type"]}
    if values["type"] == "ssh":
        machine["host"] = values["host"].strip()
        if values["port"].strip():
            machine["port"] = int(values["port"].strip())
        if values["ssh_key"].strip():
            machine["ssh_key"] = str(Path(values["ssh_key"].strip()).expanduser())
        if values["colette_path"].strip():
            machine["colette_path"] = values["colette_path"].strip()
    machine["projects_dir"] = values["projects_dir"].strip()

    template_name = values["template_name"].strip() if values["add_template"] == "yes" else ""
    if template_name:
        ttype = values["template_type"]
        source = values["template_source"].strip()
        entry: dict = {"name": template_name, "type": ttype}
        if ttype == "directory":
            entry["path"] = source
        else:
            entry["url"] = source
        machine["templates"] = [entry]

    cfg.setdefault("machines", {})[name] = machine
    if not has_default:
        cfg["default_machine"] = name
    elif values.get("set_default") == "yes":
        cfg["default_machine"] = name

    save_config(cfg)
    if template_name:
        scaffold_template_hook_files(template_name, name)


def _edit_machine_interactive(machine_name):
    """Edit machine fields via a single multi-field form and save to config."""
    from .forms import form, FormField

    cfg = load_config()
    machine = cfg.get("machines", {}).get(machine_name)
    if not machine:
        return

    cur_type = machine.get("type", "local")
    default_ide = DEFAULT_IDE_COMMAND_REMOTE if cur_type == "ssh" else DEFAULT_IDE_COMMAND_LOCAL

    fields = [
        FormField(name="type", label="Type", kind="choice", choices=["local", "ssh"], default=cur_type),
        FormField(
            name="host", label="SSH host", default=machine.get("host", ""),
            visible_if=lambda v: v["type"] == "ssh",
            validator=lambda s: (True, "") if s.strip() else (False, "SSH host cannot be empty"),
        ),
        FormField(
            name="port", label="SSH port (empty = default 22)",
            default=str(machine.get("port", "")),
            visible_if=lambda v: v["type"] == "ssh",
            validator=lambda s: (True, "") if (not s.strip() or s.strip().isdigit())
                else (False, "Port must be a number"),
        ),
        FormField(
            name="ssh_key", label="SSH key path (empty = none)",
            default=machine.get("ssh_key", ""), visible_if=lambda v: v["type"] == "ssh",
        ),
        FormField(
            name="colette_path", label="Path to colette binary (empty = skip auto-sync)",
            default=machine.get("colette_path", ""), visible_if=lambda v: v["type"] == "ssh",
        ),
        FormField(
            name="projects_dir", label="Projects directory",
            default=machine.get("projects_dir", ""),
            validator=lambda s: (True, "") if s.strip() else (False, "cannot be empty"),
        ),
        FormField(
            name="agent_command", label="Agent command (empty = use default)",
            default=machine.get("agent_command", ""),
            placeholder=f"default: {DEFAULT_AGENT_COMMAND}",
        ),
        FormField(
            name="ide_command", label="IDE command (empty = use default)",
            default=machine.get("ide_command", ""),
            placeholder=f"default: {default_ide}",
        ),
    ]

    values = form(fields, title=f"Edit '{machine_name}'")
    if values is None:
        return

    machine["type"] = values["type"]
    if values["type"] == "ssh":
        machine["host"] = values["host"].strip()
        if values["port"].strip():
            machine["port"] = int(values["port"].strip())
        else:
            machine.pop("port", None)
        if values["ssh_key"].strip():
            machine["ssh_key"] = str(Path(values["ssh_key"].strip()).expanduser())
        else:
            machine.pop("ssh_key", None)
        if values["colette_path"].strip():
            machine["colette_path"] = values["colette_path"].strip()
        else:
            machine.pop("colette_path", None)
    else:
        machine.pop("host", None)
        machine.pop("port", None)
        machine.pop("ssh_key", None)
        machine.pop("colette_path", None)

    machine["projects_dir"] = values["projects_dir"].strip()

    if values["agent_command"].strip():
        machine["agent_command"] = values["agent_command"].strip()
    else:
        machine.pop("agent_command", None)

    if values["ide_command"].strip():
        machine["ide_command"] = values["ide_command"].strip()
    else:
        machine.pop("ide_command", None)

    save_config(cfg)


def _rename_machine_interactive(machine_name):
    """Rename a machine via a single text prompt."""
    from .forms import ask
    new_name = ask(f"New name for machine '{machine_name}'")
    if not new_name or not new_name.strip():
        return
    from colette_cli.config import cmd_config_rename_machine
    _popup(cmd_config_rename_machine)(Namespace(old_name=machine_name, new_name=new_name.strip()))


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


def _sync_all_interactive():
    from colette_cli.config import cmd_config_sync
    _async_popup(lambda: cmd_config_sync(Namespace(machine_name=None)), "Sync all machines")()


def _add_template_interactive(machine_name):
    """Collect template details via a form and add to machine config."""
    from .forms import form, FormField
    from colette_cli.config import apply_add_template

    cfg = load_config()
    machine = cfg.get("machines", {}).get(machine_name)
    if not machine:
        return
    existing_names = set(list_machine_template_names(machine))
    existing_projects = {p["name"] for p in load_projects()}
    existing_machines = set(cfg.get("machines", {}))

    fields = [
        FormField(
            name="name", label="Template name",
            validator=lambda s: (True, "") if (
                s.strip() and s.strip() not in existing_names
                and s.strip() not in existing_projects
                and s.strip() not in existing_machines
            ) else (False, "name required, must be unique on this machine, and not used as a project or machine name"),
        ),
        FormField(name="type", label="Type", kind="choice", choices=["directory", "git"], default="directory"),
        FormField(
            name="source",
            label=lambda v: "Template path" if v.get("type") == "directory" else "Template git URL",
            validator=lambda s: (True, "") if s.strip() else (False, "cannot be empty"),
        ),
        FormField(name="description", label="Description (optional)"),
    ]
    values = form(fields, title="Add template")
    if values is None:
        return

    apply_add_template(
        cfg, machine_name, values["name"].strip(), values["type"],
        values["source"].strip(), values["description"].strip() or None,
    )


def _edit_template_interactive(machine_name, template_name):
    """Edit template source and description via a form."""
    from .forms import form, FormField
    from colette_cli.config import apply_edit_template

    cfg = load_config()
    machine = cfg.get("machines", {}).get(machine_name)
    if not machine:
        return

    machine_templates = normalize_machine_templates(machine)
    template = next((t for t in machine_templates if t["name"] == template_name), None)
    if not template:
        return

    current_type = template.get("type", "directory")
    current_source = template.get("path") or template.get("url", "")
    current_desc = template.get("description") or ""

    fields = [
        FormField(name="type", label="Type", kind="choice", choices=["directory", "git"], default=current_type),
        FormField(
            name="source",
            label=lambda v: "Template path" if v.get("type") == "directory" else "Template git URL",
            default=current_source,
            validator=lambda s: (True, "") if s.strip() else (False, "cannot be empty"),
        ),
        FormField(name="description", label="Description (optional)", default=current_desc),
    ]
    values = form(fields, title=f"Edit '{template_name}'")
    if values is None:
        return

    apply_edit_template(
        cfg, machine_name, template_name, values["type"],
        values["source"].strip(), values["description"].strip() or None,
    )


def _unlink_interactive(name, project):
    """Confirm unlink via TUI form and remove project from config."""
    from .forms import confirm

    if not confirm(
        f"Unlink '{name}' from '{project['machine']}'? Files will NOT be deleted.",
        default=False,
    ):
        return
    from colette_cli.project.commands import cmd_unlink
    _popup(lambda: cmd_unlink(Namespace(name=name), skip_confirmation=True))()


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def main_menu_items():
    def _run_monitor(agent=False, all=False):
        from colette_cli.session import cmd_monitor
        cmd_monitor(Namespace(machine=None, projects=[], agent=agent, all=all))

    def _monitor_items():
        return [
            MenuItem("Standard", action=_suspend(lambda: _run_monitor())),
            MenuItem("Agent", action=_suspend(lambda: _run_monitor(agent=True))),
            MenuItem("All", action=_suspend(lambda: _run_monitor(all=True))),
        ]

    return [
        MenuItem("Projects", children=project_list_items),
        MenuItem("Machines", children=machine_list_items),
        MenuItem("Debug", children=debug_menu_items),
        MenuItem("Monitor", children=_monitor_items),
    ]


# ---------------------------------------------------------------------------
# Project screens
# ---------------------------------------------------------------------------

def _create_project_interactive():
    """Collect project details via a form and create the project async."""
    from .forms import form, FormField
    from colette_cli.template.registry import list_creatable_template_names

    cfg = load_config()
    machines = list(cfg.get("machines", {}).keys())
    default_machine = cfg.get("default_machine") or (machines[0] if machines else "")

    def _template_choices(v):
        machine_name = v.get("machine") or default_machine
        machine_cfg = cfg.get("machines", {}).get(machine_name, {})
        return ["(none)"] + list_creatable_template_names(machine_cfg, machine_name)

    fields = [
        FormField(
            name="name", label="Project name",
            validator=lambda s: (True, "") if (
                s.strip() and s.strip() not in all_template_names(cfg)
                and s.strip() not in cfg.get("machines", {})
            ) else (False, "name required and must not collide with a template or machine name"),
        ),
        FormField(name="machine", label="Machine", kind="choice", choices=machines, default=default_machine),
        FormField(name="template", label="Template", kind="choice", choices=_template_choices, default="(none)"),
    ]
    values = form(fields, title="Create project")
    if values is None:
        return

    name = values["name"].strip()
    template = values["template"] if values["template"] != "(none)" else None

    from colette_cli.project import cmd_create
    args = Namespace(name=name, machine=values["machine"], template=template)
    _async_popup(cmd_create, f"Create {name}")(args)


def _link_directory_interactive():
    """Collect link details via a form and call cmd_link."""
    from colette_cli.project import cmd_link
    from .forms import form, FormField
    cfg = load_config()
    machines = list(cfg.get("machines", {}).keys())
    default_machine = cfg.get("default_machine", "")

    fields = [
        FormField(
            name="path", label="Directory path",
            validator=lambda s: (True, "") if s.strip() else (False, "cannot be empty"),
        ),
        FormField(name="machine", label="Machine", kind="choice", choices=machines, default=default_machine),
        FormField(name="name", label="Project name (empty = directory name)"),
    ]
    values = form(fields, title="Link project")
    if values is None:
        return

    _popup(cmd_link)(Namespace(
        path=values["path"].strip(),
        machine=values["machine"],
        name=values["name"].strip() or None,
    ))


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
                project, project["machine"], template_metadata, is_remote=True, machine=machine
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

    def _open_ide():
        path = project["path"] if is_remote else str(Path(project["path"]).expanduser())
        subprocess.Popen(resolve_ide_command(machine, path))

    def _open_agent():
        from colette_cli.project.commands import _open_agent_session
        project_path = project["path"] if is_remote else str(Path(project["path"]).expanduser())
        _open_agent_session(name, project_path, machine=machine, is_remote=is_remote)

    def _open_logs():
        from colette_cli.session import cmd_logs
        cmd_logs(Namespace(name=name, machine=None))

    def _monitor_all():
        from colette_cli.session import cmd_monitor
        cmd_monitor(Namespace(machine=None, projects=[name], agent=False, all=True))

    def _delete():
        from .forms import confirm, type_to_confirm
        if not type_to_confirm(
            f"Delete '{name}' on '{project['machine']}'?",
            expected=name,
        ):
            return
        if not confirm(f"Will delete: {project['path']}", default=False):
            return
        _async_popup(lambda: cmd_delete(Namespace(name=name), skip_confirmation=True), f"Delete {name}")()

    return [
        MenuItem("Open session", action=_suspend(_open_session)),
        MenuItem("IDE", action=_open_ide),
        MenuItem("Agent", action=_suspend(_open_agent)),
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
# Machine screens (also home to their templates and a project cross-reference)
# ---------------------------------------------------------------------------

def machine_list_items():
    cfg = load_config()
    machines = cfg.get("machines", {})
    default = cfg.get("default_machine", "")

    items = [MenuItem("Add machine", action=_add_machine_interactive)]

    if any(is_remote_machine(m) for m in machines.values()):
        items.append(MenuItem("Sync all", action=_sync_all_interactive))

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
    from colette_cli.config import cmd_config_set_default, cmd_config_sync
    from colette_cli.project import cmd_attach
    from colette_cli.utils.config import load_machine_cache
    _cfg = load_config()
    _machine = _cfg.get("machines", {}).get(machine_name) or {}
    _is_remote = is_remote_machine(_machine)

    def _set_default():
        _popup(cmd_config_set_default)(Namespace(machine_name=machine_name))

    def _sync():
        _async_popup(lambda: cmd_config_sync(Namespace(machine_name=machine_name)), f"Sync {machine_name}")()

    items = []
    if _is_remote:
        cache = load_machine_cache(machine_name)
        ts = cache.get("synced_at") if cache else None
        items.append(MenuItem(f"Last synced: {ts or 'never'}", selectable=False))

    items.append(MenuItem("Terminal", action=_suspend(
        lambda: cmd_attach(Namespace(name=machine_name))
    )))

    items += [
        MenuItem("Edit", action=lambda: _edit_machine_interactive(machine_name)),
        MenuItem("Set as default", action=_set_default),
        MenuItem("Rename", action=lambda: _rename_machine_interactive(machine_name)),
    ]
    if _is_remote:
        items.append(MenuItem("Sync", action=_sync))
    items += [
        MenuItem("Templates", children=lambda: machine_template_items(machine_name)),
        MenuItem("Projects", children=lambda: machine_project_items(machine_name)),
        MenuItem("Remove", action=lambda: _remove_machine_interactive(machine_name)),
    ]
    return items


def machine_project_items(machine_name):
    """This machine's own projects, drilling into the full project action
    set (project_action_items) — not just hooks. Useful e.g. to check/unlink
    a machine's projects before removing it, without leaving this screen."""
    projects = [p for p in load_projects() if p["machine"] == machine_name]
    if not projects:
        return [MenuItem("(no projects)", action=lambda: None)]
    items = []
    for project in sorted(projects, key=lambda p: p["name"]):
        items.append(MenuItem(
            project["name"],
            detail=project.get("template") or "—",
            children=lambda p=project: project_action_items(p),
        ))
    return items


def machine_template_items(machine_name):
    cfg = load_config()
    machine = cfg.get("machines", {}).get(machine_name, {})
    template_names = list_machine_template_names(machine)

    items = [MenuItem("Add template", action=_popup(lambda: _add_template_interactive(machine_name)))]

    for tmpl_name in template_names:
        items.append(MenuItem(
            tmpl_name,
            children=lambda tn=tmpl_name: machine_template_action_items(machine_name, tn),
        ))

    if not template_names:
        items.append(MenuItem("(no templates)", action=lambda: None))

    return items


def machine_template_action_items(machine_name, template_name):
    """Full, unified action set for a machine-scoped template."""
    def _create_project():
        from .forms import ask
        name = ask(f"New project name for '{template_name}'")
        if not name:
            return
        args = Namespace(name=name, machine=machine_name, template=template_name)
        from colette_cli.project import cmd_create
        _async_popup(cmd_create, f"Create {name}")(args)

    def _run_update():
        from colette_cli.template import run_onupdate_for_template, get_template_metadata
        from colette_cli.template.registry import get_creatable_template
        cfg = load_config()
        machine = cfg.get("machines", {}).get(machine_name) or {}
        is_remote = is_remote_machine(machine)
        template_metadata = get_template_metadata(machine, machine_name, template_name)
        template_entry = get_creatable_template(machine, machine_name, template_name)
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

    def _rename():
        from .forms import ask
        from colette_cli.config import cmd_config_rename_template
        new_name = ask(f"New name for template '{template_name}'")
        if not new_name or not new_name.strip():
            return
        _popup(cmd_config_rename_template)(Namespace(
            machine_name=machine_name,
            old_name=template_name,
            new_name=new_name.strip(),
        ))

    def _remove():
        from .forms import confirm
        from colette_cli.config import cmd_config_remove_template
        if not confirm(f"Remove template '{template_name}' from '{machine_name}'?", default=False):
            return
        _popup(cmd_config_remove_template)(Namespace(machine_name=machine_name, template_name=template_name))

    return [
        MenuItem("Create project", action=_create_project),
        MenuItem("Run update", action=_async_popup(_run_update, f"Update template {template_name}")),
        MenuItem("Edit hooks", children=lambda: template_hook_items(template_name, machine_name)),
        MenuItem("Edit parameters", children=lambda: template_param_items(template_name, machine_name)),
        MenuItem("Edit", action=_popup(lambda: _edit_template_interactive(machine_name, template_name))),
        MenuItem("Rename", action=_rename),
        MenuItem("Remove", action=_remove),
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
    from colette_cli.config import cmd_config_set_template_params

    def _reload_metadata():
        from colette_cli.utils.config import get_machine_template_params
        return get_machine_template_params(load_config().get("machines", {}).get(machine_name, {}), template_name)

    def _save_params(params):
        cfg = load_config()
        cmd_config_set_template_params(cfg, machine_name, template_name, params)

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
