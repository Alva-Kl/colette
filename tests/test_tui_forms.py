"""Tests for colette_cli.tui.forms — in-TUI overlay form widgets."""

import pytest
from unittest.mock import MagicMock, patch, call
import curses


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stdscr(height=24, width=80):
    """Return a MagicMock that behaves like a minimal curses window."""
    scr = MagicMock()
    scr.getmaxyx.return_value = (height, width)
    return scr


# ---------------------------------------------------------------------------
# ask()
# ---------------------------------------------------------------------------

class TestAsk:
    def test_returns_none_when_stdscr_is_none(self, monkeypatch):
        """With no stdscr, ask() falls back to input() and returns the text."""
        import colette_cli.tui.state as state
        state.stdscr = None
        from colette_cli.tui.forms import ask
        with patch("builtins.input", return_value="hello"):
            result = ask("Prompt")
        assert result == "hello"

    def test_returns_default_when_input_empty_and_stdscr_none(self, monkeypatch):
        import colette_cli.tui.state as state
        state.stdscr = None
        from colette_cli.tui.forms import ask
        with patch("builtins.input", return_value=""):
            result = ask("Prompt", default="fallback")
        assert result == "fallback"

    def test_returns_none_when_input_empty_and_no_default(self):
        import colette_cli.tui.state as state
        state.stdscr = None
        from colette_cli.tui.forms import ask
        with patch("builtins.input", return_value=""):
            result = ask("Prompt")
        assert result is None

    def test_curses_path_enter_returns_typed_text(self):
        """With a mock stdscr, typing text + Enter returns that text."""
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        # Simulate: type 'a', 'b', 'c', then Enter
        key_seq = [ord("a"), ord("b"), ord("c"), ord("\n")]
        mock_win = MagicMock()
        mock_win.getch.side_effect = key_seq
        mock_win.getmaxyx.return_value = (6, 52)

        from colette_cli.tui.forms import ask
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = ask("Name")

        assert result == "abc"

    def test_curses_path_esc_returns_none(self):
        """Pressing ESC returns None."""
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        mock_win = MagicMock()
        mock_win.getch.side_effect = [27]  # ESC
        mock_win.getmaxyx.return_value = (6, 52)

        from colette_cli.tui.forms import ask
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = ask("Name")

        assert result is None

    def test_curses_path_backspace_deletes(self):
        """Backspace removes the previous character."""
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        # type 'a', 'b', backspace, Enter → should return "a"
        key_seq = [ord("a"), ord("b"), curses.KEY_BACKSPACE, ord("\n")]
        mock_win = MagicMock()
        mock_win.getch.side_effect = key_seq
        mock_win.getmaxyx.return_value = (6, 52)

        from colette_cli.tui.forms import ask
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = ask("Name")

        assert result == "a"

    def test_curses_path_enter_on_empty_returns_default(self):
        """Enter on empty input returns the default."""
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        mock_win = MagicMock()
        mock_win.getch.side_effect = [ord("\n")]
        mock_win.getmaxyx.return_value = (6, 52)

        from colette_cli.tui.forms import ask
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = ask("Name", default="mydefault")

        assert result == "mydefault"


# ---------------------------------------------------------------------------
# confirm()
# ---------------------------------------------------------------------------

class TestConfirm:
    def test_returns_default_when_stdscr_none_and_no_input(self):
        import colette_cli.tui.state as state
        state.stdscr = None
        from colette_cli.tui.forms import confirm
        with patch("builtins.input", return_value=""):
            result = confirm("Sure?", default=True)
        assert result is True

    def test_y_returns_true_when_stdscr_none(self):
        import colette_cli.tui.state as state
        state.stdscr = None
        from colette_cli.tui.forms import confirm
        with patch("builtins.input", return_value="y"):
            result = confirm("Sure?")
        assert result is True

    def test_n_returns_false_when_stdscr_none(self):
        import colette_cli.tui.state as state
        state.stdscr = None
        from colette_cli.tui.forms import confirm
        with patch("builtins.input", return_value="n"):
            result = confirm("Sure?", default=True)
        assert result is False

    def test_curses_y_returns_true(self):
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        mock_win = MagicMock()
        mock_win.getch.return_value = ord("y")
        mock_win.getmaxyx.return_value = (5, 44)

        from colette_cli.tui.forms import confirm
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = confirm("Delete it?")

        assert result is True

    def test_curses_esc_returns_false(self):
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        mock_win = MagicMock()
        mock_win.getch.return_value = 27  # ESC
        mock_win.getmaxyx.return_value = (5, 44)

        from colette_cli.tui.forms import confirm
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = confirm("Delete it?")

        assert result is False

    def test_curses_enter_returns_default(self):
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        mock_win = MagicMock()
        mock_win.getch.return_value = ord("\n")
        mock_win.getmaxyx.return_value = (5, 44)

        from colette_cli.tui.forms import confirm
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = confirm("Delete it?", default=True)

        assert result is True


# ---------------------------------------------------------------------------
# type_to_confirm()
# ---------------------------------------------------------------------------

class TestTypeToConfirm:
    def test_returns_true_on_correct_text_when_stdscr_none(self):
        import colette_cli.tui.state as state
        state.stdscr = None
        from colette_cli.tui.forms import type_to_confirm
        with patch("builtins.input", return_value="my-project"):
            result = type_to_confirm("Delete?", expected="my-project")
        assert result is True

    def test_returns_false_on_wrong_text_when_stdscr_none(self):
        import colette_cli.tui.state as state
        state.stdscr = None
        from colette_cli.tui.forms import type_to_confirm
        with patch("builtins.input", return_value="wrong"):
            result = type_to_confirm("Delete?", expected="my-project")
        assert result is False

    def test_curses_correct_text_plus_enter_returns_true(self):
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        # type 'm','y',Enter
        key_seq = [ord("m"), ord("y"), ord("\n")]
        mock_win = MagicMock()
        mock_win.getch.side_effect = key_seq
        mock_win.getmaxyx.return_value = (8, 52)

        from colette_cli.tui.forms import type_to_confirm
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = type_to_confirm("Delete?", expected="my")

        assert result is True

    def test_curses_esc_returns_false(self):
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        mock_win = MagicMock()
        mock_win.getch.return_value = 27
        mock_win.getmaxyx.return_value = (8, 52)

        from colette_cli.tui.forms import type_to_confirm
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = type_to_confirm("Delete?", expected="my-project")

        assert result is False

    def test_curses_wrong_text_enter_sets_mismatch_and_continues(self):
        """Pressing Enter with wrong text doesn't confirm; ESC eventually cancels."""
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        # type 'x', Enter (wrong), then ESC
        key_seq = [ord("x"), ord("\n"), 27]
        mock_win = MagicMock()
        mock_win.getch.side_effect = key_seq
        mock_win.getmaxyx.return_value = (8, 52)

        from colette_cli.tui.forms import type_to_confirm
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = type_to_confirm("Delete?", expected="my-project")

        assert result is False
