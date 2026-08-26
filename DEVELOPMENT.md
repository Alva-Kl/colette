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
    commands.py            create / delete / list / link / unlink / attach / ide / agent
    __init__.py            Re-exports for the project package
  config/
    commands.py            machine & template management sub-commands
    __init__.py            Re-exports for the config package
  session/
    commands.py            start / stop / monitor / logs
    __init__.py            Re-exports for the session package
  template/
    executor.py            Hook execution (_resolve_hook_with_super, run_template_hook, build_hook_command,
                           build_project_bootstrap, compute_effective_template_hook)
    registry.py            Scaffold / metadata helpers (scaffold_template_hook_files, upsert/remove metadata)
    __init__.py            Re-exports for the template package
  debug/
    commands.py            hook-log (failure log) / self-report (internal — dumps this machine's own
                           projects/templates as JSON, invoked over SSH by `colette config sync`)
    __init__.py            Re-exports for the debug package
  tui/
    app.py                 cmd_tui entry point — curses wrapper, screen-stack loop, sets tui.state.stdscr
    menu.py                Menu widget — renders items, handles arrow-key navigation, jobs footer
    screens.py             Screen builders — main menu, project/template lists and actions; async create/delete
    forms.py               In-TUI overlay forms: ask(), confirm(), type_to_confirm()
    state.py               Shared TUI state: stdscr reference, running_jobs list (thread-safe)
    __init__.py            Re-exports cmd_tui
  utils/
    config.py              Config file I/O — config.json, local-only projects.json (load_local_projects/
                           save_local_projects), read-only remote cache (load_machine_cache/save_machine_cache),
                           merged load_projects() view, get_project() with live-SSH fallback, hook files
    helpers.py             build_projects_by_machine, filter_projects_by_name, detect_project_from_cwd,
                           resolve_ide_command, write_project_record/delete_project_record dispatcher
    formatting.py          ANSI colours, err() / warn() / info()
    validation.py          validate_project_name / validate_machine_name
    ssh.py                 ssh_run, ssh_interactive, fetch_self_report (project/template pull),
                           push_project_entry/remove_remote_project_entry, push_project_hooks/
                           push_template_hooks, ssh_read_hook_files (batched fetch)
    tmux.py                local_tmux_session, ensure_session, get_sessions, create_tmux_window_with_panes
    notify.py              send_notification(title, body) — desktop notifications (Linux/macOS)
tests/
  conftest.py              tmp_config fixture + reset_tui_state autouse fixture + shared helpers
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
  test_tui_screens.py
  test_tui_navigation.py
  test_tui_forms.py        Tests for ask(), confirm(), type_to_confirm()
  test_notify.py           Tests for send_notification()
scripts/
  build.sh                 beta / prod zipapp build
  install.sh               install helper
