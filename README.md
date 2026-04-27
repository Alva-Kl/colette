# Colette

```
   ██████╗ ██████╗ ██╗     ███████╗████████╗████████╗███████╗
  ██╔════╝██╔═══██╗██║     ██╔════╝╚══██╔══╝╚══██╔══╝██╔════╝
  ██║     ██║   ██║██║     █████╗     ██║      ██║   █████╗
  ██║     ██║   ██║██║     ██╔══╝     ██║      ██║   ██╔══╝
  ╚██████╗╚██████╔╝███████╗███████╗   ██║      ██║   ███████╗
   ╚═════╝ ╚═════╝ ╚══════╝╚══════╝   ╚═╝      ╚═╝   ╚══════╝
  Context Organizer for Local Environments and Task Tracking Engine
```

Colette is a CLI tool for managing projects across one or more machines (local or
remote via SSH). It orchestrates tmux sessions, runs lifecycle hook scripts, and
lets you supervise multiple development tasks or GenAI agents in parallel.

---

## Installation

```bash
pip install -e .
```

Or run directly from the repository:

```bash
./colette <command>
```

---

## Configuration files

All state is stored under `~/.config/colette/`:

| File / Directory | Purpose |
|---|---|
| `config.json` | Machine definitions and default machine |
| `projects.json` | Registered projects |
| `templates.json` | Template metadata (description, params) |
| `templates/<name>/` | Hook scripts for a template |
| `projects/<name>/` | Project-specific hook overrides |

---

## Concepts

### Machines

A **machine** is a target environment — either the local host or a remote host
accessed via SSH. Every project belongs to a machine.

### Templates

A **template** is a directory or git repository used as the starting point when
creating a new project. Templates have associated hook scripts that run at
lifecycle events.

Template names and project names share a **global namespace** — a name cannot be
used for both a template and a project at the same time. This allows project
commands (`colette code`, `colette attach`, etc.) to accept a template name and
work on the template's source directory directly.

### Projects

A **project** is a directory on a machine, optionally created from a template.
Projects can also be linked without a template (`colette link`).

### Hooks

