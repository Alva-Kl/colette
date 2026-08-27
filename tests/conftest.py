"""Shared fixtures for the Colette test suite."""

import json
import subprocess

import pytest


@pytest.fixture(autouse=True)
def block_real_ssh_subprocess(monkeypatch):
    """Fail fast and loud on any unmocked real `ssh` subprocess call.

    Every module calls it as `subprocess.run(...)` after a plain `import
    subprocess`, so patching the shared attribute covers every call site.
    A test that legitimately exercises ssh.py/tmux.py's own subprocess calls
    patches `subprocess.run` (or a higher-level function) itself — that local
    patch wins for the duration of its `with` block, then this guard resumes.

    Without this, a missing mock doesn't fail — it just silently blocks for
    up to the OS's default TCP connect timeout (~130s on Linux) trying to
    reach a fake host, which is how the suite quietly grew to ~5 minutes.
    """
    real_run = subprocess.run

    def guarded_run(args, *a, **kw):
        if isinstance(args, (list, tuple)) and args and args[0] == "ssh":
            raise AssertionError(
                f"real `ssh` subprocess call attempted in a test: {args!r} — "
                "mock the relevant colette_cli.utils.ssh/tmux function instead."
            )
        return real_run(args, *a, **kw)

    monkeypatch.setattr(subprocess, "run", guarded_run)


@pytest.fixture(autouse=True)
def suppress_notifications(monkeypatch):
    """Suppress real desktop notifications during every test."""
    noop = lambda *a, **kw: None
    monkeypatch.setattr("colette_cli.utils.notify.send_notification", noop)


@pytest.fixture(autouse=True)
def interactive_stdin(monkeypatch):
    """Make colette_cli.utils.helpers.prompt() behave like plain input() by
    default, since pytest's captured stdin isn't a real terminal.

    prompt() falls back to '' (skip/keep-default) instead of calling input()
    when stdin isn't a tty, so a script/agent invocation that omits a value
    degrades gracefully instead of raising EOFError. Tests exercising that
    non-interactive behavior explicitly re-patch isatty() to False.
    """
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)


@pytest.fixture(autouse=True)
def reset_tui_state():
    """Reset shared TUI module state before and after every test."""
    import colette_cli.tui.state as tui_state
    tui_state.stdscr = None
    yield
    tui_state.stdscr = None


@pytest.fixture()
def tmp_config(tmp_path, monkeypatch):
    """Redirect all colette config paths to a temporary directory."""
    config_dir = tmp_path / ".config" / "colette"
    config_dir.mkdir(parents=True)
    projects_dir = config_dir / "projects"
    projects_dir.mkdir()

    import colette_cli.utils.config as cfg_mod

    machines_dir = config_dir / "machines"
    machines_dir.mkdir()
    cache_dir = config_dir / "cache"
    cache_dir.mkdir()

    monkeypatch.setattr(cfg_mod, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", config_dir / "config.json")
    monkeypatch.setattr(cfg_mod, "PROJECTS_FILE", config_dir / "projects.json")
    monkeypatch.setattr(cfg_mod, "PROJECT_HOOKS_DIR", projects_dir)
    monkeypatch.setattr(cfg_mod, "HOOK_FAILURES_FILE", config_dir / "hook-failures.json")
    monkeypatch.setattr(cfg_mod, "MACHINE_SCRIPTS_DIR", machines_dir)
    monkeypatch.setattr(cfg_mod, "CACHE_DIR", cache_dir)

    return config_dir


def write_config(config_dir, cfg):
    (config_dir / "config.json").write_text(json.dumps(cfg))


def write_projects(config_dir, projects):
    (config_dir / "projects.json").write_text(json.dumps(projects))


def write_machine_cache(config_dir, machine_name, data):
    cache_dir = config_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{machine_name}.json").write_text(json.dumps(data))


def make_local_machine(projects_dir="/tmp/projects"):
    return {"type": "local", "projects_dir": projects_dir, "templates": []}


def make_project(name="proj", machine="local", path="/tmp/projects/proj", template=None):
    return {"name": name, "machine": machine, "path": path, "template": template}
