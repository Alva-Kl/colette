"""SSH utilities for connecting to remote machines."""

import subprocess


def _ssh_base_args(machine):
    """Build base SSH arguments from machine config."""
    args = ["ssh"]
    if "ssh_key" in machine:
        args += ["-i", machine["ssh_key"]]
    args.append(machine["host"])
    return args


def ssh_run(machine, remote_cmd):
    """Run a non-interactive command on a remote machine; return CompletedProcess."""
    return subprocess.run(
        _ssh_base_args(machine) + [remote_cmd],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def ssh_interactive(machine, remote_cmd):
    """Run a command on a remote machine with a TTY allocated."""
    cmd = ["ssh", "-t"]
    if "ssh_key" in machine:
        cmd += ["-i", machine["ssh_key"]]
    cmd += [machine["host"], remote_cmd]
    subprocess.run(cmd)
