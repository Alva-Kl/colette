"""Input validation utilities."""

import re

NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def validate_project_name(name):
    """Validate project name format. Returns True if valid."""
    return bool(NAME_RE.match(name))


def validate_machine_name(name):
    """Validate machine name format. Returns True if valid."""
    return bool(NAME_RE.match(name))
