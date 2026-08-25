#!/usr/bin/env python3
"""Seed a fake $HOME with a colette config + fake projects/templates.

Used by both sandbox containers' entrypoint.sh (once, idempotently) so
neither ever needs to touch the real host's ~/.config/colette or
~/colette-projects. Colette's config dir is hardcoded to
Path.home() / ".config" / "colette" (colette_cli/utils/config.py) with no
env override, so a container's own $HOME is the only isolation mechanism —
this script builds one from scratch.

--role sandbox: the machine the TUI/harness runs in. Gets a "local" machine
  plus (if reachable) an "ssh-target" remote machine entry.
--role target:  the remote machine. Gets only its own "local" machine entry
  (required for `colette debug self-report` to have something to report).
"""
import argparse
import json
import os
import shutil
from pathlib import Path

HOOK_VAR_DOCS = """\
# Available Colette environment variables:
# $COLETTE_PROJECT_NAME  — name of the project
# $COLETTE_PROJECT_PATH  — absolute path to the project directory
# $COLETTE_MACHINE_NAME  — name of the configured machine
# $COLETTE_TEMPLATE_NAME — name of the template used by the project
# $SUPER                 — path to parent hook
"""

# Lightweight fake hooks — echo/touch/sleep only, no real Docker, per the
# sandbox's "fake projects" design.
FAKE_HOOKS = {
    "oncreate": (
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'echo "[fake] oncreate for $COLETTE_PROJECT_NAME"\n'
        'touch "$COLETTE_PROJECT_PATH/.oncreate-ran"\n'
    ),
    "onstart": (
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'echo "[fake] onstart for $COLETTE_PROJECT_NAME"\n'
        "sleep 1\n"
        'echo "[fake] started"\n'
    ),
    "onstop": (
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'echo "[fake] onstop for $COLETTE_PROJECT_NAME"\n'
        'echo "[fake] stopped"\n'
    ),
    "onlogs": (
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'echo "[fake] tailing logs for $COLETTE_PROJECT_NAME (Ctrl+C to stop)"\n'
        "sleep 3600\n"
    ),
    "coletterc": HOOK_VAR_DOCS + 'source "$SUPER" 2>/dev/null || true\n',
}

FAKE_PROJECT_NAMES = ["fake-web-app", "fake-api"]

# Deliberately NOT a valid colette slug (space + capital letters) and
# deliberately NOT registered in projects.json — a plain directory meant to
# be linked via the TUI's "Link project" flow. Reproduces the historical
# ESC-cancel crash: cancelling the "Project name" prompt used to fall back
# to this raw basename, which fails validate_project_name() and used to
# crash the whole TUI via an uncaught SystemExit from cmd_link.
FAKE_LINKED_DIR_NAME = "Fake Linked Dir"


def seed(home: Path, role: str, force: bool) -> None:
    config_dir = home / ".config" / "colette"
    config_file = config_dir / "config.json"
    if config_file.exists() and not force:
        print(f"{config_file} already exists — skipping seed (pass --force to re-seed)")
        return

    projects_dir = home / "colette-projects"
    templates_dir = home / "colette-templates"
    projects_dir.mkdir(parents=True, exist_ok=True)
    templates_dir.mkdir(parents=True, exist_ok=True)

    fixture_src = Path(__file__).parent / "fixtures" / "fake-template"
    template_dst = templates_dir / "fake-template"
    if not template_dst.exists():
        shutil.copytree(fixture_src, template_dst)

    machines = {
        "local": {
            "type": "local",
            "projects_dir": str(projects_dir),
            "templates": [
                {"name": "fake-template", "type": "directory", "path": str(template_dst)},
            ],
        }
    }

    if role == "sandbox":
        machines["ssh-target"] = {
            "type": "ssh",
            "host": "root@ssh-target",
            "ssh_key": str(home / ".ssh" / "id_ed25519"),
            "colette_path": "/root/.local/bin/colette",
        }

    config = {"default_machine": "local", "machines": machines}

    projects = []
    for name in FAKE_PROJECT_NAMES:
        path = projects_dir / name
        path.mkdir(parents=True, exist_ok=True)
        projects.append({
            "name": name,
            "machine": "local",
            "path": str(path),
            "template": "fake-template",
        })

    linked_path = projects_dir / FAKE_LINKED_DIR_NAME
    linked_path.mkdir(parents=True, exist_ok=True)

    config_dir.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(config, indent=2) + "\n")
    (config_dir / "projects.json").write_text(json.dumps(projects, indent=2) + "\n")

    hook_dir = config_dir / "templates" / "fake-template"
    hook_dir.mkdir(parents=True, exist_ok=True)
    for hook_name, content in FAKE_HOOKS.items():
        hook_path = hook_dir / f".{hook_name}"
        hook_path.write_text(content)
        hook_path.chmod(0o644 if hook_name == "coletterc" else 0o755)

    print(f"Seeded {config_file} (role={role})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", default=os.environ.get("HOME", "/root"))
    parser.add_argument("--role", choices=["sandbox", "target"], default="sandbox")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    seed(Path(args.home), args.role, args.force)
