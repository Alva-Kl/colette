"""Cross-platform desktop notification helper."""

import shutil
import subprocess
import sys


def send_notification(title: str, body: str = "") -> None:
    """Send a desktop notification. Silently no-ops if unsupported."""
    try:
        if sys.platform.startswith("linux") and shutil.which("notify-send"):
            subprocess.run(
                ["notify-send", title, body],
                capture_output=True,
            )
        elif sys.platform == "darwin":
            script = (
                f'display notification {_applescript_quote(body)} '
                f'with title {_applescript_quote(title)}'
            )
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
            )
    except Exception:
        pass


def _applescript_quote(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
