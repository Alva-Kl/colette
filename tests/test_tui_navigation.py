"""Tests for colette_cli.tui navigation — Menu widget, splash screen, app loop."""

import pytest
from unittest.mock import patch, MagicMock, call, ANY


def _make_stdscr(keys):
    """Return a mock stdscr that yields the given key sequence from getch()."""
    scr = MagicMock()
    scr.getmaxyx.return_value = (24, 80)
    scr.getch.side_effect = list(keys)
    return scr


def _make_leaf(label="item"):
    from colette_cli.tui.menu import MenuItem
    return MenuItem(label, action=lambda: None)


def _make_submenu(label="sub"):
    from colette_cli.tui.menu import MenuItem
    return MenuItem(label, children=lambda: [])


# ---------------------------------------------------------------------------
# Menu.run() — return values
# ---------------------------------------------------------------------------

class TestMenuNavigation:
    """Menu.run() must distinguish ← (back=None) from q/Escape (QUIT)."""

    def _run_menu(self, keys, items=None):
        import curses
        from colette_cli.tui.menu import Menu
        scr = _make_stdscr(keys)
        menu_items = items or [_make_leaf("A"), _make_leaf("B")]
        with patch("curses.curs_set"):
            return Menu(scr, menu_items).run()

    def test_q_returns_quit(self):
        from colette_cli.tui.menu import QUIT
        assert self._run_menu([ord("q")]) is QUIT

    def test_escape_returns_quit(self):
        from colette_cli.tui.menu import QUIT
        assert self._run_menu([27]) is QUIT

    def test_left_returns_none(self):
        import curses
        assert self._run_menu([curses.KEY_LEFT]) is None

    def test_right_returns_selected_item(self):
        import curses
        items = [_make_leaf("A"), _make_leaf("B")]
        result = self._run_menu([curses.KEY_RIGHT], items)
        assert result is items[0]

    def test_enter_returns_selected_item(self):
        items = [_make_leaf("A"), _make_leaf("B")]
        result = self._run_menu([ord("\n")], items)
        assert result is items[0]

    def test_down_then_enter_selects_second_item(self):
        import curses
        items = [_make_leaf("A"), _make_leaf("B")]
        result = self._run_menu([curses.KEY_DOWN, ord("\n")], items)
        assert result is items[1]

    def test_up_at_top_stays_on_first_item(self):
        import curses
        items = [_make_leaf("A"), _make_leaf("B")]
        result = self._run_menu([curses.KEY_UP, ord("\n")], items)
        assert result is items[0]

    def test_j_navigates_down(self):
        items = [_make_leaf("A"), _make_leaf("B")]
        result = self._run_menu([ord("j"), ord("\n")], items)
        assert result is items[1]

    def test_k_navigates_up(self):
        import curses
        items = [_make_leaf("A"), _make_leaf("B")]
        result = self._run_menu([curses.KEY_DOWN, ord("k"), ord("\n")], items)
        assert result is items[0]

    def test_quit_and_back_are_distinct(self):
        import curses
        from colette_cli.tui.menu import QUIT
        assert self._run_menu([ord("q")]) is QUIT
        assert self._run_menu([curses.KEY_LEFT]) is None


# ---------------------------------------------------------------------------
# QUIT sentinel identity
# ---------------------------------------------------------------------------

class TestQuitSentinel:
    def test_quit_is_singleton(self):
        from colette_cli.tui.menu import QUIT
        from colette_cli.tui.menu import QUIT as QUIT2
        assert QUIT is QUIT2

    def test_quit_is_not_none(self):
        from colette_cli.tui.menu import QUIT
        assert QUIT is not None

    def test_quit_is_not_false(self):
        from colette_cli.tui.menu import QUIT
        assert QUIT is not False


# ---------------------------------------------------------------------------
# show_splash
# ---------------------------------------------------------------------------

