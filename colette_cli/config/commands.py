"""Configuration sub-commands: machine and template management."""

from pathlib import Path

from colette_cli.template import (
    list_machine_template_hook_paths,
    list_machine_template_names,
    normalize_machine_templates,
    scaffold_template_hook_files,
)
from colette_cli.utils.config import (
    get_machine_template_dir,
    get_machine_template_hook_path,
    get_project_hook_path,
    load_config,
    load_projects,
    load_templates,
    rename_machine_template_dir,
    require_machine,
    save_config,
    save_projects,
    scaffold_project_hook_files,
)
from colette_cli.utils.formatting import bold, cyan, err, info
from colette_cli.utils.helpers import all_template_names


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
    print()


def cmd_config_list_templates(args):
    """List templates available for a machine."""
    cfg = load_config()
    machine_name = args.machine_name or cfg.get("default_machine")
    if not machine_name:
        err("no machine specified and no default machine set.")
    machine = require_machine(cfg, machine_name)
    templates = normalize_machine_templates(machine)
    templates_cfg = load_templates()
    if not templates:
        print(f"No templates configured for machine '{machine_name}'.")
        return
    print(f"\n{bold(f'Templates for {machine_name}:')}")
    for template in templates:
        tname = template["name"]
        source = template.get("path") or template.get("url") or "?"
        print(f"  {bold(tname)}  -  {template.get('type', 'directory')}  {source}")
        description = template.get("description")
        if not description:
            legacy = next((t for t in templates_cfg.get("templates", []) if t.get("name") == tname), {})
            description = legacy.get("description")
        if description:
            print(f"    {description}")
        hooks_dir = get_machine_template_dir(machine_name, tname)
        print(f"    hooks_dir: {hooks_dir}")
        scripts = list_machine_template_hook_paths(machine_name, tname)
        if scripts:
            script_names = ", ".join(sorted(scripts))
            print(f"    hook files: {script_names}")
        params = template.get("params")
        if not params:
            legacy = next((t for t in templates_cfg.get("templates", []) if t.get("name") == tname), {})
            params = legacy.get("params")
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


def cmd_config_set_default(args):
    """Set the default machine."""
    cfg = load_config()
    name = args.machine_name
    if name not in cfg.get("machines", {}):
        err(f"machine '{name}' not found.")
    cfg["default_machine"] = name
    save_config(cfg)
    info(f"Default machine set to '{name}'.")


def cmd_config_add_template(args):
    """Add a template source and metadata to a machine."""
    cfg = load_config()
    machine = require_machine(cfg, args.machine_name)
    existing = list_machine_template_names(machine)
    if args.template_name in existing:
        err(
            f"template '{args.template_name}' already exists on machine '{args.machine_name}'."
        )

    projects = load_projects()
    if any(p["name"] == args.template_name for p in projects):
        err(f"'{args.template_name}' is already used as a project name.")

    template_type = _prompt_template_type()
    source = _prompt_template_source(template_type)
    if template_type == "directory" and not source.strip():
        err("template path cannot be empty.")
    if template_type == "git" and not source.strip():
        err("template git URL cannot be empty.")
    description = input("Description (optional): ").strip() or None
    params = _parse_params(getattr(args, "params", None) or [])

    entry = {"name": args.template_name, "type": template_type}
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

    scaffold_template_hook_files(args.template_name, args.machine_name)
    info(f"Hook files: {get_machine_template_dir(args.machine_name, args.template_name)}")
    info(f"Template '{args.template_name}' added to machine '{args.machine_name}'.")


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
    if template_type == "directory" and not source.strip():
        err("template path cannot be empty.")
    if template_type == "git" and not source.strip():
        err("template git URL cannot be empty.")

    cur_desc = template.get("description") or ""
    templates_cfg = load_templates()
    if not cur_desc:
        legacy_meta = next(
            (t for t in templates_cfg.get("templates", []) if t.get("name") == args.template_name),
            {},
        )
        cur_desc = legacy_meta.get("description", "")
    description = input(f"Description [{cur_desc}]: ").strip() or cur_desc or None

    raw_params = getattr(args, "params", None)
    if raw_params is not None:
        params = _parse_params(raw_params)
    else:
        params = template.get("params")
        if not params:
            legacy_meta = next(
                (t for t in templates_cfg.get("templates", []) if t.get("name") == args.template_name),
                {},
            )
            params = legacy_meta.get("params")

    template.clear()
    template.update({"name": args.template_name, "type": template_type})
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

    scaffold_template_hook_files(args.template_name, args.machine_name)
    info(f"Hook files: {get_machine_template_dir(args.machine_name, args.template_name)}")
    info(f"Template '{args.template_name}' updated on machine '{args.machine_name}'.")


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


def cmd_config_edit_project_hook(args):
    """Open a project-specific hook script in nano for editing."""
    import subprocess

    from colette_cli.project import require_project

    project_name = args.project_name
    hook_name = args.hook_name
    require_project(project_name)
    scaffold_project_hook_files(project_name)
    hook_path = get_project_hook_path(project_name, hook_name)
    subprocess.run(["nano", str(hook_path)])


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

    from colette_cli.template.registry import get_machine_template
    template_entry = get_machine_template(machine, template_name)
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

    template["name"] = new_name
    machine["templates"] = machine_templates
    save_config(cfg)

    rename_machine_template_dir(args.machine_name, args.old_name, new_name)

    updated = 0
    for project in projects:
        if project.get("machine") == args.machine_name and project.get("template") == args.old_name:
            project["template"] = new_name
            updated += 1
    if updated:
        save_projects(projects)

    info(f"Template '{args.old_name}' renamed to '{new_name}' on machine '{args.machine_name}'.")
    if updated:
        info(f"Updated {updated} project(s) to use new template name.")


def cmd_config_sync_remote(args):
    """Sync the local colette binary and config to one or all remote machines."""
    from colette_cli.utils.ssh import sync_remote_colette, inject_project_config
    from colette_cli.utils.helpers import is_remote_machine

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

    for name, machine in targets.items():
        if not machine.get("colette_path"):
            print(f"  {name}: no colette_path set, skipping.")
            continue
        synced = sync_remote_colette(machine, name)
        if synced is True:
            info(f"colette synced to '{name}' at {machine['colette_path']}")
        elif synced is False:
            print(f"  {name}: already up to date.")
        if synced is not None:
            machine_projects = [p for p in load_projects() if p.get("machine") == name]
            for project in machine_projects:
                inject_project_config(machine, name, project)
            if machine_projects:
                info(f"Config injected for {len(machine_projects)} project(s) on '{name}'")


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
    elif args.config_cmd == "sync-remote":
        cmd_config_sync_remote(args)
    elif args.config_cmd == "rename-template":
        cmd_config_rename_template(args)
    else:
        args.config_parser.print_help()
