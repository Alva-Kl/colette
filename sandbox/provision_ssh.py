#!/usr/bin/env python3
"""Provision passwordless SSH from the sandbox container to ssh-target.

Run once (idempotent) by the sandbox container's entrypoint.sh. Both
containers' $HOME dirs are bind-mounted from the same host tree
(sandbox/state/sandbox-home, sandbox/state/ssh-target-home) and the sandbox
container additionally mounts ssh-target's home at /ssh-target-home
(docker-compose.yml), so this script can write ssh-target's authorized_keys
directly — no SSH round-trip needed to bootstrap the connection.

colette_cli/utils/ssh.py never sets StrictHostKeyChecking, so the sync/
self-report paths (BatchMode=yes) need ssh-target's host key already in
known_hosts, or they'll fail outright rather than prompt.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

SANDBOX_HOME = Path(os.environ.get("HOME", "/root"))
SSH_TARGET_HOME = Path("/ssh-target-home")
SSH_TARGET_HOSTNAME = "ssh-target"


def main() -> None:
    ssh_dir = SANDBOX_HOME / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    key_path = ssh_dir / "id_ed25519"

    if not key_path.exists():
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(key_path),
             "-C", "sandbox-to-ssh-target"],
            check=True,
        )
        print(f"generated {key_path}")
    key_path.chmod(0o600)

    pubkey = (ssh_dir / "id_ed25519.pub").read_text().strip()

    target_ssh_dir = SSH_TARGET_HOME / ".ssh"
    target_ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    authorized_keys = target_ssh_dir / "authorized_keys"
    existing = authorized_keys.read_text() if authorized_keys.exists() else ""
    if pubkey not in existing:
        with authorized_keys.open("a") as f:
            f.write(pubkey + "\n")
    authorized_keys.chmod(0o600)

    known_hosts = ssh_dir / "known_hosts"
    existing_kh = known_hosts.read_text() if known_hosts.exists() else ""
    for attempt in range(30):
        result = subprocess.run(
            ["ssh-keyscan", "-T", "2", SSH_TARGET_HOSTNAME],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            if result.stdout.strip() not in existing_kh:
                with known_hosts.open("a") as f:
                    f.write(result.stdout)
            print(f"known_hosts populated for {SSH_TARGET_HOSTNAME}")
            break
        time.sleep(1)
    else:
        print(f"WARNING: could not reach {SSH_TARGET_HOSTNAME}'s sshd after 30s", file=sys.stderr)


if __name__ == "__main__":
    main()
