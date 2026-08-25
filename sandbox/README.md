# Colette sandbox

A disposable, fully isolated Docker environment for testing the real
`colette` binary/TUI end-to-end — fake projects, fake templates, and an
optional fake SSH "remote machine" — without ever touching this host's live
`~/.config/colette` or `~/colette-projects`. See `DEVELOPMENT.md`'s "Sandbox"
section for the full rationale.

Two containers, both on a private `colette-sandbox-net` network, no ports
published anywhere:

- **`sandbox`** — where you actually run `colette tui`. Its `$HOME` is
  `sandbox/state/sandbox-home/` (bind-mounted, gitignored), seeded on first
  boot with a `local` machine plus a couple of fake projects/templates.
- **`ssh-target`** — a bare `sshd`, playing the role of a remote `type: ssh`
  machine so the SSH-driven code paths (`colette_cli/utils/ssh.py`) get
  exercised too, not just the local ones.

## Quick start

A `Makefile` at the repo root wraps the common commands:

```bash
# From the repo root:
make sandbox-up        # first run builds images; later runs just start them
make sandbox-build      # build + install the real colette binary inside the container
make test               # run the full pytest suite inside the container
make sandbox-shell      # drop into a shell in the sandbox container
make sandbox-rebuild    # force an image rebuild (after changing a Dockerfile)
make sandbox-down       # stop both containers
```

`sandbox-up`/`sandbox-build`/`sandbox-shell`/`test` all wait for the
container's entrypoint (seeding + SSH provisioning + installing
`requirements-dev.txt`) to actually finish before proceeding — `docker
compose up -d` alone returns as soon as the container *starts*, not once
it's ready.

The raw commands, if you'd rather not use `make`:

```bash
docker compose -f sandbox/docker-compose.yml up -d

# Build + install the real colette binary inside the sandbox container
# (reuses the project's own scripts, picks up any uncommitted edits since
# the repo is bind-mounted, not copied). Plain `./scripts/build.sh prod`
# never touches the version number — pass --bump only when you actually
# mean to cut a release (see DEVELOPMENT.md's Build pipeline section):
docker compose -f sandbox/docker-compose.yml exec sandbox bash -lc '
  cd /workspace && ./scripts/build.sh && ./scripts/build.sh prod && ./scripts/install.sh
'

# Interactive session:
docker compose -f sandbox/docker-compose.yml exec sandbox colette tui

# Or drive it non-interactively and check for a crash:
docker compose -f sandbox/docker-compose.yml exec sandbox \
  python3 sandbox/harness.py --scenario link-project-cancel-name
```

`sandbox/harness.py --list` prints the available scenarios. Exit code 0
(`OK` on stderr) means a clean run; exit code 1 (`CRASHED`) means the
transcript contained an unhandled Python traceback.

## Running the unit test suite

Colette's own dev/test workflow is Docker-only, same as every other project
on this host — never run `pytest`/`python3 -m pytest` directly on the host:

```bash
make test
```

`requirements-dev.txt` (pytest) is installed automatically by
`entrypoint.sh` on every `sandbox` container start, against the live
bind-mounted repo.

## Testing the SSH remote machine

The `sandbox` container's config already has an `ssh-target` machine entry
pointing at `colette_path: /root/.local/bin/colette` on `ssh-target` — but
that path doesn't exist there yet on first boot. Trigger colette's own real
provisioning path (`sync_remote_colette`) to install it, exactly like a real
user adding a new remote machine would:

```bash
docker compose -f sandbox/docker-compose.yml exec sandbox colette config sync ssh-target
```

This scp's the freshly-built zipapp over (via the actual `sync_remote_colette`
code path, not a shortcut) and pulls `ssh-target`'s own seeded fake
projects/templates into the sandbox's local cache. After that, "Create
project" / "Link project" / etc. against machine `ssh-target` exercise the
real remote-machine flow end-to-end.

## Resetting state

Both containers' fake `$HOME`s live under `sandbox/state/` (gitignored) and
persist across `docker compose restart`. For a fully clean slate:

```bash
make sandbox-down
rm -rf sandbox/state/sandbox-home sandbox/state/ssh-target-home
make sandbox-up
```

## Why this is safe to run on this host

- Everything lives under a container-local `$HOME` — colette's config dir
  is hardcoded to `Path.home() / ".config" / "colette"` with no env
  override, so a container's own `$HOME` is complete isolation.
- No ports are published on either container — nothing here is reachable
  from the host or the internet.
- A dedicated `colette-sandbox-net` Docker network, separate from the host's
  real `proxy` network used by Traefik and the live production stacks.