class TestShowSplash:
    def _splash(self, key, quit_mode):
        from colette_cli.tui.splash import show_splash
        scr = _make_stdscr([key])
        scr.timeout = MagicMock()
        return show_splash(scr, quit_mode=quit_mode)

    def test_startup_mode_always_returns_false(self):
        assert self._splash(-1, quit_mode=False) is False

    def test_quit_mode_left_returns_true(self):
        import curses
        assert self._splash(curses.KEY_LEFT, quit_mode=True) is True

    def test_quit_mode_q_returns_true(self):
        assert self._splash(ord("q"), quit_mode=True) is True

    def test_quit_mode_escape_returns_true(self):
        assert self._splash(27, quit_mode=True) is True

    def test_quit_mode_any_other_key_returns_false(self):
        assert self._splash(ord("x"), quit_mode=True) is False

    def test_quit_mode_enter_returns_false(self):
        assert self._splash(ord("\n"), quit_mode=True) is False

    def test_startup_mode_sets_2s_timeout(self):
        from colette_cli.tui.splash import show_splash
        scr = _make_stdscr([-1])
        scr.timeout = MagicMock()
        show_splash(scr, quit_mode=False)
        scr.timeout.assert_any_call(2000)

    def test_quit_mode_does_not_set_2s_timeout(self):
        """Quit mode must wait indefinitely — no 2-second auto-dismiss."""
        import curses
        from colette_cli.tui.splash import show_splash
        scr = _make_stdscr([curses.KEY_LEFT])
        timeout_calls = []
        scr.timeout = lambda v: timeout_calls.append(v)
        show_splash(scr, quit_mode=True)
        assert 2000 not in timeout_calls


# ---------------------------------------------------------------------------
# App loop (_run) — navigation
# ---------------------------------------------------------------------------

class TestAppLoop:
    """_run() integration: QUIT exits, ← at root shows quit splash, ← elsewhere pops."""

    def _run_with_keys(self, tmp_config, keys, projects=None, splash_returns=None):
        """Run _run() with scripted keys and mocked splash.

        splash_returns: list of booleans returned by successive show_splash calls.
        First entry is the startup splash (should be False); subsequent entries
        are quit-mode splash calls.
        """
        from colette_cli.utils.config import save_config, save_projects
        save_config({
            "machines": {"local": {"type": "local", "projects_dir": "/tmp", "templates": []}},
            "default_machine": "local",
        })
        save_projects(projects or [])

        scr = _make_stdscr(keys)
        scr.timeout = MagicMock()

        returns = splash_returns if splash_returns is not None else [False]
        from colette_cli.tui.app import _run
        with patch("colette_cli.tui.app.show_splash", side_effect=returns) as mock_splash, \
             patch("curses.curs_set"), \
             patch("curses.use_default_colors"):
            _run(scr)
        return mock_splash

    def test_q_exits_immediately(self, tmp_config):
        """q should exit without ever showing the quit-mode splash."""
        mock_splash = self._run_with_keys(
            tmp_config, [ord("q")], splash_returns=[False]
        )
        # Only the startup splash is shown
        assert mock_splash.call_count == 1

    def test_left_at_root_shows_quit_mode_splash(self, tmp_config):
        """← at root should trigger quit-mode splash."""
        import curses
        mock_splash = self._run_with_keys(
            tmp_config,
            [curses.KEY_LEFT],
            splash_returns=[False, True],  # startup=False, quit=True → exit
        )
        assert mock_splash.call_count == 2
        assert mock_splash.call_args_list[1] == call(ANY, quit_mode=True)

    def test_left_at_root_with_splash_false_returns_to_home(self, tmp_config):
        """← at root, splash returns False → stay; next q exits."""
        import curses
        mock_splash = self._run_with_keys(
            tmp_config,
            [curses.KEY_LEFT, ord("q")],
            splash_returns=[False, False],  # startup=False, quit=False → stay
        )
        # Startup splash + quit-mode splash both called
        assert mock_splash.call_count == 2
