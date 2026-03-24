# Colette — Copilot Instructions

Colette is a stdlib-only Python CLI tool that manages development projects across local and SSH machines. It orchestrates tmux sessions and runs lifecycle hook scripts.

---

## Commands

```bash
# Install
pip install -e .

# Run tests (full suite)
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_project_commands.py -v

# Run a single test by name
python -m pytest tests/test_project_commands.py::TestCmdCreate::test_create_local -v

# Install dev dependencies (pytest only)
pip install -r requirements-dev.txt
```

No linter is configured. No build step is needed for development.

---

## Architecture

```
colette_cli/
  main.py          Entry point — dispatches args.command to handlers dict
  cli/parser.py    All argparse definitions (build_parser)
  project/         create / delete / list / link / unlink / attach / code
  session/         start / stop / monitor / logs
  config/          machine & template management sub-commands
  template/
    executor.py    Hook resolution and execution
    registry.py    Scaffold / metadata helpers
  tui/
    app.py         curses wrapper and screen-stack loop
    menu.py        Menu widget — MenuItem, navigation, rendering
    screens.py     Screen builders — all menus and their actions
  utils/
    config.py      All config file I/O (load/save config.json, projects.json, templates.json, hook files)
    helpers.py     build_projects_by_machine, filter_projects_by_name
    formatting.py  err() / warn() / info() + ANSI helpers
    validation.py  validate_project_name / validate_machine_name
    ssh.py         ssh_run, ssh_interactive
    tmux.py        local_tmux_session, ensure_session, get_sessions
```

**Data flow**: `main.py` → `cli/parser.py` builds args → `handlers[args.command](args)` dispatches to `project/`, `session/`, or `config/` command functions → they call `utils/config.py` for all file I/O and `utils/helpers.py` for filtering/grouping.

**State** lives entirely in `~/.config/colette/`: `config.json` (machines), `projects.json` (registered projects), `templates.json` (template metadata), and hook script files under `templates/<name>/` and `projects/<name>/`.

**Hook execution** (`template/executor.py`): `_resolve_hook_with_super` picks the project-level hook if effective, else falls back to the template hook. It sets `$SUPER` to the template hook path so project hooks can call `source "$SUPER"`. `coletterc` is prepended before every hook invocation and also bootstrapped into interactive terminal sessions via a base64-encoded `--rcfile`.

**TUI** (`tui/`): `app.py` runs a screen-stack loop. Each screen is a `list[MenuItem]` returned by a builder function in `screens.py`. `menu.py` renders and handles all keyboard input. `MenuItem` supports `selectable=False` for section titles and separators, which are skipped by navigation.

---

## Key conventions

**Error handling** — never call `sys.exit()` directly. Always use:
- `err(msg)` → prints to stderr, exits with code 1
- `warn(msg)` → prints to stderr, no exit
- `info(msg)` → prints `✓ msg` to stdout

**Naming** — `cmd_<name>` for top-level commands, `cmd_config_<sub>` for config sub-commands.

**No duplication** — shared logic goes in `utils/helpers.py` (project filtering/grouping) or `utils/config.py` (file I/O). Never copy logic across `project/`, `session/`, or `config/` modules.

**Thin handlers** — command functions orchestrate helpers; keep business logic out of `main.py`.

**No runtime dependencies** — stdlib only. Do not add third-party packages.

---

## Adding a new top-level command

Every step is required:

1. `cmd_<name>(args)` in the appropriate `commands.py`
2. Export from the package `__init__.py`
3. Import in `colette_cli/main.py`
4. Add `"<name>": cmd_<name>` to the `handlers` dict in `main.py`
5. Add a subparser in `cli/parser.py`
6. Update the `description` string in `build_parser()`
7. Add a `### colette <name>` section in `README.md`
8. Add a `TestCmd<Name>` class in the relevant `tests/test_*_commands.py`

---

## Test patterns

**Filesystem isolation** — every test touching config files must use the `tmp_config` fixture from `tests/conftest.py`. It monkeypatches all path constants in `colette_cli.utils.config` to a temp directory.

**`MagicMock` and `name`** — `MagicMock(name="x")` sets the mock's display name, not an attribute. Always do:
```python
args = MagicMock()
args.name = "my-project"  # correct
```

**`sys.exit`** — catch it with `pytest.raises(SystemExit)`.

**Subprocess** — patch at the call site: `patch("subprocess.run")`.

**TUI actions** — patch `curses.endwin` and `curses.doupdate` when calling actions that use `_suspend` or `_suspend_with_pause`.
