"""Colette TUI entry point.

Manages the screen stack: each level pushes a new list of MenuItems; ← pops
back to the parent. Leaf actions suspend curses, run the action, then resume.
"""

import curses
import locale
import sys

from colette_cli.utils.formatting import err

from .menu import Menu, QUIT, NOTIFICATIONS
from .screens import main_menu_items, notifications_screen_items
from .splash import show_splash
from . import state


def _run(stdscr):
    """Main TUI loop — runs inside curses.wrapper."""
    curses.use_default_colors()
    state.stdscr = stdscr

    show_splash(stdscr)

    # Stack entries: (breadcrumb_string, list[MenuItem])
    stack = [("COLETTE", main_menu_items())]

    while stack:
        breadcrumb, items = stack[-1]
        if not items:
            stack.pop()
            continue

        selected = Menu(stdscr, items, breadcrumb).run()

        if selected is QUIT:
            break  # q or Escape → exit immediately

        if selected is NOTIFICATIONS:
            stack.append(("COLETTE  ›  Notifications", notifications_screen_items()))
            continue

        if selected is None:
            # ← pressed
            if len(stack) > 1:
                stack.pop()
            else:
                # At root: show splash in quit mode; ←/q quits, anything else stays
                if show_splash(stdscr, quit_mode=True):
                    break
                stdscr.clear()
                stdscr.refresh()
            continue

        if selected.is_leaf:
            selected.run()
            # After a leaf action the screen may have been repainted by an
            # external process; refresh to restore curses state.
            stdscr.clear()
            stdscr.refresh()
        else:
            # Navigate deeper
            children = selected.get_children()
            new_breadcrumb = f"{breadcrumb}  ›  {selected.label}"
            stack.append((new_breadcrumb, children))


def cmd_tui(_args):
    """Launch the interactive Colette TUI."""
    if not sys.stdout.isatty():
        err("colette tui requires an interactive terminal (stdout is not a TTY).")

    # Ensure the locale is set so curses can initialize properly
    locale.setlocale(locale.LC_ALL, "")

    try:
        curses.wrapper(_run)
    except curses.error as e:
        err(
            f"Terminal initialisation failed: {e}\n"
            "Make sure TERM is set correctly (e.g. xterm-256color) and run "
            "colette tui from a full interactive terminal."
        )
    except KeyboardInterrupt:
        pass
