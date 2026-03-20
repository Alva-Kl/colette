"""Tests for colette_cli.utils.formatting."""

import sys
import pytest
from unittest.mock import patch


class TestTextFormatters:
    """When not a TTY, formatters return plain text (no ANSI codes)."""

    def test_bold_no_color(self):
        from colette_cli.utils.formatting import bold
        with patch("colette_cli.utils.formatting._COL_OUT", False):
            assert bold("hello") == "hello"

    def test_dim_no_color(self):
        from colette_cli.utils.formatting import dim
        with patch("colette_cli.utils.formatting._COL_OUT", False):
            assert dim("x") == "x"

    def test_cyan_no_color(self):
        from colette_cli.utils.formatting import cyan
        with patch("colette_cli.utils.formatting._COL_OUT", False):
            assert cyan("x") == "x"

    def test_bold_with_color(self):
        from colette_cli.utils.formatting import bold
        with patch("colette_cli.utils.formatting._COL_OUT", True):
            result = bold("hi")
            assert "\033[1m" in result
            assert "hi" in result

    def test_red_no_color(self):
        from colette_cli.utils.formatting import red
        with patch("colette_cli.utils.formatting._COL_ERR", False):
            assert red("oops") == "oops"


class TestErrWarnInfo:
    def test_err_exits_with_1(self, capsys):
        from colette_cli.utils.formatting import err
        with pytest.raises(SystemExit) as exc:
            err("something went wrong")
        assert exc.value.code == 1

    def test_err_prints_to_stderr(self, capsys):
        from colette_cli.utils.formatting import err
        with pytest.raises(SystemExit):
            err("bad thing")
        captured = capsys.readouterr()
        assert "bad thing" in captured.err

    def test_warn_prints_to_stderr(self, capsys):
        from colette_cli.utils.formatting import warn
        warn("heads up")
        captured = capsys.readouterr()
        assert "heads up" in captured.err

    def test_info_prints_to_stdout(self, capsys):
        from colette_cli.utils.formatting import info
        info("all good")
        captured = capsys.readouterr()
        assert "all good" in captured.out
