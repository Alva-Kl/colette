"""Configuration sub-commands: machine and template management."""

from pathlib import Path

from colette_cli.template import (
    list_machine_template_hook_paths,
    list_machine_template_names,
    normalize_machine_templates,
    scaffold_template_hook_files,
)
from colette_cli.utils.config import (
    DEFAULT_AGENT_COMMAND,
    DEFAULT_IDE_COMMAND_LOCAL,
    DEFAULT_IDE_COMMAND_REMOTE,
    get_machine,
    get_machine_template_dir,
    get_machine_template_hook_path,
    get_project_hook_path,
    load_config,
    load_projects,
    rename_machine_template_dir,
    require_machine,
    save_config,
    scaffold_project_hook_files,
)
from colette_cli.utils.formatting import bold, cyan, err, info, warn
from colette_cli.utils.helpers import all_template_names, is_remote_machine, write_project_record


def _parse_params(raw_params):
    """Parse a list of 'KEY=VALUE' strings into a dict."""
    params = {}
    for kv in raw_params:
        if "=" not in kv:
            err(f"invalid param format '{kv}', expected KEY=VALUE")
        k, _, v = kv.partition("=")
        params[k.strip()] = v.strip()
    return params


def _prompt_template_type(default=None):
    template_type = input(
        f"Template type (directory/git) [{default or 'directory'}]: "
    ).strip()
    template_type = template_type or default or "directory"
    if template_type not in ("directory", "git"):
        err("template type must be 'directory' or 'git'.")
    return template_type


def _prompt_template_source(template_type, current=None):
    label = "Template path" if template_type == "directory" else "Template git URL"
    suffix = f" [{current}]" if current else ""
    source = input(f"{label}{suffix}: ").strip() or current
    if not source:
        err("template source cannot be empty.")
    return source


def _push_template_if_remote(machine, machine_name, template_name):
    """Push a template's effective hooks to *machine* over SSH if it's remote.

    Called after every local edit to a machine-scoped template hook (add,
    edit, edit-hook) so the remote's own copy never goes stale.
    """
    if not is_remote_machine(machine):
        return
    from colette_cli.utils.ssh import push_template_hooks
    push_template_hooks(machine, machine_name, template_name)


def cmd_config_list(args):
    """List all configured machines."""
    cfg = load_config()
    machines = cfg.get("machines", {})
    if not machines:
        print("No machines configured. Run: colette config add-machine")
        return
    default = cfg.get("default_machine")
    print(f"\n{bold('Configured machines:')}")
    for name, m in sorted(machines.items()):
        tag = f"  {cyan('(default)')}" if name == default else ""
        mtype = m.get("type", "local")
        if mtype == "ssh":
            key_info = f", key={m['ssh_key']}" if "ssh_key" in m else ""
            port_info = f", port={m['port']}" if "port" in m else ""
            print(f"  {bold(name)}{tag}  -  ssh  host={m.get('host', '?')}{port_info}{key_info}")
            cp = m.get("colette_path")
            print(f"    colette_path: {cp if cp else '(not set)'}")
        else:
            print(f"  {bold(name)}{tag}  -  local")
        template_names = list_machine_template_names(m)
        print(
            f"    templates:    {', '.join(template_names) if template_names else 'N/A'}"
        )
        print(f"    projects_dir: {m.get('projects_dir', 'N/A')}")
        default_ide = DEFAULT_IDE_COMMAND_REMOTE if mtype == "ssh" else DEFAULT_IDE_COMMAND_LOCAL
        print(f"    agent_command: {m.get('agent_command') or DEFAULT_AGENT_COMMAND + ' (default)'}")
        print(f"    ide_command:   {m.get('ide_command') or default_ide + ' (default)'}")
    print()


def cmd_config_list_templates(args):
    """List templates available for a machine."""
    cfg = load_config()
    machine_name = args.machine_name or cfg.get("default_machine")
    if not machine_name:
        err("no machine specified and no default machine set.")
    machine = require_machine(cfg, machine_name)
    templates = normalize_machine_templates(machine)
    if not templates:
        print(f"No templates configured for machine '{machine_name}'.")
        return
    print(f"\n{bold(f'Templates for {machine_name}:')}")
    for template in templates:
        tname = template["name"]
        source = template.get("path") or template.get("url") or "?"
        print(f"  {bold(tname)}  -  {template.get('type', 'directory')}  {source}")
        description = template.get("description")
        if description:
            print(f"    {description}")
        hooks_dir = get_machine_template_dir(machine_name, tname)
        print(f"    hooks_dir: {hooks_dir}")
        scripts = list_machine_template_hook_paths(machine_name, tname)
        if scripts:
            script_names = ", ".join(sorted(scripts))
            print(f"    hook files: {script_names}")
        params = template.get("params")
        if params:
            for pk, pv in params.items():
                print(f"    param {pk}: {pv}")
    print()


