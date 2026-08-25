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


class TestAskChoices:
    """Tests for ask() with the choices parameter."""

    def test_fallback_returns_first_choice_when_stdscr_none(self, monkeypatch):
        """When stdscr is None, ask() with choices falls back to stdin."""
        import colette_cli.tui.state as state
        state.stdscr = None

        from colette_cli.tui.forms import ask
        with patch("builtins.input", return_value="2"):
            result = ask("Pick", choices=["alpha", "beta", "gamma"])
        assert result == "beta"

    def test_fallback_returns_default_on_invalid_input(self, monkeypatch):
        """Invalid numeric input falls back to default."""
        import colette_cli.tui.state as state
        state.stdscr = None

        from colette_cli.tui.forms import ask
        with patch("builtins.input", return_value="xyz"):
            result = ask("Pick", default="beta", choices=["alpha", "beta", "gamma"])
        assert result == "beta"

    def test_fallback_returns_first_on_no_default_invalid(self, monkeypatch):
        """Invalid input with no matching default returns first choice."""
        import colette_cli.tui.state as state
        state.stdscr = None

        from colette_cli.tui.forms import ask
        with patch("builtins.input", return_value=""):
            result = ask("Pick", choices=["alpha", "beta"])
        assert result == "alpha"

    def test_empty_choices_returns_none(self, monkeypatch):
        """ask() with empty choices list returns None."""
        import colette_cli.tui.state as state
        state.stdscr = None

        from colette_cli.tui.forms import ask
        result = ask("Pick", choices=[])
        assert result is None

    def test_curses_enter_selects_current(self):
        """Pressing Enter selects the highlighted choice."""
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        mock_win = MagicMock()
        mock_win.getch.return_value = ord("\n")
        mock_win.getmaxyx.return_value = (20, 60)

        from colette_cli.tui.forms import ask
        with patch("curses.newwin", return_value=mock_win), \
             patch("colette_cli.tui.forms._restore"):
            result = ask("Pick", choices=["alpha", "beta", "gamma"])

        assert result == "alpha"  # first item selected by default

    def test_curses_default_preselected(self):
        """The item matching default is pre-selected."""
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        # DOWN then Enter → should select second item when default pre-selects it
        mock_win = MagicMock()
        mock_win.getch.return_value = ord("\n")
        mock_win.getmaxyx.return_value = (20, 60)

        from colette_cli.tui.forms import ask
        with patch("curses.newwin", return_value=mock_win), \
             patch("colette_cli.tui.forms._restore"):
            result = ask("Pick", default="gamma", choices=["alpha", "beta", "gamma"])

        assert result == "gamma"

    def test_curses_esc_returns_none(self):
        """ESC returns None."""
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        mock_win = MagicMock()
        mock_win.getch.return_value = 27
        mock_win.getmaxyx.return_value = (20, 60)

        from colette_cli.tui.forms import ask
        with patch("curses.newwin", return_value=mock_win), \
             patch("colette_cli.tui.forms._restore"):
            result = ask("Pick", choices=["alpha", "beta"])

        assert result is None


# ---------------------------------------------------------------------------
# form()
# ---------------------------------------------------------------------------

