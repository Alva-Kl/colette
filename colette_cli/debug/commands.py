"""Debug sub-commands."""

from colette_cli.utils.config import clear_hook_failures, load_hook_failures
from colette_cli.utils.formatting import bold, cyan, dim


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


def cmd_debug(args):
    """Dispatcher for debug sub-commands."""
    if args.debug_cmd == "hook-log":
        cmd_debug_hook_log(args)
    else:
        args.debug_parser.print_help()