def cmd_config_add_machine(args):
    """Interactively add a new machine."""
    cfg = load_config()
    name = input("Machine name: ").strip()
    if not name:
        err("machine name cannot be empty.")
    if name in cfg.get("machines", {}):
        err(
            f"machine '{name}' already exists. Use 'colette config edit-machine {name}' to modify."
        )
    if name in all_template_names(cfg):
        err(f"'{name}' is already used as a template name.")
    if any(p["name"] == name for p in load_projects()):
        err(f"'{name}' is already used as a project name.")

    mtype = input("Type (local/ssh) [local]: ").strip() or "local"
    if mtype not in ("local", "ssh"):
        err("type must be 'local' or 'ssh'.")

    machine = {"type": mtype}

    if mtype == "ssh":
        host = input("SSH host (user@hostname or SSH config alias): ").strip()
        if not host:
            err("SSH host cannot be empty.")
        machine["host"] = host
        port = input("SSH port (leave empty for default 22): ").strip()
        if port:
            if not port.isdigit():
                err("SSH port must be a number.")
            machine["port"] = int(port)
        key = input(
            "Path to SSH private key (leave empty to use SSH default): "
        ).strip()
        if key:
            machine["ssh_key"] = str(Path(key).expanduser())
        colette_path = input(
            "Path to colette binary on this machine (leave empty to skip auto-sync): "
        ).strip()
        if colette_path:
            machine["colette_path"] = colette_path

    template = input("Initial template name (optional, leave empty to skip): ").strip()
    if template:
        template_type = _prompt_template_type()
        source = _prompt_template_source(template_type)
        if template_type == "directory":
            machine["templates"] = [
                {"name": template, "type": "directory", "path": source}
            ]
        else:
            machine["templates"] = [{"name": template, "type": "git", "url": source}]

    projects_dir = input("Projects directory (on the target machine): ").strip()
    if not projects_dir:
        err("projects directory cannot be empty.")
    machine["projects_dir"] = projects_dir

    cfg.setdefault("machines", {})[name] = machine

    if not cfg.get("default_machine"):
        cfg["default_machine"] = name
        info(f"Set '{name}' as the default machine.")
    else:
        ans = input(f"Set '{name}' as the default machine? [y/N]: ").strip().lower()
        if ans == "y":
            cfg["default_machine"] = name

    save_config(cfg)
    if template:
        scaffold_template_hook_files(template, name)
    info(f"Machine '{name}' added.")


def cmd_config_edit_machine(args):
    """Edit an existing machine interactively."""
    cfg = load_config()
    name = args.machine_name
    if name not in cfg.get("machines", {}):
        err(f"machine '{name}' not found.")
    machine = cfg["machines"][name]
    print(f"Editing machine '{name}'. Press Enter to keep current value.")

    cur_type = machine.get("type", "local")
    mtype = input(f"Type (local/ssh) [{cur_type}]: ").strip() or cur_type
    machine["type"] = mtype

    if mtype == "ssh":
        cur_host = machine.get("host", "")
        host = input(f"SSH host [{cur_host}]: ").strip() or cur_host
        machine["host"] = host
        cur_port = machine.get("port", "")
        port = input(f"SSH port [{cur_port or 'default 22'}]: ").strip()
        if port:
            if not port.isdigit():
                err("SSH port must be a number.")
            machine["port"] = int(port)
        elif "port" in machine and not port:
            pass  # keep existing port if user presses Enter
        cur_key = machine.get("ssh_key", "")
        key = input(f"SSH key path [{cur_key}] (leave empty to keep): ").strip()
        if key:
            machine["ssh_key"] = str(Path(key).expanduser())
        cur_cp = machine.get("colette_path", "")
        colette_path = input(
            f"Path to colette binary on this machine [{cur_cp}] (leave empty to keep): "
        ).strip()
        if colette_path:
            machine["colette_path"] = colette_path
    else:
        machine.pop("host", None)
        machine.pop("ssh_key", None)
        machine.pop("colette_path", None)

    cur_pdir = machine.get("projects_dir", "")
    pdir = input(f"Projects directory [{cur_pdir}]: ").strip() or cur_pdir
    machine["projects_dir"] = pdir

    cur_agent = machine.get("agent_command", "")
    agent_command = input(
        f"Agent command [{cur_agent or DEFAULT_AGENT_COMMAND + ' (default)'}] (leave empty to keep): "
    ).strip()
    if agent_command:
        machine["agent_command"] = agent_command

    cur_ide = machine.get("ide_command", "")
    default_ide = DEFAULT_IDE_COMMAND_REMOTE if mtype == "ssh" else DEFAULT_IDE_COMMAND_LOCAL
    ide_command = input(
        f"IDE command [{cur_ide or default_ide + ' (default)'}] (leave empty to keep, "
        "supports {host}/{path} placeholders): "
    ).strip()
    if ide_command:
        machine["ide_command"] = ide_command

    save_config(cfg)
    info(f"Machine '{name}' updated.")


