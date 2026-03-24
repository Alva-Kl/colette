"""Configuration sub-commands: machine and template management."""

from pathlib import Path

from colette_cli.template import (
    list_machine_template_names,
    list_template_hook_paths,
    normalize_machine_templates,
    remove_template_metadata,
    scaffold_template_hook_files,
    upsert_template_metadata,
)
from colette_cli.utils.config import (
    get_template_dir,
    get_template_hook_path,
    get_project_hook_path,
    load_config,
    load_templates,
    remove_template_dir,
    require_machine,
    save_config,
    save_templates,
    scaffold_project_hook_files,
)
from colette_cli.utils.formatting import bold, cyan, err, info


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
            print(f"  {bold(name)}{tag}  -  ssh  host={m.get('host', '?')}{key_info}")
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
    metadata_cfg = load_templates()
    if not templates:
        print(f"No templates configured for machine '{machine_name}'.")
        return
    print(f"\n{bold(f'Templates for {machine_name}:')}")
    for template in templates:
        metadata = next(
            (
                item
                for item in metadata_cfg.get("templates", [])
                if item.get("name") == template["name"]
            ),
            {},
        )
        source = template.get("path") or template.get("url") or "?"
        print(
            f"  {bold(template['name'])}  -  {template.get('type', 'directory')}  {source}"
        )
        if metadata.get("description"):
            print(f"    {metadata['description']}")
        print(f"    hooks_dir: {get_template_dir(template['name'])}")
        scripts = list_template_hook_paths(template["name"])
        if scripts:
            script_names = ", ".join(sorted(scripts))
            print(f"    hook files: {script_names}")
        if metadata.get("params"):
            for pk, pv in metadata["params"].items():
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
        key = input(
            "Path to SSH private key (leave empty to use SSH default): "
        ).strip()
        if key:
            machine["ssh_key"] = str(Path(key).expanduser())

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
        templates_cfg = load_templates()
        upsert_template_metadata(templates_cfg, template)
        save_templates(templates_cfg)
        scaffold_template_hook_files(template)
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
        cur_key = machine.get("ssh_key", "")
        key = input(f"SSH key path [{cur_key}] (leave empty to keep): ").strip()
        if key:
            machine["ssh_key"] = str(Path(key).expanduser())
    else:
        machine.pop("host", None)
        machine.pop("ssh_key", None)

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
    templates_cfg = load_templates()
    machine = require_machine(cfg, args.machine_name)
    existing = list_machine_template_names(machine)
    if args.template_name in existing:
        err(
            f"template '{args.template_name}' already exists on machine '{args.machine_name}'."
        )

    template_type = _prompt_template_type()
    source = _prompt_template_source(template_type)
    description = input("Description (optional): ").strip() or None
    params = _parse_params(getattr(args, "params", None) or [])

    entry = {"name": args.template_name, "type": template_type}
    if template_type == "directory":
        entry["path"] = source
    else:
        entry["url"] = source

    machine_templates = normalize_machine_templates(machine)
    machine_templates.append(entry)
    machine["templates"] = machine_templates
    save_config(cfg)

    upsert_template_metadata(
        templates_cfg, args.template_name, description, params or None
    )
    save_templates(templates_cfg)
    scaffold_template_hook_files(args.template_name)
    info(f"Hook files: {get_template_dir(args.template_name)}")
    info(f"Template '{args.template_name}' added to machine '{args.machine_name}'.")


def cmd_config_edit_template(args):
    """Edit a template source and metadata on a machine."""
    cfg = load_config()
    templates_cfg = load_templates()
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
    metadata = next(
        (
            item
            for item in templates_cfg.get("templates", [])
            if item.get("name") == args.template_name
        ),
        {},
    )
    description = input(
        f"Description [{metadata.get('description', '')}]: "
    ).strip() or metadata.get("description")
    raw_params = getattr(args, "params", None)
    if raw_params is not None:
        params = _parse_params(raw_params)
    else:
        params = metadata.get("params")  # keep existing if not overridden

    template.clear()
    template.update({"name": args.template_name, "type": template_type})
    if template_type == "directory":
        template["path"] = source
    else:
        template["url"] = source
    machine["templates"] = machine_templates
    save_config(cfg)

    upsert_template_metadata(templates_cfg, args.template_name, description, params)
    save_templates(templates_cfg)
    scaffold_template_hook_files(args.template_name)
    info(f"Hook files: {get_template_dir(args.template_name)}")
    info(f"Template '{args.template_name}' updated on machine '{args.machine_name}'.")


def cmd_config_edit_hook(args):
    """Open a template hook script in nano for editing."""
    import subprocess

    template_name = args.template_name
    hook_name = args.hook_name
    scaffold_template_hook_files(template_name)
    hook_path = get_template_hook_path(template_name, hook_name)
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
    """Remove a template from a machine and drop unused metadata."""
    cfg = load_config()
    templates_cfg = load_templates()
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

    still_used = False
    for other_machine in cfg.get("machines", {}).values():
        if args.template_name in list_machine_template_names(other_machine):
            still_used = True
            break
    if not still_used:
        remove_template_metadata(templates_cfg, args.template_name)
        save_templates(templates_cfg)
        remove_template_dir(args.template_name)

    info(f"Template '{args.template_name}' removed from machine '{args.machine_name}'.")


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
    elif args.config_cmd == "remove-template":
        cmd_config_remove_template(args)
    elif args.config_cmd == "remove-machine":
        cmd_config_remove_machine(args)
    elif args.config_cmd == "set-default":
        cmd_config_set_default(args)
    else:
        args.config_parser.print_help()
