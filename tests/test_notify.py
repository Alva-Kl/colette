"""Tests for colette_cli.utils.notify — desktop notification helper."""

import sys
from unittest.mock import patch, call

# Capture the real implementation at import time, before the conftest autouse
# fixture replaces it with a no-op.  Tests in this module must use this
# reference so they exercise the actual logic.
import colette_cli.utils.notify as _notify_mod
_real_send_notification = _notify_mod.send_notification


class TestSendNotification:
    def test_linux_calls_notify_send(self):
        with patch("sys.platform", "linux"), \
             patch("shutil.which", return_value="/usr/bin/notify-send"), \
             patch("subprocess.run") as mock_run:
            _real_send_notification("Title", "Body")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "notify-send"
        assert "Title" in args
        assert "Body" in args

    def test_linux_no_notify_send_is_noop(self):
        with patch("sys.platform", "linux"), \
             patch("shutil.which", return_value=None), \
             patch("subprocess.run") as mock_run:
            _real_send_notification("Title", "Body")
        mock_run.assert_not_called()

    def test_macos_calls_osascript(self):
        with patch("sys.platform", "darwin"), \
             patch("subprocess.run") as mock_run:
            _real_send_notification("Title", "Body")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "osascript"
        assert "display notification" in args[2]
        assert "Title" in args[2]
        assert "Body" in args[2]

    def test_unknown_platform_is_noop(self):
        with patch("sys.platform", "win32"), \
             patch("subprocess.run") as mock_run:
            _real_send_notification("Title", "Body")
        mock_run.assert_not_called()

    def test_never_raises_on_subprocess_error(self):
        """Notification failure must be swallowed silently."""
        with patch("sys.platform", "linux"), \
             patch("shutil.which", return_value="/usr/bin/notify-send"), \
             patch("subprocess.run", side_effect=OSError("fail")):
            # Should not raise
            _real_send_notification("Title", "Body")

    def test_empty_body_allowed(self):
        with patch("sys.platform", "linux"), \
             patch("shutil.which", return_value="/usr/bin/notify-send"), \
             patch("subprocess.run") as mock_run:
            _real_send_notification("Title")
        mock_run.assert_called_once()
