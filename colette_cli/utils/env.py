"""Environment file (.env) management utilities."""

import re
from pathlib import Path
from .ssh import ssh_run
from .formatting import warn


def _env_upsert_local(env_path, variables):
    """Set key=value pairs in a local .env file; create file if missing."""
    env_path = Path(env_path)
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    found = {k: False for k in variables}
    new_lines = []
    for line in lines:
        matched = False
        for key in list(variables):
            if re.match(rf"^{re.escape(key)}\s*=", line):
                new_lines.append(f"{key}={variables[key]}")
                found[key] = True
                matched = True
                break
        if not matched:
            new_lines.append(line)
    for key, value in variables.items():
        if not found[key]:
            new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines) + "\n")


def _env_upsert_remote(machine, env_path, variables):
    """Set key=value pairs in a remote .env file via SSH."""
    parts = []
    for key, value in variables.items():
        parts.append(
            f"if grep -qE '^{key}\\s*=' {env_path} 2>/dev/null; then "
            f"sed -i 's|^{key}\\s*=.*|{key}={value}|' {env_path}; "
            f"else echo '{key}={value}' >> {env_path}; fi"
        )
    result = ssh_run(machine, " && ".join(parts))
    if result.returncode != 0:
        warn(f"could not update .env on remote: {result.stderr.strip()}")


def env_upsert(machine, env_path, variables, is_remote=False):
    """Set key=value pairs in .env file (local or remote)."""
    if is_remote:
        _env_upsert_remote(machine, env_path, variables)
    else:
        _env_upsert_local(env_path, variables)