def cmd_config_remove_machine(args):
    """Remove a machine from configuration."""
    cfg = load_config()
    name = args.machine_name
    if name not in cfg.get("machines", {}):
        err(f"machine '{name}' not found.")
    ans = input(f"Remove machine '{name}'? [y/N]: ").strip().lower()
    if ans != "y":
        print("Aborted.")
        return
    del cfg["machines"][name]
    if cfg.get("default_machine") == name:
        cfg["default_machine"] = next(iter(cfg.get("machines", {})), None)
    save_config(cfg)
    info(f"Machine '{name}' removed.")


def cmd_config_rename_machine(args):
    """Rename a machine: the config key, its template-hooks directory, its
    remote-cache file (if any), the default_machine pointer, and every
    local project record's "machine" field.

    Mirrors cmd_config_rename_template's approach. Only this machine's own
    local projects.json can ever reference a machine by name (per the
    documented schema, "machine" always names one of this config's own
    type:"local" entries) — a remote connection stub's own projects live on
    that remote, keyed by its own self-name, never by the controller's
    connection name for it, so there is nothing to update there.
    """
    from colette_cli.utils.config import (
        MACHINE_SCRIPTS_DIR,
        get_machine_cache_path,
        load_local_projects,
        save_local_projects,
    )

    cfg = load_config()
    old_name = args.old_name
    new_name = args.new_name
    machine = require_machine(cfg, old_name)
    if new_name in cfg.get("machines", {}):
        err(f"machine '{new_name}' already exists.")
    if new_name in all_template_names(cfg):
        err(f"'{new_name}' is already used as a template name.")
    if any(p["name"] == new_name for p in load_projects()):
        err(f"'{new_name}' is already used as a project name.")

    machines = cfg.setdefault("machines", {})
    del machines[old_name]
    machines[new_name] = machine
    if cfg.get("default_machine") == old_name:
        cfg["default_machine"] = new_name
    save_config(cfg)

    old_dir = MACHINE_SCRIPTS_DIR / old_name
    new_dir = MACHINE_SCRIPTS_DIR / new_name
    if old_dir.exists() and not new_dir.exists():
        old_dir.rename(new_dir)

    old_cache = get_machine_cache_path(old_name)
    new_cache = get_machine_cache_path(new_name)
    if old_cache.exists() and not new_cache.exists():
        old_cache.rename(new_cache)

    projects = load_local_projects()
    updated = 0
    for project in projects:
        if project.get("machine") == old_name:
            project["machine"] = new_name
            updated += 1
    if updated:
        save_local_projects(projects)

    info(f"Machine '{old_name}' renamed to '{new_name}'.")
    if updated:
        info(f"Updated {updated} project(s) to use new machine name.")


def cmd_config_set_default(args):
    """Set the default machine."""
    cfg = load_config()
    name = args.machine_name
    if name not in cfg.get("machines", {}):
        err(f"machine '{name}' not found.")
    cfg["default_machine"] = name
    save_config(cfg)
    info(f"Default machine set to '{name}'.")


