#!/usr/bin/env bash
# Shared entrypoint for both sandbox containers (SANDBOX_ROLE picks the branch).
# Idempotent: safe to restart either container without losing manual poking
# done inside the bind-mounted sandbox/state/*-home directories.
set -euo pipefail

: "${SANDBOX_ROLE:?SANDBOX_ROLE must be set to 'sandbox' or 'ssh-target'}"

if [ "$SANDBOX_ROLE" = "sandbox" ]; then
    # Dev/test dependencies for the *current* working tree — installed at
    # every start (not baked into the image) so requirements-dev.txt edits
    # are picked up without a rebuild. Colette's unit tests run only in
    # here, never on the host.
    pip install --quiet --no-cache-dir -r /workspace/requirements-dev.txt
    python3 /workspace/sandbox/seed_home.py --role sandbox
    python3 /workspace/sandbox/provision_ssh.py
    # `docker compose up -d` returns as soon as this process starts, not once
    # it's actually done initializing — this marker lets callers (the
    # Makefile's sandbox-up target) poll for real readiness instead of
    # racing pip/seed/ssh setup.
    touch /tmp/.sandbox-ready
    echo "colette sandbox ready — docker compose exec sandbox bash"
    exec sleep infinity
else
    python3 /workspace/sandbox/seed_home.py --role target
    mkdir -p /run/sshd
    exec /usr/sbin/sshd -D -e
fi
