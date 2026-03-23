"""Splash screen displayed once on TUI launch."""

import curses

from colette_cli.cli.parser import BANNER

_BANNER_LINES = BANNER.strip("\n").splitlines()


def show_splash(stdscr, quit_mode=False):
    """Display the Colette banner centered on screen.

    When quit_mode is False (startup): auto-dismisses after 2 s or any keypress.
    When quit_mode is True (back from home): shows "← quit  any other key back" hint,
    waits for input, and returns True if the user wants to quit, False to stay.
    """
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    hint = "← quit   any other key back" if quit_mode else "[ Press any key ]"
    # All lines: banner + blank + hint
    lines = _BANNER_LINES + ["", hint]

    top = max(0, (h - len(lines)) // 2)

    for i, line in enumerate(lines):
        row = top + i
        if row >= h - 1:
            break

        # Best-effort centering (len() may undercount wide Unicode glyphs by 1-2 cells)
        col = max(0, (w - len(line)) // 2)
        # Truncate to avoid writing past the right edge
        available = w - col - 1
        if available <= 0:
            continue
        text = line[:available]

        try:
            if i < len(_BANNER_LINES) - 1:
                # Block-letter logo lines — bold
                stdscr.addstr(row, col, text, curses.A_BOLD)
            elif i == len(_BANNER_LINES) - 1:
                # Subtitle line — dim
                stdscr.addstr(row, col, text, curses.A_DIM)
            elif line == hint:
                # Hint line — dim
                stdscr.addstr(row, col, text, curses.A_DIM)
        except curses.error:
            pass

    stdscr.refresh()

    if quit_mode:
        stdscr.timeout(-1)
        key = stdscr.getch()
        return key in (curses.KEY_LEFT, ord("q"), 27)  # ←, q, Escape → quit

    # Startup mode: auto-dismiss after 2 s or on any keypress
    stdscr.timeout(2000)
    stdscr.getch()
    stdscr.timeout(-1)
    return False
