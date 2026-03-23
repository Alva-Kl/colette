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
| `remove-template <machine> <template>` | Remove a template from a machine |
| `remove-machine <machine>` | Remove a machine |
| `set-default <machine>` | Set the default machine |

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
# Prompts: name, type (local/ssh), SSH host/key (if ssh), projects_dir, initial template
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
colette config edit-hook my-template coletterc
```

Valid hook names: `oncreate`, `onstart`, `onstop`, `onlogs`, `coletterc`.

#### `colette config edit-project-hook <project> <hook>`

Open a project-specific hook override script in `nano` for editing. Scaffolds
the project's hook directory under `~/.config/colette/projects/<project>/` if
needed. The project must already be registered with colette.

```bash
colette config edit-project-hook my-project onstart
colette config edit-project-hook my-project onlogs
```

Valid hook names: `oncreate`, `onstart`, `onstop`, `onlogs`, `coletterc`.

Project-level hooks take full precedence over the template hook for that event.

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

**Screens:**
- **Projects** — lists all projects grouped by machine. Selecting a project offers: *Open session*, *Code*, *Edit config* (hook scripts).
- **Templates** — lists all configured templates. Selecting a template offers: *Create project*, *Edit config* (hook scripts).

```bash
colette tui
```

---

### `colette monitor` — watch multiple sessions

```
colette monitor [-m <machine>] [<projects>...]
```

Open a tmux window with read-only panes attached to each project session.
Sessions that are not running are started automatically.

```bash
colette monitor
colette monitor -m local project-a project-b
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

```bash
colette code my-project
```

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