def apply_add_template(cfg, machine_name, name, template_type, source, description=None, params=None):
    """Validate and persist a new template on a machine, scaffold its hook
    files, and push to the remote if applicable.

    Shared core for cmd_config_add_template (CLI, collects via input()) and
    the TUI's _add_template_interactive (collects via form()) — kept in one
    place so both stay in sync on validation and remote-push behavior.
    Returns the new template entry dict.
    """
    machine = require_machine(cfg, machine_name)
    existing = list_machine_template_names(machine)
    if name in existing:
        err(f"template '{name}' already exists on machine '{machine_name}'.")

    projects = load_projects()
    if any(p["name"] == name for p in projects):
        err(f"'{name}' is already used as a project name.")

    if name in cfg.get("machines", {}):
        err(f"'{name}' is already used as a machine name.")

    if template_type == "directory" and not (source or "").strip():
        err("template path cannot be empty.")
    if template_type == "git" and not (source or "").strip():
        err("template git URL cannot be empty.")

    entry = {"name": name, "type": template_type}
    if template_type == "directory":
        entry["path"] = source
    else:
        entry["url"] = source
    if description:
        entry["description"] = description
    if params:
        entry["params"] = params

    machine_templates = normalize_machine_templates(machine)
    machine_templates.append(entry)
    machine["templates"] = machine_templates
    save_config(cfg)

    scaffold_template_hook_files(name, machine_name)
    _push_template_if_remote(machine, machine_name, name)
    return entry


def cmd_config_add_template(args):
    """Add a template source and metadata to a machine."""
    cfg = load_config()
    machine = require_machine(cfg, args.machine_name)  # fail before prompting if invalid
    if args.template_name in list_machine_template_names(machine):
        err(f"template '{args.template_name}' already exists on machine '{args.machine_name}'.")
    if any(p["name"] == args.template_name for p in load_projects()):
        err(f"'{args.template_name}' is already used as a project name.")
    if args.template_name in cfg.get("machines", {}):
        err(f"'{args.template_name}' is already used as a machine name.")

    template_type = _prompt_template_type()
    source = _prompt_template_source(template_type)
    description = input("Description (optional): ").strip() or None
    params = _parse_params(getattr(args, "params", None) or [])

    apply_add_template(cfg, args.machine_name, args.template_name, template_type, source, description, params)
    info(f"Hook files: {get_machine_template_dir(args.machine_name, args.template_name)}")
    info(f"Template '{args.template_name}' added to machine '{args.machine_name}'.")


def apply_edit_template(cfg, machine_name, template_name, template_type, source, description=None, params=None):
    """Validate and persist edits to an existing template on a machine,
    re-scaffold its hook files, and push to the remote if applicable.

    Shared core for cmd_config_edit_template (CLI) and the TUI's
    _edit_template_interactive. Returns the updated template entry dict.
    """
    machine = require_machine(cfg, machine_name)
    machine_templates = normalize_machine_templates(machine)
    template = next((item for item in machine_templates if item["name"] == template_name), None)
    if not template:
        err(f"template '{template_name}' not found on machine '{machine_name}'.")

    if template_type == "directory" and not (source or "").strip():
        err("template path cannot be empty.")
    if template_type == "git" and not (source or "").strip():
        err("template git URL cannot be empty.")

    template.clear()
    template.update({"name": template_name, "type": template_type})
    if template_type == "directory":
        template["path"] = source
    else:
        template["url"] = source
    if description:
        template["description"] = description
    if params:
        template["params"] = params
    machine["templates"] = machine_templates
    save_config(cfg)

    scaffold_template_hook_files(template_name, machine_name)
    _push_template_if_remote(machine, machine_name, template_name)
    return template


def cmd_config_edit_template(args):
    """Edit a template source and metadata on a machine."""
    cfg = load_config()
    machine = require_machine(cfg, args.machine_name)
    machine_templates = normalize_machine_templates(machine)
    template = next(
        (item for item in machine_templates if item["name"] == args.template_name), None
    )
    if not template:
        err(
            f"template '{args.template_name}' not found on machine '{args.machine_name}'."
        )

    current_type = template.get("type", "directory")
    template_type = _prompt_template_type(current_type)
    current_source = template.get("path") or template.get("url")
    source = _prompt_template_source(template_type, current_source)

    cur_desc = template.get("description") or ""
    description = input(f"Description [{cur_desc}]: ").strip() or cur_desc or None

    raw_params = getattr(args, "params", None)
    params = _parse_params(raw_params) if raw_params is not None else template.get("params")

    apply_edit_template(cfg, args.machine_name, args.template_name, template_type, source, description, params)
    info(f"Hook files: {get_machine_template_dir(args.machine_name, args.template_name)}")
    info(f"Template '{args.template_name}' updated on machine '{args.machine_name}'.")