class TestForm:
    def test_plain_input_fallback_collects_all_fields(self):
        import colette_cli.tui.state as state
        state.stdscr = None
        from colette_cli.tui.forms import form, FormField

        fields = [
            FormField(name="name", label="Name"),
            FormField(name="type", label="Type", kind="choice", choices=["local", "ssh"], default="local"),
        ]
        with patch("builtins.input", side_effect=["myname", "2"]):
            result = form(fields)

        assert result == {"name": "myname", "type": "ssh"}

    def test_plain_input_fallback_keeps_default_on_empty(self):
        import colette_cli.tui.state as state
        state.stdscr = None
        from colette_cli.tui.forms import form, FormField

        fields = [FormField(name="name", label="Name", default="fallback")]
        with patch("builtins.input", return_value=""):
            result = form(fields)

        assert result == {"name": "fallback"}

    def test_plain_input_fallback_reprompts_on_validator_failure(self):
        import colette_cli.tui.state as state
        state.stdscr = None
        from colette_cli.tui.forms import form, FormField

        validator = lambda s: (True, "") if s.isdigit() else (False, "must be a number")
        fields = [FormField(name="port", label="Port", validator=validator)]
        with patch("builtins.input", side_effect=["notanumber", "24"]):
            result = form(fields)

        assert result == {"port": "24"}

    def test_plain_input_fallback_skips_hidden_field(self):
        import colette_cli.tui.state as state
        state.stdscr = None
        from colette_cli.tui.forms import form, FormField

        fields = [
            FormField(name="type", label="Type", kind="choice", choices=["local", "ssh"], default="local"),
            FormField(name="host", label="Host", visible_if=lambda v: v["type"] == "ssh"),
        ]
        with patch("builtins.input", return_value=""):
            result = form(fields)

        assert result == {"type": "local", "host": ""}

    def test_curses_submit_returns_all_field_values(self):
        """Type into a text field, cycle a choice field, then submit."""
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        mock_win = MagicMock()
        mock_win.getmaxyx.return_value = (24, 80)
        key_seq = [
            ord("a"), ord("b"), ord("c"),   # type "abc" into "name" (focus 0)
            curses.KEY_DOWN,                 # move focus to "type" (choice, focus 1)
            curses.KEY_RIGHT,                # cycle local -> ssh
            curses.KEY_DOWN,                 # move focus to Submit (focus 2)
            ord("\n"),                       # submit
        ]
        mock_win.getch.side_effect = key_seq

        from colette_cli.tui.forms import form, FormField
        fields = [
            FormField(name="name", label="Name"),
            FormField(name="type", label="Type", kind="choice", choices=["local", "ssh"], default="local"),
        ]
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = form(fields)

        assert result == {"name": "abc", "type": "ssh"}

    def test_curses_esc_cancels(self):
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        mock_win = MagicMock()
        mock_win.getmaxyx.return_value = (24, 80)
        mock_win.getch.side_effect = [27]

        from colette_cli.tui.forms import form, FormField
        fields = [FormField(name="name", label="Name")]
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = form(fields)

        assert result is None

    def test_curses_cancel_row_cancels(self):
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        mock_win = MagicMock()
        mock_win.getmaxyx.return_value = (24, 80)
        key_seq = [
            curses.KEY_DOWN,   # focus 0 (name) -> Submit
            curses.KEY_DOWN,   # Submit -> Cancel
            ord("\n"),          # activate Cancel
        ]
        mock_win.getch.side_effect = key_seq

        from colette_cli.tui.forms import form, FormField
        fields = [FormField(name="name", label="Name", default="x")]
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = form(fields)

        assert result is None

    def test_curses_conditional_field_visibility(self):
        """A field with visible_if only appears once the controlling field's
        value satisfies it — and its own field is skippable when hidden."""
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        mock_win = MagicMock()
        mock_win.getmaxyx.return_value = (24, 80)
        key_seq = [
            curses.KEY_RIGHT,   # cycle "type" local -> ssh (focus 0, choice) — "host" becomes visible
            curses.KEY_DOWN,    # move to "host" (now visible, focus 1)
            ord("h"), ord("i"),
            curses.KEY_DOWN,    # move to Submit (focus 2)
            ord("\n"),
        ]
        mock_win.getch.side_effect = key_seq

        from colette_cli.tui.forms import form, FormField
        fields = [
            FormField(name="type", label="Type", kind="choice", choices=["local", "ssh"], default="local"),
            FormField(name="host", label="Host", visible_if=lambda v: v["type"] == "ssh"),
        ]
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = form(fields)

        assert result == {"type": "ssh", "host": "hi"}

    def test_curses_validator_failure_keeps_form_open(self):
        """Submitting with an invalid field re-focuses it and keeps the form
        open instead of returning; fixing the value and resubmitting works."""
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        mock_win = MagicMock()
        mock_win.getmaxyx.return_value = (24, 80)
        key_seq = [
            curses.KEY_DOWN,           # move from "port" (focus 0) to Submit (focus 1)
            ord("\n"),                  # try to submit with default "" -> fails validator
            ord("2"), ord("4"),         # NOTE: focus was snapped back to "port" (focus 0) on failure
            curses.KEY_DOWN,           # move to Submit again
            ord("\n"),                  # submit successfully this time
        ]
        mock_win.getch.side_effect = key_seq

        from colette_cli.tui.forms import form, FormField
        validator = lambda s: (True, "") if s.isdigit() else (False, "must be a number")
        fields = [FormField(name="port", label="Port", validator=validator)]
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = form(fields)

        assert result == {"port": "24"}

    def test_curses_dynamic_choices_depend_on_other_field(self):
        """A choice field's options can be a callable of the working dict,
        recomputed live as an earlier field changes."""
        import colette_cli.tui.state as state
        scr = _make_stdscr()
        state.stdscr = scr

        mock_win = MagicMock()
        mock_win.getmaxyx.return_value = (24, 80)
        key_seq = [
            curses.KEY_RIGHT,   # cycle "machine" local -> remote (focus 0)
            curses.KEY_DOWN,    # move to "template" (focus 1) — its choices depend on "machine"
            curses.KEY_DOWN,    # move to Submit (focus 2)
            ord("\n"),
        ]
        mock_win.getch.side_effect = key_seq

        from colette_cli.tui.forms import form, FormField
        templates_by_machine = {"local": ["tmpl-a"], "remote": ["tmpl-b", "tmpl-c"]}
        fields = [
            FormField(name="machine", label="Machine", kind="choice", choices=["local", "remote"], default="local"),
            FormField(
                name="template", label="Template", kind="choice",
                choices=lambda v: templates_by_machine[v["machine"]],
            ),
        ]
        with patch("curses.newwin", return_value=mock_win), \
             patch("curses.curs_set"), \
             patch("colette_cli.tui.forms._restore"):
            result = form(fields)

        assert result["machine"] == "remote"
        assert result["template"] in ("tmpl-b", "tmpl-c")
