# Colette — Development Guide

This guide is the authoritative reference for working on the Colette codebase.
Read it at the start of every session to avoid omitting steps.

---

## Codebase map

```
colette_cli/
  main.py                  Entry point — dispatches args.command to handlers
  cli/
    parser.py              All argparse definitions (build_parser)
  project/
    commands.py            create / delete / list / link / unlink / attach / code
    __init__.py            Re-exports for the project package
  config/
    commands.py            machine & template management sub-commands
    __init__.py            Re-exports for the config package
  session/
    commands.py            start / stop / monitor / logs
    __init__.py            Re-exports for the session package
  template/
    executor.py            Hook execution (_resolve_hook, run_template_hook, build_hook_command, build_project_bootstrap)
    registry.py            Scaffold / metadata helpers (scaffold_template_hook_files, upsert/remove metadata)
    __init__.py            Re-exports for the template package
  utils/
    config.py              JSON I/O, path constants, hook r/w (template + project)
    helpers.py             build_projects_by_machine, filter_projects_by_name
    formatting.py          ANSI colours, err() / warn() / info()
    validation.py          validate_project_name / validate_machine_name
    ssh.py                 ssh_run, ssh_interactive
    tmux.py                local_tmux_session, ensure_session, get_sessions, create_tmux_window_with_panes
    env.py                 (environment helpers)
tests/
  conftest.py              tmp_config fixture + shared helpers
  test_utils_config.py
  test_utils_helpers.py
  test_utils_formatting.py
  test_utils_validation.py
  test_template_registry.py
  test_template_executor.py
  test_project_commands.py
  test_config_commands.py
  test_session_commands.py
  test_cli_parser.py
scripts/
  build.sh                 beta / prod zipapp build
  install.sh               install helper
README.md                  End-user documentation
DEVELOPMENT.md             This file
```

---

## Config file schemas

All state lives under `~/.config/colette/`.

### `config.json`
```json
{
  "default_machine": "local",
  "machines": {
    "local": {
      "type": "local",
      "projects_dir": "/home/user/projects",
      "templates": [
        { "name": "my-tmpl", "type": "directory", "path": "/home/user/templates/my-tmpl" },
        { "name": "from-git", "type": "git", "url": "https://github.com/user/tmpl.git" }
      ]
    },
    "server": {
      "type": "ssh",
      "host": "user@192.168.1.10",
      "ssh_key": "/home/user/.ssh/id_ed25519",
      "projects_dir": "/home/user/projects",
      "templates": []
    }
  }
}
```

### `projects.json`
```json
[
  {
    "name": "my-project",
    "machine": "local",
    "path": "/home/user/projects/my-project",
    "template": "my-tmpl"
  }
]
```

`template` may be `null` for linked projects with no template.

### `templates.json`
```json
{
  "templates": [
    {
      "name": "my-tmpl",
      "description": "A description",
      "params": { "ENV": "dev", "PORT": "8080" }
    }
  ]
}
```

### Hook file directories

```
~/.config/colette/
  templates/
    <template-name>/
      .oncreate    (chmod 755, bash)
      .onstart     (chmod 755, bash)
      .onstop      (chmod 755, bash)
      .onlogs      (chmod 755, bash)
      .coletterc   (chmod 644, sourced — not executed)
  projects/
    <project-name>/
      .oncreate    (same filenames — project-specific overrides)
      ...
```

---

## Hook system architecture

1. **Resolution order**: `_resolve_hook` in `template/executor.py` first checks the
   project-specific hook (`projects/<project>/.<hook>`), then falls back to the
   template hook (`templates/<template>/.<hook>`). A hook is only "effective" if
   it contains at least one non-comment, non-shebang line (`_has_effective_script`).

2. **Execution**: `run_template_hook` runs the resolved script via `bash -lc` either
   locally (`subprocess.run`) or remotely (`ssh_run`).

3. **Interactive hooks** (`onlogs`, `attach`): use `build_hook_command` to assemble a
   full shell command string with env assignments, then pass to `local_tmux_session`
   or `ssh_interactive`.

4. **Bootstrap** (`coletterc`): `build_project_bootstrap` reads the template's
   `.coletterc` and prepends it to `exec bash` for `tmux new-session`.