def cmd_config_set_template_params(cfg, machine_name, template_name, params):
    """Set a template's custom parameters directly (no interactive I/O) and
    push to the remote if applicable.

    Used by the TUI's template-parameter screen (add/edit/remove a single
    param) so those edits get the same remote-push treatment
    cmd_config_edit_template's --param flag already gets from the CLI —
    previously this screen mutated params with no push at all.
    """
    machine = require_machine(cfg, machine_name)
    machine_templates = normalize_machine_templates(machine)
    template = next((item for item in machine_templates if item["name"] == template_name), None)
    if not template:
        err(f"template '{template_name}' not found on machine '{machine_name}'.")
    if params:
        template["params"] = params
    else:
        template.pop("params", None)
    machine["templates"] = machine_templates
    save_config(cfg)
    _push_template_if_remote(machine, machine_name, template_name)


def cmd_config_edit_hook(args):
    """Open a template hook script in nano for editing."""
    import subprocess

    template_name = args.template_name
    hook_name = args.hook_name
    machine_name = getattr(args, "machine", None)
    if not machine_name:
        cfg = load_config()
        machine_name = cfg.get("default_machine")
    if not machine_name:
        err("--machine is required (or set a default machine with 'colette config set-default').")
    scaffold_template_hook_files(template_name, machine_name)
    hook_path = get_machine_template_hook_path(machine_name, template_name, hook_name)
    subprocess.run(["nano", str(hook_path)])

    machine = get_machine(load_config(), machine_name)
    _push_template_if_remote(machine, machine_name, template_name)


def cmd_config_edit_project_hook(args):
    """Open a project-specific hook script in nano for editing."""
    import subprocess

    from colette_cli.project import require_project

    project_name = args.project_name
    hook_name = args.hook_name
    project = require_project(project_name)
    scaffold_project_hook_files(project_name)
    hook_path = get_project_hook_path(project_name, hook_name)
    subprocess.run(["nano", str(hook_path)])

    machine = get_machine(load_config(), project.get("machine"))
    if is_remote_machine(machine):
        from colette_cli.utils.ssh import push_project_hooks
        push_project_hooks(machine, project["machine"], project_name)


def cmd_config_remove_template(args):
    """Remove a template from a machine."""
    from colette_cli.utils.config import get_machine_template_dir
    import shutil

    cfg = load_config()
    machine = require_machine(cfg, args.machine_name)
    machine_templates = normalize_machine_templates(machine)
    remaining = [
        item for item in machine_templates if item["name"] != args.template_name
    ]
    if len(remaining) == len(machine_templates):
        err(
            f"template '{args.template_name}' not found on machine '{args.machine_name}'."
        )

    machine["templates"] = remaining
    save_config(cfg)

    machine_hooks_dir = get_machine_template_dir(args.machine_name, args.template_name)
    if machine_hooks_dir.exists():
        shutil.rmtree(str(machine_hooks_dir))

    if is_remote_machine(machine):
        from colette_cli.utils.ssh import ssh_run
        ssh_run(machine, f"rm -rf $HOME/.config/colette/templates/{args.template_name}")

    info(f"Template '{args.template_name}' removed from machine '{args.machine_name}'.")


def cmd_config_run_template_update(args):
    """Run the onupdate hook directly for a template (without a project context)."""
    from colette_cli.template import run_onupdate_for_template, get_template_metadata
    from colette_cli.utils.helpers import is_remote_machine

    cfg = load_config()
    machine_name = getattr(args, "machine", None) or cfg.get("default_machine")
    if not machine_name:
        err("no machine specified and no default machine set.")
    machine = require_machine(cfg, machine_name)
    is_remote = is_remote_machine(machine)

    template_name = args.template_name
    template_metadata = get_template_metadata(machine, machine_name, template_name)

    from colette_cli.template.registry import get_creatable_template
    template_entry = get_creatable_template(machine, machine_name, template_name)
    template_path = (template_entry or {}).get("path")

    run_onupdate_for_template(
        template_name,
        machine,
        machine_name,
        is_remote,
        template_metadata,
        template_path=template_path,
        fail_on_error=True,
    )
    info(f"onupdate ran for template '{template_name}'.")


