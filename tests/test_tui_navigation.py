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

    def test_up_at_top_wraps_to_last_item(self):
        import curses
        items = [_make_leaf("A"), _make_leaf("B")]
        result = self._run_menu([curses.KEY_UP, ord("\n")], items)
        assert result is items[1]

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


class TestShowQuitConfirm:
    def _confirm(self, key):
        from colette_cli.tui.splash import show_quit_confirm
        scr = _make_stdscr([key])
        scr.timeout = MagicMock()
        return show_quit_confirm(scr, running=1)

    def test_y_returns_true(self):
        assert self._confirm(ord("y")) is True

    def test_other_key_returns_false(self):
        assert self._confirm(ord("n")) is False

    def test_enter_returns_false(self):
        assert self._confirm(ord("\n")) is False

    def test_escape_returns_false(self):
        assert self._confirm(27) is False

    def test_plural_tasks(self):
        """Smoke test with multiple running tasks (no error)."""
        from colette_cli.tui.splash import show_quit_confirm
        scr = _make_stdscr([ord("y")])
        scr.timeout = MagicMock()
        result = show_quit_confirm(scr, running=3)
        assert result is True


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

    def _run_with_keys_and_confirm(
        self, tmp_config, keys, splash_returns=None, confirm_returns=None, running_tasks=0
    ):
        """Like _run_with_keys but also mocks show_quit_confirm and state.running_tasks."""
        import colette_cli.tui.state as state
        from colette_cli.utils.config import save_config, save_projects
        save_config({
            "machines": {"local": {"type": "local", "projects_dir": "/tmp", "templates": []}},
            "default_machine": "local",
        })
        save_projects([])

        orig_running = state.running_tasks
        state.running_tasks = running_tasks
        try:
            scr = _make_stdscr(keys)
            scr.timeout = MagicMock()

            splash_side = splash_returns if splash_returns is not None else [False]
            confirm_side = confirm_returns if confirm_returns is not None else []
            from colette_cli.tui.app import _run
            with patch("colette_cli.tui.app.show_splash", side_effect=splash_side), \
                 patch("colette_cli.tui.app.show_quit_confirm", side_effect=confirm_side) as mock_confirm, \
                 patch("curses.curs_set"), \
                 patch("curses.use_default_colors"):
                _run(scr)
            return mock_confirm
        finally:
            state.running_tasks = orig_running

    # -- q / Escape with running tasks --

    def test_q_with_running_tasks_shows_confirm(self, tmp_config):
        """q while tasks run must prompt for confirmation."""
        mock_confirm = self._run_with_keys_and_confirm(
            tmp_config, [ord("q")],
            splash_returns=[False],
            confirm_returns=[True],
            running_tasks=1,
        )
        assert mock_confirm.call_count == 1
        _, kwargs = mock_confirm.call_args
        assert kwargs.get("running", mock_confirm.call_args[0][1] if len(mock_confirm.call_args[0]) > 1 else None) == 1 \
            or mock_confirm.call_args[0][1] == 1

    def test_q_with_running_tasks_confirm_yes_quits(self, tmp_config):
        """q + confirm y → TUI exits (show_splash only called once for startup)."""
        with patch("colette_cli.tui.app.show_splash", side_effect=[False]) as mock_splash, \
             patch("colette_cli.tui.app.show_quit_confirm", return_value=True), \
             patch("curses.curs_set"), \
             patch("curses.use_default_colors"):
            import colette_cli.tui.state as state
            from colette_cli.utils.config import save_config, save_projects
            save_config({
                "machines": {"local": {"type": "local", "projects_dir": "/tmp", "templates": []}},
                "default_machine": "local",
            })
            save_projects([])
            orig = state.running_tasks
            state.running_tasks = 2
            try:
                from colette_cli.tui.app import _run
                scr = _make_stdscr([ord("q")])
                scr.timeout = MagicMock()
                _run(scr)
            finally:
                state.running_tasks = orig
        assert mock_splash.call_count == 1  # only startup splash

    def test_q_with_running_tasks_confirm_no_stays(self, tmp_config):
        """q + confirm n → stays in TUI; second q (no tasks) exits."""
        import colette_cli.tui.state as state
        from colette_cli.utils.config import save_config, save_projects
        save_config({
            "machines": {"local": {"type": "local", "projects_dir": "/tmp", "templates": []}},
            "default_machine": "local",
        })
        save_projects([])

        confirm_calls = []

        def _confirm(stdscr, running):
            confirm_calls.append(running)
            # After first refusal, clear running tasks so second q exits cleanly
            state.running_tasks = 0
            return False

        orig = state.running_tasks
        state.running_tasks = 1
        try:
            scr = _make_stdscr([ord("q"), ord("q")])
            scr.timeout = MagicMock()
            from colette_cli.tui.app import _run
            with patch("colette_cli.tui.app.show_splash", side_effect=[False]), \
                 patch("colette_cli.tui.app.show_quit_confirm", side_effect=_confirm), \
                 patch("curses.curs_set"), \
                 patch("curses.use_default_colors"):
                _run(scr)
        finally:
            state.running_tasks = orig

        assert confirm_calls == [1]  # confirm shown once for the first q

    # -- ← at root with running tasks --

    def test_left_at_root_with_running_tasks_shows_confirm(self, tmp_config):
        """← at root while tasks run must prompt before the quit-mode splash."""
        import curses
        import colette_cli.tui.state as state
        from colette_cli.utils.config import save_config, save_projects
        save_config({
            "machines": {"local": {"type": "local", "projects_dir": "/tmp", "templates": []}},
            "default_machine": "local",
        })
        save_projects([])

        orig = state.running_tasks
        state.running_tasks = 1
        try:
            scr = _make_stdscr([curses.KEY_LEFT])
            scr.timeout = MagicMock()
            from colette_cli.tui.app import _run
            with patch("colette_cli.tui.app.show_splash", side_effect=[False, True]) as mock_splash, \
                 patch("colette_cli.tui.app.show_quit_confirm", return_value=True) as mock_confirm, \
                 patch("curses.curs_set"), \
                 patch("curses.use_default_colors"):
                _run(scr)
        finally:
            state.running_tasks = orig

        assert mock_confirm.call_count == 1

    def test_left_at_root_with_running_tasks_confirm_no_stays(self, tmp_config):
        """← at root + confirm n → stays, no quit-mode splash shown."""
        import curses
        import colette_cli.tui.state as state
        from colette_cli.utils.config import save_config, save_projects
        save_config({
            "machines": {"local": {"type": "local", "projects_dir": "/tmp", "templates": []}},
            "default_machine": "local",
        })
        save_projects([])

        orig = state.running_tasks
        state.running_tasks = 1
        try:
            scr = _make_stdscr([curses.KEY_LEFT, ord("q")])
            scr.timeout = MagicMock()
            from colette_cli.tui.app import _run
            with patch("colette_cli.tui.app.show_splash", side_effect=[False]) as mock_splash, \
                 patch("colette_cli.tui.app.show_quit_confirm", return_value=False) as mock_confirm, \
                 patch("curses.curs_set"), \
                 patch("curses.use_default_colors"):
                # After ← is refused, state has tasks; second q will also be refused
                # unless we clear tasks. Simulate clearing after confirm.
                def _confirm(stdscr, running):
                    state.running_tasks = 0
                    return False
                mock_confirm.side_effect = _confirm
                _run(scr)
        finally:
            state.running_tasks = orig

        # quit-mode splash never called (confirm blocked it)
        assert mock_splash.call_count == 1

    # -- No tasks: no confirmation --

    def test_q_without_running_tasks_no_confirm(self, tmp_config):
        """q with no running tasks must NOT show confirmation."""
        import colette_cli.tui.state as state
        orig = state.running_tasks
        state.running_tasks = 0
        try:
            mock_confirm = self._run_with_keys_and_confirm(
                tmp_config, [ord("q")],
                splash_returns=[False],
                confirm_returns=[],
                running_tasks=0,
            )
        finally:
            state.running_tasks = orig
        assert mock_confirm.call_count == 0


class TestNotificationsKey:
    def _run_menu(self, keys, items=None):
        import curses
        from colette_cli.tui.menu import Menu
        scr = MagicMock()
        scr.getmaxyx.return_value = (24, 80)
        scr.getch.side_effect = list(keys)
        menu_items = items or [_make_leaf("A")]
        with patch("curses.curs_set"):
            return Menu(scr, menu_items).run()

    def test_n_returns_notifications_sentinel(self):
        from colette_cli.tui.menu import NOTIFICATIONS
        import colette_cli.tui.state as state
        state.notifications = []
        state.running_tasks = 0
        result = self._run_menu([ord("n")])
        assert result is NOTIFICATIONS