---

## Checklist — adding a new top-level command

Follow **every** step. Missing any one step is a bug.

- [ ] **Handler**: add `cmd_<name>(args)` in the appropriate `commands.py`
  (project, session, or a new module)
- [ ] **Package export**: add the function to the package `__init__.py`
- [ ] **main.py import**: add the import at the top of `colette_cli/main.py`
- [ ] **main.py dispatch**: add `"<name>": cmd_<name>` to the `handlers` dict
- [ ] **Parser**: add a subparser in `cli/parser.py` under `sub = parser.add_subparsers(...)`
- [ ] **Parser banner**: update the `description` string in `build_parser()` to list the new command
- [ ] **README.md**: add a `### colette <name>` section describing usage and examples
- [ ] **Tests**: add a `TestCmd<Name>` class in the relevant `tests/test_*_commands.py`

---

## Checklist — adding a new `config` sub-command

- [ ] **Handler**: add `cmd_config_<sub>(args)` to `config/commands.py`
- [ ] **Package export**: add to `config/__init__.py`
- [ ] **Dispatch branch**: add an `elif args.config_cmd == "<sub>":` branch in `cmd_config`
- [ ] **Parser**: add `csub.add_parser("<sub>", ...)` in `cli/parser.py`
- [ ] **Parser config description**: update the `description` string of the `config` sub-parser
- [ ] **README.md**: add a `#### colette config <sub>` section
- [ ] **Tests**: add test cases in `tests/test_config_commands.py`

---

## Coding conventions

| Rule | Detail |
|---|---|
| Errors | Always use `err(message)` from `utils/formatting.py` — it prints to stderr and calls `sys.exit(1)` |
| Warnings | Use `warn(message)` — prints to stderr, does **not** exit |
| Success output | Use `info(message)` — prints `✓ message` to stdout |
| No duplication | Shared logic belongs in `utils/helpers.py` (project grouping/filtering) or `utils/config.py` (I/O). Never copy logic across command modules. |
| Thin command functions | Command handlers should orchestrate helpers; keep business logic out of `main.py`. |
| Imports | Import functions from `colette_cli.utils.*`; avoid relative imports across packages. |
| Naming | `cmd_<name>` for top-level commands, `cmd_config_<sub>` for config sub-commands |

---

## Test patterns

### Redirecting config paths

Every test that touches the filesystem **must** use the `tmp_config` fixture
from `tests/conftest.py`. It monkeypatches all module-level path constants in
`colette_cli.utils.config` to point at `tmp_path`. This prevents tests from
reading or writing `~/.config/colette/`.

```python
def test_something(self, tmp_config):
    from colette_cli.utils.config import save_projects, load_projects
    save_projects([{"name": "p", ...}])
    assert load_projects()[0]["name"] == "p"
```

### Mocking `subprocess.run`

```python
with patch("subprocess.run") as mock_run:
    cmd_something(args)
mock_run.assert_called_once()
```

### Mocking `input()`

```python
with patch("builtins.input", return_value="y"):
    cmd_something(args)
```

### ⚠️ MagicMock and `name`

`MagicMock(name="proj")` sets the mock's **display name**, **not** an attribute
called `name`. Always assign name explicitly:

```python
# WRONG — args.name will be a MagicMock, not "proj"
args = MagicMock(name="proj")

# CORRECT
args = MagicMock()
args.name = "proj"
```

### Expecting `sys.exit`

```python
with pytest.raises(SystemExit):
    cmd_something(args)
```

### Running tests

```bash
python -m pytest tests/ -v
```

There is no `setup.py` or `pyproject.toml` test runner config; pytest discovers
tests automatically.

---

## Do-not-forget checklist (before committing)

- [ ] README.md updated for every user-visible change
- [ ] `__init__.py` exports updated for every new public symbol
- [ ] `main.py` handlers dict and imports updated for new top-level commands
- [ ] Parser description strings updated (both banner and sub-parser descriptions)
- [ ] Tests written for all new behavior
- [ ] `python -m pytest tests/` passes with zero failures
- [ ] No logic duplicated across command modules (use `utils/`)
- [ ] No direct `sys.exit` in command handlers — always use `err()`
