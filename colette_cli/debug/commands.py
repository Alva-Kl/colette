"""Debug sub-commands."""

import json

from colette_cli.utils.config import clear_hook_failures, load_config, load_hook_failures, load_local_projects
from colette_cli.utils.formatting import bold, cyan, dim, err


def cmd_debug_hook_log(args):
    """Display persisted hook failure entries."""
    if getattr(args, "clear", False):
        clear_hook_failures()
        print("Hook failure log cleared.")
        return

    failures = load_hook_failures()
    project_filter = getattr(args, "project", None)
    if project_filter:
        failures = [f for f in failures if f.get("project") == project_filter]

    if not failures:
        print("No hook failures recorded.")
        return

    for entry in reversed(failures):
        ts = entry.get("ts", "?")
        project = entry.get("project", "?")
        hook = entry.get("hook", "?")
        template = entry.get("template") or "—"
        exit_code = entry.get("exit_code", "?")
        output = entry.get("output", "")
        print(
            f"\n{bold(f'[{ts}]')}  {cyan(project)} / {hook}"
            f"  template: {template}  exit: {exit_code}"
        )
        if output:
            for line in output.splitlines()[:30]:
                print(f"  {dim(line)}")


def cmd_debug_self_report(args):
    """Print this machine's own projects/templates as JSON.

    Used by `colette config sync` (and get_project()'s live-fallback check)
    over SSH to pull a read-only snapshot of a remote machine's own data —
    never intended for interactive use. Self-identification: if the caller
    passed a `projects_dir` that matches one of this host's own `type:
    "local"` entries' own `projects_dir`, that entry is used as-is — this
    disambiguates hosts that run more than one logical "local" machine out
    of a single shared `~/.config/colette/` (e.g. separate prod/dev
    workspaces on one server, each with its own projects directory). Both
    sides are `~`-expanded before comparing (using *this* machine's own
    home, since that's where both values are meaningful) so `~/projects`
    and its absolute equivalent still match. Otherwise, falls back to the
    `type: "local"` entry matching this machine's own default_machine, else
    the first `type: "local"` entry — the original single-local-machine
    heuristic.

    `projects` is filtered to only entries whose own `machine` field equals
    the resolved self-name, so a host with multiple local machines sharing
    one `projects.json` never reports another machine's projects as its
    own. On a normal single-local-machine host this filter is a no-op,
    since every project there already carries that one machine's name.
    """
    import os

    cfg = load_config()
    machines = cfg.get("machines", {})
    default_name = cfg.get("default_machine")
    requested_dir = getattr(args, "projects_dir", None)

    self_name = None
    if requested_dir:
        requested_dir = os.path.expanduser(requested_dir).rstrip("/")
        self_name = next(
            (
                n
                for n, m in machines.items()
                if m.get("type") == "local"
                and m.get("projects_dir")
                and os.path.expanduser(m["projects_dir"]).rstrip("/") == requested_dir
            ),
            None,
        )
    if not self_name:
        if default_name and machines.get(default_name, {}).get("type") == "local":
            self_name = default_name
        else:
            self_name = next((n for n, m in machines.items() if m.get("type") == "local"), None)

    if not self_name:
        err("no local machine entry found in this machine's own config; cannot self-report.")

    self_machine = machines[self_name]
    report = {
        "machine": {
            "projects_dir": self_machine.get("projects_dir", ""),
            "templates": self_machine.get("templates", []),
        },
        "projects": [p for p in load_local_projects() if p.get("machine") == self_name],
    }
    print(json.dumps(report))


def cmd_debug(args):
    """Dispatcher for debug sub-commands."""
    if args.debug_cmd == "hook-log":
        cmd_debug_hook_log(args)
    elif args.debug_cmd == "self-report":
        cmd_debug_self_report(args)
    else:
        args.debug_parser.print_help()