sandbox/                   Docker sandbox for end-to-end testing — see "Sandbox" below
README.md                  End-user documentation
DEVELOPMENT.md             This file
```

---

## Sandbox

`sandbox/` is a Docker-based, fully isolated test environment for exercising
the real `colette` binary/TUI end-to-end — real fake projects, real fake
templates, an optional fake SSH remote machine — without ever touching a
developer's or a deployment host's real `~/.config/colette` or
`~/colette-projects`. Colette's config dir is hardcoded to
`Path.home() / ".config" / "colette"` (`utils/config.py`) with no env
override, so a container's own `$HOME` is the isolation mechanism; the repo
is bind-mounted read-write into the `sandbox` container so edits to
`colette_cli/*.py` are picked up immediately (rebuild the zipapp with
`./scripts/build.sh` inside the container, no image rebuild needed) —
`sandbox/README.md` has the full quick-start. `sandbox/harness.py` drives
`colette tui` over a real pty with scripted keystrokes (including ESC) and
flags a run as crashed if an unhandled Python traceback shows up in the
output — useful for regression-testing the TUI's crash-safety behavior
(see the "TUI leaf actions"/"TUI multi-field forms" rows in "Coding
conventions" above) without a human at the keyboard.

---

## Config file schemas

All state lives under `~/.config/colette/`, and is **local to whichever
machine you're looking at** — see "Decentralized remote-machine model"
below for the full picture. This section documents the schema of each file
as it exists on a single machine.

### `config.json`

Machine entries come in two shapes: the machine's own definition(s)
(`type: "local"`, full data), and connection stubs for known remote
machines (`type: "ssh"`, mostly connection info — the remote's actual
project/template data is the remote's own business, reachable only via the
read-only cache described below). A connection stub *is* still prompted for
and stores its own `projects_dir` (the value the user enters when running
`add-machine`/`edit-machine`) — this is purely the controller's own record
of what it believes that connection's projects directory to be; the
controller never reads or writes anything there directly. `fetch_self_report`
(`utils/ssh.py`) passes it to the remote's `colette debug self-report` call
so the remote can disambiguate itself when it hosts more than one logical
`type: "local"` machine — see `cmd_debug_self_report`'s docstring
(`debug/commands.py`) and the "Decentralized remote-machine model" section
below. A connection stub *can* also still carry its own `templates` list
(the older push model: author hook scripts locally via
`add-template`/`edit-hook`, which get pushed to the remote — see "Hook
resolution and pushing to remotes" below); the two sources are merged by
`list_creatable_templates`/`list_creatable_template_names`/
`get_creatable_template` (`template/registry.py`) wherever a template needs
to be *resolved for use* (`cmd_create`, the TUI's "Create project" picker,
`all_template_names`'s namespace check) — local entries win on a name
collision. Everywhere else (listing/editing/removing a machine's own
configured templates) still reads `machine["templates"]` directly via
`normalize_machine_templates`/`list_machine_template_names`/
`get_machine_template`, deliberately untouched by the cache, since mutating
a cache-derived entry would incorrectly persist read-only remote data as if
locally owned.

```json
{
  "default_machine": "local",
  "machines": {
    "local": {
      "type": "local",
      "projects_dir": "/home/user/projects",
      "agent_command": "copilot --resume",
      "ide_command": "code",
      "templates": [
        { "name": "my-tmpl", "type": "directory", "path": "/home/user/templates/my-tmpl" },
        { "name": "from-git", "type": "git", "url": "https://github.com/user/tmpl.git" }
      ]
    },
    "server": {
      "type": "ssh",
      "host": "user@192.168.1.10",
      "ssh_key": "/home/user/.ssh/id_ed25519",
      "colette_path": "/home/user/.local/bin/colette",
      "projects_dir": "/home/user/projects",
      "agent_command": "claude",
      "ide_command": "code --folder-uri vscode-remote://ssh-remote+{host}{path}"
    }
  }
}
```

`agent_command`/`ide_command` on a remote connection stub are
**controller-side only** — they describe how *this* machine talks to
`server` (the literal command embedded in the SSH+tmux session; the local
argv `ide_command` resolves to), never fetched from or pushed to the
remote's own config. `colette config edit-machine server` run from a
different controller could set different values for the same remote.

`agent_command`/`ide_command` are optional free-text fields, no validation.
When unset, `colette_cli.utils.config` exposes the fallback defaults
(`DEFAULT_AGENT_COMMAND`, `DEFAULT_IDE_COMMAND_LOCAL`,
`DEFAULT_IDE_COMMAND_REMOTE`) — call sites always read them as
`machine.get("agent_command") or DEFAULT_AGENT_COMMAND`, never a bare
`.get(..., default)`, so an explicitly empty string also falls back.
`ide_command` is resolved via `resolve_ide_command()` in `utils/helpers.py`:
it's `shlex.split()` first, then `{host}`/`{path}` tokens are substituted
into each argv token, and the path is appended as a trailing argument only
if no token contained `{path}` — see that function's docstring for the full
algorithm. `ide_command` always runs as a local subprocess, even for a
remote project; it never SSHes anywhere itself.

### `projects.json`

**Local-only** — this machine's own projects, never a remote's. A project
created on a remote machine (`colette create -m server ...`) lives in
*that* machine's own `projects.json`, reached over SSH at create/delete/
rename time, never written here.

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

`template` may be `null` for linked projects with no template. `machine`
always names one of this config's own `type: "local"` entries — never a
remote connection stub.

### `cache/<machine>.json` — read-only remote cache

Populated by `colette config sync [machine]`, one file per known remote
machine. **Machine-generated and read-only** — never hand-edited, always
overwritten wholesale by the next sync.

```json
{
  "machine": "server",
  "synced_at": "2026-01-01T12:00:00Z",
  "projects_dir": "/home/user/projects",
  "templates": [
    { "name": "my-tmpl", "type": "directory", "path": "/home/user/templates/my-tmpl" }
  ],
  "projects": [
    { "name": "remote-project", "machine": "local", "path": "/home/user/projects/remote-project", "template": "my-tmpl" }
  ]
}
```

`projects` here is the remote's own `projects.json`, filtered to the entries
belonging to the specific local machine being reported on (so each entry's
`machine` field is the *remote's* self-name, typically `"local"` — not the
controller's connection name for it, e.g. `"server"`). The merged read view
in `load_projects()` (`utils/config.py`) remaps this to the controller's
connection name and tags each entry `_cached: True` before handing it to
callers — see "Decentralized remote-machine model" below. `templates` here
is metadata only (name/type/path-or-url/description/params) — hook script
*bodies* are never cached; they're always fetched fresh over SSH at
execution time (see the hook system section below).

A single physical host can run more than one logical `type: "local"`
machine out of one shared `~/.config/colette/` (e.g. separate prod/dev
workspaces on the same server, distinguished only by each project's own
`machine` field in that host's one `projects.json`). `cmd_debug_self_report`
(`debug/commands.py`) disambiguates this using each connection's own
`projects_dir`, not its name: `fetch_self_report` (`utils/ssh.py`) passes
the calling machine stub's configured `projects_dir` as an argument to the
remote `colette debug self-report` call, and if that value (`~`-expanded)
matches one of the remote's own `type: "local"` entries' own `projects_dir`
(also `~`-expanded, both against *this* machine's home since the comparison
runs on the remote), that entry is used as-is (`projects` filtered to
`p["machine"] == that entry's name`). This only requires each connection
stub's `projects_dir` to be set to that logical machine's real projects
directory — nothing about the controller's own name for the connection
matters. If it doesn't match (empty/unset `projects_dir`, or the remote has
only one local machine, the common case), self-report falls back to its
original heuristic (the entry matching the remote's own `default_machine`,
else the first `type: "local"` entry) and reports all of that host's
projects.

### Hook file directories

```
~/.config/colette/
  machines/
    <machine-name>/
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

Resolution differs by whether the project's machine is local or remote —
`_resolve_hook_with_super` in `template/executor.py` branches on whether a
pre-fetched `remote_hooks` dict is supplied:

1. **Local resolution order** (`remote_hooks=None`): first checks the
   project-specific hook (`projects/<project>/.<hook>`), then falls back to
   the machine-scoped template hook (`machines/<machine>/templates/<template>/.<hook>`).
   A hook is only "effective" if it contains at least one non-comment,
   non-shebang line (`_has_effective_script`). Both tiers are read straight
   off local disk.

2. **Remote resolution order** (`remote_hooks` supplied): also two tiers —
   project hook, then template hook — both read from a dict pre-fetched over
   SSH by `ssh_read_hook_files` (`utils/ssh.py`), which fetches every hook
   name's project- and template-level content in **one** SSH round-trip (a
   delimited `cat` loop), not one round-trip per hook. The remote's own
   `templates/<template>/.<hook>` *is* already the machine-specific,
   already-flattened copy — see `push_template_hooks` below. Remote hook
   content is never cached locally; it's fetched fresh on every hook
   invocation, trading one extra SSH round-trip for the guarantee that
   remote-owned hooks are never run stale.

3. **SUPER inheritance**: When a project-level hook is active and wants to
   chain to its template hook, `$SUPER` is set to point at it. Locally this
   is a literal file path; when the "super" source is a `_FetchedContent`
   instance (remote_hooks mode) or `is_remote=True` with a local path, its
   content is inlined via a base64-encoded tempfile instead (`_super_assignment`)
   — see `push_template_hooks` for how remote copies get pre-flattened so
   remote resolution never needs a *second* level of $SUPER-over-SSH.
   `$SUPER` is never set for template-level hooks to prevent self-sourcing.

4. **coletterc**: `_prepend_coletterc` prepends the resolved coletterc content
   before every hook command — `run_template_hook` and `build_hook_command` both
   call it, threading the same `remote_hooks` dict *and* `machine_name` through
   (required so local resolution can find the machine-scoped tier) so coletterc and
   the main hook share one SSH fetch. When a project-level coletterc is
   active, `SUPER` is set before the coletterc content so it can inherit
   from the template coletterc.

5. **Execution**: `run_template_hook` runs the resolved+prepended script via
   `bash -lc` either locally (`subprocess.run`) or remotely (`ssh_run`).

6. **Interactive hooks** (`onlogs`, `attach`): `build_hook_command` assembles a
   full shell command string with coletterc prepended and env assignments, then
   passes it to `local_tmux_session` or `ssh_interactive`.

7. **Bootstrap** (`coletterc` for terminal sessions): `build_project_bootstrap`
   generates `exec bash --rcfile <(echo BASE64 | base64 -d)` where the decoded
   rcfile sources `~/.bashrc` first, then coletterc. This ensures venv activations
   in coletterc are applied *after* `.bashrc` and therefore persist in the
   interactive terminal. Takes an optional `machine` param, required when
   `is_remote=True` so it can fetch coletterc content over SSH.

### Pushing hooks to a remote machine

Authoring stays controller-local (`colette config edit-hook`/`add-template`/
`edit-template` still open a local file in `nano`) — but every save pushes
eagerly to the target machine over SSH if it's remote, instead of waiting
for the next `colette config sync`:

- **`push_template_hooks`** (`utils/ssh.py`): for each hook name, computes
  the *effective* content for that specific machine — its machine-scoped
  override if effective, else the shared template hook — via
  `compute_effective_template_hook` (`template/executor.py`), inlining any
  `source "$SUPER"` chain between them (base64 tempfile trick) so the
  pushed copy is fully self-contained. Called from
  `cmd_config_add_template`/`edit_template`/`edit_hook`/`remove_template`
  (as a delete)/`rename_template` (as a move) whenever the target machine
  is remote.
- **`push_project_hooks`**: pushes a project's own hook-override files
  *verbatim* (no flattening) — a project hook's `source "$SUPER"` is left
  intact and resolves dynamically at remote execution time against
  whatever's currently in that machine's `templates/<template>/` (kept
  fresh by `push_template_hooks`). Called from `cmd_config_edit_project_hook`.
- `inject_project_config` (the old combined push-everything-on-sync
  function) no longer exists — replaced by these two eager-push functions
  plus `push_project_entry`/`remove_remote_project_entry` for project
  *records* (see below).

---

## Decentralized remote-machine model

Each machine's `~/.config/colette/` is authoritative only for its own
projects and templates — the controller never keeps a permanent, owned copy
of a remote's data. Colette also never installs or updates its own binary on
a remote machine — keeping the `colette` binary at each machine's configured
`colette_path` up to date is entirely the user's own responsibility (e.g.
`colette update` still runs the `onupdate` project hook, but does nothing to
the colette binary itself).

**Project/template sync (pull)** — `colette config sync [machine]`
(`cmd_config_sync`, `config/commands.py`) SSHs an internal `colette debug
self-report` command on the remote (which dumps that machine's own
`projects.json` plus its own machine entry's `projects_dir`/`templates` as
JSON — `cmd_debug_self_report`, `debug/commands.py`) and writes the result
into `~/.config/colette/cache/<machine>.json`. This is the **only** way the
cache gets refreshed in bulk; nothing pushes local data to a remote's
registry.

Two smaller mechanisms round this out — both described in "Hook system
architecture" above and "Config file schemas" below, respectively:
eager hook pushes (`push_template_hooks`/`push_project_hooks`, triggered by
every `edit-hook`/`add-template`/`edit-project-hook` etc.) and project
*record* pushes (`push_project_entry`/`remove_remote_project_entry`,
triggered by `cmd_create`/`cmd_delete`/`cmd_link`/`cmd_unlink`/
`cmd_config_rename_template` via the `write_project_record`/
`delete_project_record` dispatcher in `utils/helpers.py`, which routes to
either the local `projects.json` or the remote's own over SSH depending on
`is_remote_machine(machine)`).

### Live fallback for stale caches

`get_project(name)` (`utils/config.py`) — the single chokepoint under
`require_project`, used by all single-name lookups (`ide`, `agent`,
`attach`, `delete`, `unlink`, `logs <name>`, `edit-project-hook`) — falls
back to a live SSH self-report check against every configured remote
machine when a name isn't found in the merged local+cache view, patching
that machine's cache opportunistically on a hit. This is **not** wired into
`load_projects()` itself, so batch/listing commands (`list`, `start`,
`stop`, `update`, `monitor`) stay cache-only and fast — they never trigger
a live SSH round-trip just because a project happens to be missing.

### Build pipeline

A `Makefile` at the repo root wraps these — `make build-beta`, `make
build-prod`, `make build-prod-release`, `make install` — but the raw
commands are:

```bash
# 1. Build the beta zipapp
./scripts/build.sh

# 2. Promote beta to prod — plain, no version change (safe to run any time,
#    e.g. after every edit while iterating in the sandbox)
./scripts/build.sh prod

# 2b. ...or cut an actual release: promote AND bump the patch version in
#     __init__.py/pyproject.toml (only happens with this flag — never implicit)
./scripts/build.sh prod --bump

# 3. Install prod binary to PATH for local use
./scripts/install.sh          # copies build/prod/colette → ~/.local/bin/colette
```

`build/prod/colette` is the **canonical local binary** and the file that
`colette --version` reports. Colette never copies it to a remote machine
itself — see "Decentralized remote-machine model" above.

### For developers

**Before testing against the sandbox's fake remote machine**, always build
and promote (inside `sandbox/`'s container — never on the host, see "Running
tests" below), then copy the binary onto `ssh-target` yourself (colette has
no auto-install path — see `sandbox/README.md`'s "Testing the SSH remote
machine" section for the exact copy command):

```bash
./scripts/build.sh && ./scripts/build.sh prod && ./scripts/install.sh
```

The manual project/template pull (useful for debugging) is:

```bash
colette config sync [machine-name]
```

---



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
- [ ] **TUI action**: wire the same capability into the relevant `tui/screens.py` screen, per the CLI/TUI-parity convention below (unless the task explicitly scopes it to CLI-only)

---

## Coding conventions

| Rule | Detail |
|---|---|
| Errors | Always use `err(message)` from `utils/formatting.py` — it prints to stderr and calls `sys.exit(1)` |
| Warnings | Use `warn(message)` — prints to stderr, does **not** exit |
| Success output | Use `info(message)` — prints `✓ message` to stdout |
| No duplication | Shared logic belongs in `utils/helpers.py` (project grouping/filtering) or `utils/config.py` (I/O). Never copy logic across command modules. |
| KISS / DRY | Prefer the simplest solution. Extract any logic used in two or more places into a helper. Avoid clever code that obscures intent. |
| Thin command functions | Command handlers should orchestrate helpers; keep business logic out of `main.py`. |
| Imports | Import functions from `colette_cli.utils.*`; avoid relative imports across packages. |
| Naming | `cmd_<name>` for top-level commands, `cmd_config_<sub>` for config sub-commands |
| CLI/TUI parity | Every new user-facing capability gets both a CLI command and a TUI action, calling the same backend function from both, unless the task explicitly scopes it to one surface. |
| TUI leaf actions | Never call a `cmd_*`/`cmd_config_*` function directly from a `tui/screens.py` action — always go through `_popup`/`_async_popup`/`_suspend` so an `err()`-raised `SystemExit` (or any other exception) surfaces as a friendly popup instead of relying solely on the backstop below. `MenuItem.run()` (`tui/menu.py`) also catches any exception that slips through, so a forgotten wrapper can no longer crash the whole TUI — but it only shows a raw traceback, not a nice message. |
| TUI multi-field forms | Prefer the `form()` primitive (`tui/forms.py`) over sequential `ask()` calls for any flow with more than one field — it shows every field at once, moves focus with arrows/Tab, and only ESC/Cancel aborts the whole thing (see `_add_machine_interactive`/`_edit_machine_interactive`/`_add_template_interactive`/`_edit_template_interactive`/`_create_project_interactive`/`_link_directory_interactive`). For the rare remaining spot that still chains multiple `ask()` calls (e.g. `template_param_items`'s `_add_param`), guard every one with `if result is None: return` before falling back to a default — never `ask(...) or default` — otherwise cancelling (ESC) a *non-first* field silently substitutes the default and keeps going instead of aborting the whole action. |

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

### TUI form actions

Actions that collect user input use overlay forms from `tui/forms.py` instead
of suspending curses. To test these actions, patch the form functions directly:

```python
with patch("colette_cli.tui.forms.ask", return_value="my-project"):
    item.run()

with patch("colette_cli.tui.forms.confirm", return_value=True):
    item.run()

with patch("colette_cli.tui.forms.type_to_confirm", return_value=True):
    item.run()
```

The `reset_tui_state` fixture in `conftest.py` is autouse and ensures
`tui.state.stdscr` is `None` before each test, so forms fall back to plain
`input()` when not explicitly mocked.

### Async TUI actions (Create / Delete)

*Create project* and *Delete project* in the TUI run in background threads.
Use `_SyncThread` (defined in `test_tui_screens.py`) to run them synchronously
and patch `colette_cli.utils.notify.send_notification` to suppress desktop
notifications during tests:

```python
class _SyncThread:
    def __init__(self, target, daemon=False): self._target = target
    def start(self): self._target()

with patch("colette_cli.tui.screens.threading.Thread", _SyncThread), \
     patch("colette_cli.utils.notify.send_notification"):
    item.run()
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

**Never run `pytest`/`python -m pytest` directly on a host machine** — always
run the suite inside `sandbox/`'s `sandbox` container, which already has
`requirements-dev.txt` installed. `make test` does this (brings the sandbox
up if needed, waits for it to finish initializing, then runs the suite); the
raw command is:

```bash
docker compose -f sandbox/docker-compose.yml up -d
docker compose -f sandbox/docker-compose.yml exec sandbox \
  python3 -m pytest tests/ -v
```

The repo is bind-mounted read-write into that container, so this always runs
against the current working tree, including uncommitted changes — no image
rebuild needed between runs. See `sandbox/README.md` for the full sandbox
setup (also used for real end-to-end TUI testing, not just unit tests).

Bring the sandbox container back down once you're done testing, rather than
leaving it running:

```bash
docker compose -f sandbox/docker-compose.yml down
```

`pyproject.toml` defines project metadata and the `colette` entry-point script.
`requirements-dev.txt` lists development-only dependencies (pytest).

---

## Do-not-forget checklist (before committing)

- [ ] README.md updated for every user-visible change
- [ ] `__init__.py` exports updated for every new public symbol
- [ ] `main.py` handlers dict and imports updated for new top-level commands
- [ ] Parser description strings updated (both banner and sub-parser descriptions)
- [ ] Tests written for all new behavior
- [ ] `python -m pytest tests/` passes with zero failures (run inside `sandbox/`'s container, never on the host)
- [ ] No logic duplicated across command modules (use `utils/`)
- [ ] No direct `sys.exit` in command handlers — always use `err()`