Hooks are shell scripts that Colette runs automatically at lifecycle events. See
[Hook System](#hook-system) for details.

---

## Commands

### `colette config` — manage machines and templates

```
colette config [<action>]
```

Without an action, prints a summary of the current configuration.

#### Actions

| Action | Description |
|---|---|
| `list` | List all configured machines |
| `list-templates [machine]` | List templates for a machine |
| `add-machine` | Interactively add a machine |
| `edit-machine <machine>` | Edit a machine |
| `add-template <machine> <template>` | Add a template to a machine |
| `edit-template <machine> <template>` | Edit a template |
| `edit-hook <template> <hook>` | Edit a template hook script |
| `edit-project-hook <project> <hook>` | Edit a project-specific hook script |
| `run-template-update <template>` | Run the onupdate hook for a template |
| `remove-template <machine> <template>` | Remove a template from a machine |
| `remove-machine <machine>` | Remove a machine |
| `set-default <machine>` | Set the default machine |
| `rename-template <machine> <old> <new>` | Rename a template on a machine |
| `sync-remote [machine]` | Manually sync the colette binary to remote machine(s) |

#### `colette config list`

List all configured machines with their templates and projects directories.

```bash
colette config list
```

#### `colette config list-templates [machine]`

List templates available for a machine, including hook files and params.

```bash
colette config list-templates
colette config list-templates my-server
```

#### `colette config add-machine`

Interactively add a machine (local or SSH).

```bash
colette config add-machine
# Prompts: name, type (local/ssh), SSH host/port/key (if ssh), projects_dir, initial template
```

#### `colette config edit-machine <machine>`

Interactively edit an existing machine's settings.

```bash
colette config edit-machine my-server
```

#### `colette config add-template <machine> <template>`

Add a template (directory or git) to a machine and scaffold its hook files.

```bash
colette config add-template local my-template
colette config add-template local my-template --param ENV=dev --param PORT=8080
```

#### `colette config edit-template <machine> <template>`

Edit a template's source, description, and parameters.

```bash
colette config edit-template local my-template --param ENV=prod
```

#### `colette config edit-hook <template> <hook>`

Open a template hook script in `nano` for editing. The hook file is created if
it does not exist yet.

```bash
colette config edit-hook my-template oncreate
colette config edit-hook my-template onstart
colette config edit-hook my-template onlogs
colette config edit-hook my-template onupdate
colette config edit-hook my-template coletterc
```

Use `--machine` / `-m` to edit a **machine-specific** hook override instead of
the shared hook. Machine-specific hooks take precedence over the shared hook
during execution; they fall back to the shared hook when their content is empty.

```bash
colette config edit-hook my-template onstart --machine my-remote
```

Valid hook names: `oncreate`, `onstart`, `onstop`, `onlogs`, `onupdate`, `ondelete`, `coletterc`.

#### `colette config edit-project-hook <project> <hook>`

Open a project-specific hook override script in `nano` for editing. Scaffolds
the project's hook directory under `~/.config/colette/projects/<project>/` if
needed. The project must already be registered with colette.

```bash
colette config edit-project-hook my-project onstart
colette config edit-project-hook my-project onlogs
```

Valid hook names: `oncreate`, `onstart`, `onstop`, `onlogs`, `onupdate`, `ondelete`, `coletterc`.

Project-level hooks take full precedence over the template hook for that event.

#### `colette config run-template-update <template> [-m <machine>]`

Run the `onupdate` hook directly for a template, without a project context.
Use this to update the template itself (e.g. pull the latest changes from its
source repository). The hook receives `COLETTE_TEMPLATE_NAME`,
`COLETTE_MACHINE_NAME`, `COLETTE_PARAM_*`, and (for directory-type templates)
`COLETTE_TEMPLATE_PATH`.

```bash
colette config run-template-update my-template
colette config run-template-update my-template -m my-server
```

#### `colette config rename-template <machine> <old> <new>`

Rename a template on a machine. Updates hook file directories and updates all projects
that referenced the old template name.

```bash
colette config rename-template local old-name new-name
```

#### `colette config sync-remote [machine]`

Manually sync the local colette binary (and config snapshot) to one or all remote
machines. Requires `colette_path` to be set on the machine (set it via
`colette config edit-machine`).

```bash
colette config sync-remote            # all remote machines
colette config sync-remote my-server  # one machine
```

This sync also happens automatically on every command that SSHs to a remote machine.

#### `colette config remove-template <machine> <template>`

Remove a template from a machine. Deletes hook files if no other machine uses
the same template name.

```bash
colette config remove-template local my-template
```

#### `colette config remove-machine <machine>`

Remove a machine from the configuration.

```bash
colette config remove-machine old-server
```

#### `colette config set-default <machine>`

Set the default machine used when `-m` is not specified.

```bash
colette config set-default local
```

---

### `colette create` — create a project

```
colette create <name> [-m <machine>] [-t <template>]
```

Creates a new project directory on the target machine by copying a template
directory or cloning a git repository. Runs the `oncreate` hook after creation.

```bash
colette create my-project
colette create my-project -m local -t my-template
```

---

### `colette link` — link an existing directory

```
colette link <path> [-m <machine>] [-n <name>]
```

Register an existing directory as a project without copying any template.

```bash
colette link /home/user/existing-project
colette link /home/user/existing-project -m local -n my-project
```

---

### `colette unlink` — remove a project from colette

```
colette unlink <name>
```

Removes the project from colette's registry **without deleting any files**. Use
this when you want to stop managing a project with colette while keeping all the
files on disk. For full deletion of both the record and the files, use
`colette delete`.

```bash
colette unlink my-project
```

---

### `colette delete` — delete a project

```
colette delete <name>
```

Removes the project directory and its registration. Asks for confirmation by
requiring the project name to be typed.

```bash
colette delete my-project
```

---

### `colette list` — list projects

```
colette list
```

List all registered projects grouped by machine.

---

### Current-directory detection

Most commands that accept an optional project `<name>` will automatically detect the
project from the current working directory when the name is omitted:

```bash
cd ~/projects/my-project
colette attach      # same as: colette attach my-project
colette start       # same as: colette start my-project
colette stop        # same as: colette stop my-project
colette code        # same as: colette code my-project
colette copilot     # same as: colette copilot my-project
colette delete      # same as: colette delete my-project
colette unlink      # same as: colette unlink my-project
colette monitor     # same as: colette monitor my-project
colette update      # same as: colette update my-project
colette logs        # same as: colette logs my-project
```

If the current directory is not a registered project path, batch commands (`start`,
`stop`, `monitor`, `update`) fall back to acting on all projects; single-name commands
(`attach`, `code`, `copilot`, `delete`, `unlink`) print their usage instead.

---

### `colette start` — start tmux sessions

```
colette start [-m <machine>] [<projects>...]
```

Create tmux sessions for projects (if not already running) and run the
`onstart` hook for each.

```bash
colette start                          # all projects on all machines
colette start -m local                 # all local projects
colette start my-project other-project # specific projects
```

---

### `colette stop` — stop tmux sessions

```
colette stop [-m <machine>] [<projects>...]
```

Run the `onstop` hook and kill tmux sessions.

```bash
colette stop
colette stop -m local my-project
```

---

### `colette attach` — attach to a session

```
colette attach <name>
```

Attach to (or create) the tmux session for a project, loading the `coletterc`
environment. If already inside tmux, switches to the session.

```bash
colette attach my-project
```

---

### `colette tui` — interactive TUI

```
colette tui
```

Launch a full-screen interactive terminal UI. Navigate with arrow keys:

| Key | Action |
|---|---|
| ↑ / ↓ | Move selection |
| → / Enter | Go deeper / select |
| ← / Escape | Go back |
| `q` | Quit |

All text input (project names, confirmations, parameter values) happens inside
the TUI via overlay forms — the terminal is never suspended for user input.

**Screens:**
- **Projects** — lists all projects grouped by machine. Selecting a project
  offers: *Open session*, *Code*, *Logs*, *Start*, *Stop*, *Edit hooks*,
  *Unlink*, *Delete*.
- **Templates** — lists all configured templates. Selecting a template offers:
  *Create project* (runs async — a desktop notification fires when done),
  *Edit hooks*, *Edit parameters*.
- **Config** — manage machines and their templates/parameters.
- **Monitor** — open a split-pane tmux window for all active project sessions.

**Async operations:** *Create project* and *Delete project* run in the
background. The footer shows `⏳ N job(s) running…` while they are in
progress; a desktop notification (`notify-send` on Linux, `osascript` on
macOS) fires when each job completes.

```bash
colette tui
```

---

### `colette monitor` — watch multiple sessions

```
colette monitor [-m <machine>] [--copilot | --all] [<projects>...]
```

Open a tmux window with read-only panes attached to each project session.
Only projects with an already-running tmux session are shown; idle projects
are skipped.

| Flag | Behaviour |
|------|-----------|
| *(none)* | Standard `<project>` sessions |
| `--copilot` | `<project>-copilot` sessions (local machines only) |
| `--all` | All active sessions (standard + copilot + logs) with **one row per project** |

With `--all`, each project occupies a horizontal band in the monitor window.
Sessions for the same project (standard, copilot, logs) appear as side-by-side
panes within that band.

```bash
colette monitor
colette monitor -m local project-a project-b
colette monitor --copilot
colette monitor --all
```

---

### `colette update` — run the onupdate hook

```
colette update [<project> ...] [-m <machine>]
```

Run the `onupdate` hook for one or more projects. Use this to update projects
(e.g. pull the latest code, rebuild dependencies).

```bash
colette update my-project
colette update                # all projects
colette update -m my-server   # all projects on a machine
```

To run `onupdate` directly on a template (without a project), use:

```bash
colette config run-template-update my-template
```

---

### `colette logs` — run the onlogs hook

```
colette logs [<name>] [-m <machine>]
```

Run the `onlogs` hook interactively in a tmux session. Without a project name,
opens a multi-pane window showing logs for all projects that have an `onlogs`
hook.

```bash
colette logs my-project
colette logs                # all projects with an onlogs hook
colette logs -m my-server
```

---

### `colette code` — open in VS Code

```
colette code <name>
```

Open the project in VS Code. Uses the Remote SSH extension for remote machines.
Also works with a **template name** — opens the template's source directory.

```bash
colette code my-project
colette code my-template   # opens the template's source directory
```

---

### `colette copilot` — open in GitHub Copilot

```
colette copilot <name>
```

Open the project in GitHub Copilot inside a dedicated tmux session named
`<project>-copilot`. Works for both local and remote machines (the `copilot`
CLI must be installed on the remote machine).

**Behaviour:**
- If the `<project>-copilot` tmux session is already running, colette switches
  to it (no new Copilot instance is launched).
- Otherwise, a numbered picker lists known previous Copilot sessions for the
  project (read from `.github/copilot-sessions`). You can resume any closed
  session or start a new one. New session IDs are recorded automatically.

```bash
colette copilot my-project
```

---

### `colette debug` — debug utilities

```
colette debug <action> [options]
```

Debug sub-commands for inspecting Colette internals.

#### `colette debug hook-log` — show hook failure log

```
colette debug hook-log [--project <name>] [--clear]
```

Displays the log of hook scripts (onstart, onstop, oncreate, …) that exited with a
non-zero status. Entries are stored in `~/.config/colette/hook-failures.json`
(last 200 kept).

```bash
# Show all failures
colette debug hook-log

# Show failures for a specific project
colette debug hook-log --project my-project

# Clear the log
colette debug hook-log --clear
```

In the TUI, the same log is accessible under **Debug → Hook log** in the main menu.

---

## Hook System

Hooks are shell scripts stored in `~/.config/colette/templates/<template>/`.
They are automatically invoked by Colette at lifecycle events.

### Hook types

| Hook | File | Trigger | Mode |
|---|---|---|---|
| `oncreate` | `.oncreate` | After `colette create` | Non-interactive |
| `onstart` | `.onstart` | After `colette start` | Non-interactive |
| `onstop` | `.onstop` | Before `colette stop` | Non-interactive |
| `onlogs` | `.onlogs` | `colette logs` | Interactive (tmux) |
| `onupdate` | `.onupdate` | `colette update` / `colette config run-template-update` | Non-interactive |
| `ondelete` | `.ondelete` | Before `colette delete` (files are removed after the hook) | Non-interactive |
| `coletterc` | `.coletterc` | Before every hook and on session bootstrap | Sourced (not executed) |

`coletterc` is the base common hook. It is sourced automatically before every
other hook script runs, and it is also applied when opening a terminal with
`colette attach` or `colette start`. This makes it the right place to activate
a virtualenv, set environment variables, or perform any per-project setup.

> **Venv note**: `coletterc` is applied *after* `~/.bashrc` when bootstrapping
> an interactive terminal, so venv activations defined in `coletterc` are never
> overwritten by the shell's rc file.

### Hook environment variables

Every hook receives these environment variables:

| Variable | Value |
|---|---|
| `COLETTE_PROJECT_NAME` | Project name |
| `COLETTE_PROJECT_PATH` | Absolute path on the target machine |
| `COLETTE_MACHINE_NAME` | Machine name |
| `COLETTE_TEMPLATE_NAME` | Template name (empty if no template) |
| `COLETTE_PARAM_<KEY>` | Template parameter values |

When `onupdate` is run directly on a template (via `colette config run-template-update`),
only `COLETTE_TEMPLATE_NAME`, `COLETTE_MACHINE_NAME`, and `COLETTE_PARAM_*` are set.
For directory-type templates `COLETTE_TEMPLATE_PATH` is also set to the template source path.

### Project-specific hook overrides

Place a hook file in `~/.config/colette/projects/<project-name>/` to override
the template hook for that specific project. The project hook takes full
precedence; the template hook is not run unless explicitly invoked.

To call the template hook from a project hook, use the `$SUPER` variable:

```bash
#!/usr/bin/env bash
# Run the template hook first (inheritance)
source "$SUPER"
# Then add project-specific steps
export MY_EXTRA_VAR=1
```

`$SUPER` is set by Colette to the path of the corresponding template hook file
whenever a project-level override is active. It is not set for template-level
hooks (to avoid self-sourcing).

```
~/.config/colette/
  templates/
    my-template/
      .oncreate      ← used by all projects with this template
      .onstart
      .onstop
      .onlogs
      .onupdate
      .coletterc
  projects/
    my-project/
      .onstart       ← overrides template .onstart for my-project only
```

### Editing hook scripts

```bash
# Open a template hook in nano
colette config edit-hook my-template onstart

# Or edit directly
nano ~/.config/colette/templates/my-template/.onstart
```

### Template parameters

Parameters are declared when adding or editing a template and passed to hooks as
`COLETTE_PARAM_<KEY>` environment variables.

```bash
colette config add-template local my-template --param ENV=dev --param PORT=8080
```

Inside a hook script:

```bash
#!/usr/bin/env bash
echo "Environment: $COLETTE_PARAM_ENV"
echo "Port: $COLETTE_PARAM_PORT"
```

---

## SSH machine setup

```bash
colette config add-machine
# Name:         my-server
# Type:         ssh
# SSH host:     user@192.168.1.10   (or an SSH config alias)
# SSH port:     24                  (optional, leave empty for default 22)
# SSH key:      ~/.ssh/id_ed25519   (optional)
# projects_dir: /home/user/projects
```

Colette uses SSH for all operations on remote machines: project creation,
hook execution, and tmux session management.

---

## Example workflow

```bash
# 1. Configure a local machine and template
colette config add-machine
colette config add-template local my-template

# 2. Edit the startup hook
colette config edit-hook my-template onstart

# 3. Create and start a project
colette create my-project -m local -t my-template
colette start my-project

# 4. Watch it
colette monitor my-project

# 5. View logs
colette logs my-project

# 6. Stop when done
colette stop my-project
```
