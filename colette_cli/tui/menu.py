"""Reusable arrow-key menu widget for the Colette TUI."""

import curses

from . import state


class _Quit:
    """Sentinel returned by Menu.run() when the user presses q or Escape."""


QUIT = _Quit()


class MenuItem:
    """A single entry in a menu."""

    def __init__(self, label, *, action=None, children=None, detail="", selectable=True):
        """
        Args:
            label:      Display text.
            action:     Callable executed when selected (leaf item).
            children:   Callable returning a list[MenuItem] (sub-menu item).
            detail:     Optional secondary text shown to the right of the label.
            selectable: If False, the item is rendered as a section title or
                        separator and cannot be focused or activated.
        """
        if selectable and action is None and children is None:
            raise ValueError("MenuItem requires either action or children")
        self.label = label
        self.detail = detail
        self.selectable = selectable
        self._action = action
        self._children = children

    @property
    def is_leaf(self):
        return self._action is not None

    def get_children(self):
        return self._children() if callable(self._children) else self._children

    def run(self):
        if self._action:
            self._action()


class Menu:
    """Renders a list of MenuItems and handles arrow-key navigation.

    Returns the selected MenuItem on → / Enter, or None on ← / Escape / q.
    """

    LABEL_COL = 4
    DETAIL_COL = 36

    def __init__(self, stdscr, items, breadcrumb="COLETTE"):
        self._scr = stdscr
        self._items = items
        self._breadcrumb = breadcrumb
        self._cursor = 0
        # Start on the first selectable item
        if items and not items[0].selectable:
            self._cursor = self._next_selectable(0, 1)

    def _next_selectable(self, from_index, direction):
        """Return the next selectable index wrapping in the given direction (+1/-1)."""
        n = len(self._items)
        if n == 0:
            return from_index
        idx = (from_index + direction) % n
        for _ in range(n):
            if self._items[idx].selectable:
                return idx
            idx = (idx + direction) % n
        return from_index  # no selectable items at all

    def run(self):
        """Block until the user makes a choice or navigates back.

        Returns:
            MenuItem if the user pressed → / Enter on an item.
            None     if the user pressed ← (go back).
            QUIT     if the user pressed q or Escape (exit TUI).
        """
        curses.curs_set(0)
        self._scr.keypad(True)

        while True:
            self._render()
            # Use a short timeout when background jobs are running so the
            # jobs indicator refreshes automatically.
            if state.running_jobs:
                self._scr.timeout(500)
            else:
                self._scr.timeout(-1)
            key = self._scr.getch()
            if key == -1:
                # Timeout tick — just re-render to update jobs indicator.
                continue

            if key in (curses.KEY_UP, ord("k")):
                self._cursor = self._next_selectable(self._cursor, -1)

            elif key in (curses.KEY_DOWN, ord("j")):
                self._cursor = self._next_selectable(self._cursor, 1)

            elif key in (curses.KEY_RIGHT, curses.KEY_ENTER, ord("\n"), ord("\r")):
                if self._items and self._items[self._cursor].selectable:
                    return self._items[self._cursor]

            elif key == curses.KEY_LEFT:
                return None  # go back

            elif key in (27, ord("q")):  # Escape or q → quit TUI
                return QUIT

    # Box-drawing characters for the item border
    _BOX_H = "─"
    _BOX_TL = "┌"
    _BOX_TR = "┐"
    _BOX_BL = "└"
    _BOX_BR = "┘"
    _BOX_V = "│"

    def _render(self):
        self._scr.erase()
        h, w = self._scr.getmaxyx()

        # ── Header (row 0) ──────────────────────────────────────────────────
        if self._breadcrumb == "COLETTE":
            # Root level: spaced logo centered in the reverse bar
            logo = "◆  C O L E T T E  ◆"
            header = logo.center(w - 2)
        else:
            header = f"  {self._breadcrumb}  "
        header_line = header.ljust(w)[:w]
        self._scr.attron(curses.A_REVERSE | curses.A_BOLD)
        self._scr.addstr(0, 0, header_line)
        self._scr.attroff(curses.A_REVERSE | curses.A_BOLD)

        # ── Box border (rows 1 and h-2) ────────────────────────────────────
        # Only draw if there's enough vertical space
        if h >= 5:
            inner_w = max(0, w - 2)
            top_border = self._BOX_TL + self._BOX_H * inner_w + self._BOX_TR
            bot_border = self._BOX_BL + self._BOX_H * inner_w + self._BOX_BR
            try:
                self._scr.addstr(1, 0, top_border[:w - 1])
                self._scr.addstr(h - 2, 0, bot_border[:w - 1])
            except curses.error:
                pass

        # ── Footer hint (row h-1) ──────────────────────────────────────────
        jobs = state.running_jobs
        if jobs:
            n = len(jobs)
            hint = f" ⏳ {n} job{'s' if n != 1 else ''} running… "
        else:
            hint = " ↑↓ navigate   → select   ← back   q quit "
        self._scr.addstr(h - 1, 0, hint.ljust(w - 1)[: w - 1], curses.A_DIM)

        # ── Items (rows 2..h-3, inside the box) ────────────────────────────
        # Item area: col 2..w-3 (inside │ borders), rows 2..h-3
        item_top = 2
        item_bot = h - 3  # inclusive last item row
        item_w = max(0, w - 4)  # width inside the box (excluding │ and one padding)

        visible_rows = max(0, item_bot - item_top + 1)
        visible_start = max(0, self._cursor - (visible_rows - 1))

        for i, item in enumerate(self._items):
            row = item_top + (i - visible_start)
            if row < item_top or row > item_bot:
                continue

            is_selected = i == self._cursor and item.selectable
            prefix = "▶ " if is_selected else "  "
            label = (prefix + item.label)[: self.DETAIL_COL - 2]
            if not item.selectable:
                attr = curses.A_DIM
            elif is_selected:
                attr = curses.A_BOLD
            else:
                attr = curses.A_NORMAL

            # Left border
            try:
                self._scr.addstr(row, 1, self._BOX_V)
            except curses.error:
                pass

            # Label
            try:
                self._scr.addstr(row, 2, f" {label:<{self.DETAIL_COL - 2}}", attr)
            except curses.error:
                pass

            # Detail (if there's room)
            detail_col = self.DETAIL_COL + 2
            if item.detail and detail_col < w - 3:
                max_detail = w - detail_col - 3
                detail = item.detail[:max_detail]
                try:
                    self._scr.addstr(row, detail_col, detail, curses.A_DIM)
                except curses.error:
                    pass

            # Right border
            try:
                self._scr.addstr(row, w - 2, " " + self._BOX_V)
            except curses.error:
                pass

        # Fill empty item rows inside the box with side borders
        items_rendered = min(len(self._items), visible_rows)
        for blank_row in range(item_top + items_rendered, item_bot + 1):
            try:
                self._scr.addstr(blank_row, 1, self._BOX_V)
                self._scr.addstr(blank_row, w - 2, " " + self._BOX_V)
            except curses.error:
                pass

        self._scr.refresh()