def cmd_config_rename_template(args):
    """Rename a template on a machine."""
    cfg = load_config()
    machine = require_machine(cfg, args.machine_name)
    machine_templates = normalize_machine_templates(machine)
    template = next((t for t in machine_templates if t["name"] == args.old_name), None)
    if not template:
        err(f"template '{args.old_name}' not found on machine '{args.machine_name}'.")
    new_name = args.new_name
    if any(t["name"] == new_name for t in machine_templates):
        err(f"template '{new_name}' already exists on machine '{args.machine_name}'.")

    projects = load_projects()
    if any(p["name"] == new_name for p in projects):
        err(f"'{new_name}' is already used as a project name.")

    if new_name in cfg.get("machines", {}):
        err(f"'{new_name}' is already used as a machine name.")

    template["name"] = new_name
    machine["templates"] = machine_templates
    save_config(cfg)

    rename_machine_template_dir(args.machine_name, args.old_name, new_name)
    if is_remote_machine(machine):
        from colette_cli.utils.ssh import ssh_run
        old_dir = f"$HOME/.config/colette/templates/{args.old_name}"
        new_dir = f"$HOME/.config/colette/templates/{new_name}"
        ssh_run(machine, f"mv {old_dir} {new_dir} 2>/dev/null || true")

    updated = 0
    for project in projects:
        if project.get("machine") == args.machine_name and project.get("template") == args.old_name:
            project["template"] = new_name
            write_project_record(machine, args.machine_name, project)
            updated += 1

    info(f"Template '{args.old_name}' renamed to '{new_name}' on machine '{args.machine_name}'.")
    if updated:
        info(f"Updated {updated} project(s) to use new template name.")


def cmd_config_sync(args):
    """Sync the local colette binary and pull a read-only project/template
    cache from one or all remote machines.

    Never pushes local project/template data outward — each remote machine
    remains authoritative for its own state. This is purely a read-only pull
    into `~/.config/colette/cache/<machine>.json`.
    """
    from datetime import datetime, timezone

    from colette_cli.utils.config import save_machine_cache
    from colette_cli.utils.ssh import fetch_self_report, sync_remote_colette

    cfg = load_config()
    machine_name = getattr(args, "machine_name", None)
    machines = cfg.get("machines", {})

    if machine_name:
        if machine_name not in machines:
            err(f"machine '{machine_name}' not found.")
        targets = {machine_name: machines[machine_name]}
    else:
        targets = {n: m for n, m in machines.items() if is_remote_machine(m)}

    if not targets:
        print("No remote machines configured.")
        return

    failed = []
    for name, machine in targets.items():
        if not machine.get("colette_path"):
            print(f"  {name}: no colette_path set, skipping.")
            continue
        synced = sync_remote_colette(machine, name)
        if synced is True:
            info(f"colette synced to '{name}' at {machine['colette_path']}")
        elif synced is False:
            print(f"  {name}: binary already up to date.")

        report = fetch_self_report(machine, name)
        if report is None:
            warn(f"failed to fetch project/template data from '{name}'.")
            failed.append(name)
            continue

        cache_data = {
            "machine": name,
            "synced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "projects_dir": report.get("machine", {}).get("projects_dir", ""),
            "templates": report.get("machine", {}).get("templates", []),
            "projects": report.get("projects", []),
        }
        save_machine_cache(name, cache_data)
        info(
            f"Cached {len(cache_data['projects'])} project(s) and "
            f"{len(cache_data['templates'])} template(s) from '{name}'."
        )

    if failed:
        err(f"failed to fetch project/template data from: {', '.join(failed)}.")


def cmd_config(args):
    """Dispatcher for config sub-commands."""
    if args.config_cmd == "list":
        cmd_config_list(args)
    elif args.config_cmd == "list-templates":
        cmd_config_list_templates(args)
    elif args.config_cmd == "add-machine":
        cmd_config_add_machine(args)
    elif args.config_cmd == "edit-machine":
        cmd_config_edit_machine(args)
    elif args.config_cmd == "add-template":
        cmd_config_add_template(args)
    elif args.config_cmd == "edit-template":
        cmd_config_edit_template(args)
    elif args.config_cmd == "edit-hook":
        cmd_config_edit_hook(args)
    elif args.config_cmd == "edit-project-hook":
        cmd_config_edit_project_hook(args)
    elif args.config_cmd == "run-template-update":
        cmd_config_run_template_update(args)
    elif args.config_cmd == "remove-template":
        cmd_config_remove_template(args)
    elif args.config_cmd == "remove-machine":
        cmd_config_remove_machine(args)
    elif args.config_cmd == "set-default":
        cmd_config_set_default(args)
    elif args.config_cmd == "sync":
        cmd_config_sync(args)
    elif args.config_cmd == "rename-template":
        cmd_config_rename_template(args)
    elif args.config_cmd == "rename-machine":
        cmd_config_rename_machine(args)
    else:
        args.config_parser.print_help()
