"""In-TUI overlay forms for text input and confirmation.

All functions draw directly on ``state.stdscr`` so curses never needs to be
suspended for user input.
"""

import curses

from . import state

# Box-drawing characters shared with menu.py
_TL = "┌"
_TR = "┐"
_BL = "└"
_BR = "┘"
_H  = "─"
_V  = "│"

_HINT_STYLE = curses.A_DIM


def _draw_box(win, title: str = "") -> None:
    """Draw a full border on *win* with an optional title in the top edge."""
    h, w = win.getmaxyx()
    top = _TL + _H * (w - 2) + _TR
    if title:
        label = f" {title} "
        insert = min(len(label), w - 4)
        top = top[:2] + label[:insert] + top[2 + insert:]
    bot = _BL + _H * (w - 2) + _BR
    try:
        win.addstr(0, 0, top[: w - 1])
        win.addstr(h - 1, 0, bot[: w - 1])
    except curses.error:
        pass
    for row in range(1, h - 1):
        try:
            win.addstr(row, 0, _V)
            win.addstr(row, w - 1, _V)
        except curses.error:
            pass


def _center_win(height: int, width: int) -> "curses.window":
    """Create a centered overlay window of the given size."""
    scr = state.stdscr
    sh, sw = scr.getmaxyx()
    y = max(0, (sh - height) // 2)
    x = max(0, (sw - width) // 2)
    return curses.newwin(height, width, y, x)


def _restore() -> None:
    """Force a full redraw of the background screen after an overlay closes."""
    scr = state.stdscr
    if scr is not None:
        scr.touchwin()
        scr.refresh()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ask(prompt: str, default: str = "") -> "str | None":
    """Show a text-input overlay.

    Returns the entered string (possibly empty), or ``None`` if the user
    pressed ESC.  If the user presses Enter on an empty field the *default*
    value is returned.
    """
    scr = state.stdscr
    if scr is None:
        result = input(f"{prompt}: ").strip()
        return result or default or None

    sh, sw = scr.getmaxyx()
    box_w = min(max(len(prompt) + 10, 52), sw - 4)
    box_h = 6
    if box_w < 20 or box_h > sh - 2:
        # Terminal too small — fall back to plain input
        curses.endwin()
        result = input(f"{prompt}: ").strip()
        curses.doupdate()
        return result or default or None

    win = _center_win(box_h, box_w)
    win.keypad(True)
    curses.curs_set(1)

    buf: list[str] = list(default)
    cur = len(buf)

    try:
        while True:
            win.erase()
            _draw_box(win, prompt)

            inner_w = box_w - 4  # usable input width
            buf_str = "".join(buf)

            # Scroll window so cursor stays visible
            if cur >= inner_w:
                start = cur - inner_w + 1
            else:
                start = 0
            display = buf_str[start: start + inner_w]

            try:
                win.addstr(2, 2, display.ljust(inner_w)[: inner_w])
                win.addstr(3, 2, " " * inner_w)
                hint = "Enter: confirm   ESC: cancel"
                win.addstr(4, 2, hint[: inner_w], _HINT_STYLE)
            except curses.error:
                pass

            cursor_col = 2 + min(cur - start, inner_w - 1)
            try:
                win.move(2, cursor_col)
            except curses.error:
                pass

            win.refresh()
            key = win.getch()

            if key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                return "".join(buf) or default
            elif key == 27:  # ESC
                return None
            elif key in (curses.KEY_BACKSPACE, 8, 127):
                if cur > 0:
                    buf.pop(cur - 1)
                    cur -= 1
            elif key == curses.KEY_DC:
                if cur < len(buf):
                    buf.pop(cur)
            elif key == curses.KEY_LEFT:
                cur = max(0, cur - 1)
            elif key == curses.KEY_RIGHT:
                cur = min(len(buf), cur + 1)
            elif key == curses.KEY_HOME:
                cur = 0
            elif key == curses.KEY_END:
                cur = len(buf)
            elif 32 <= key <= 126:
                buf.insert(cur, chr(key))
                cur += 1
    finally:
        curses.curs_set(0)
        del win
        _restore()


def confirm(message: str, default: bool = False) -> bool:
    """Show a yes/no confirmation dialog.

    Returns ``True`` for yes, ``False`` for no or ESC.
    The *default* value is selected when the user presses Enter.
    """
    scr = state.stdscr
    if scr is None:
        ans = input(f"{message} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
        if ans == "y":
            return True
        if ans == "n":
            return False
        return default

    sh, sw = scr.getmaxyx()
    box_w = min(max(len(message) + 8, 44), sw - 4)
    box_h = 5
    if box_w < 20 or box_h > sh - 2:
        curses.endwin()
        ans = input(f"{message} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
        curses.doupdate()
        return (ans == "y") if ans in ("y", "n") else default

    win = _center_win(box_h, box_w)
    win.keypad(True)
    curses.curs_set(0)

    try:
        win.erase()
        _draw_box(win, "Confirm")
        inner_w = box_w - 4
        try:
            win.addstr(1, 2, message[: inner_w], curses.A_BOLD)
            yes_label = "[Y] yes" if default else "[y] yes"
            no_label  = "[N] no"  if not default else "[n] no"
            opts = f"  {yes_label}    {no_label}  "
            win.addstr(3, max(2, (box_w - len(opts)) // 2), opts[: inner_w])
        except curses.error:
            pass
        win.refresh()

        while True:
            key = win.getch()
            if key in (ord("y"), ord("Y")):
                return True
            elif key in (ord("n"), ord("N"), 27):
                return False
            elif key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                return default
    finally:
        del win
        _restore()


def type_to_confirm(message: str, expected: str) -> bool:
    """Show a destructive-action dialog that requires the user to type *expected*.

    Returns ``True`` only when the typed text matches *expected* exactly.
    Returns ``False`` on ESC or if the user presses Enter with the wrong text.
    """
    scr = state.stdscr
    if scr is None:
        ans = input(f"{message}\nType '{expected}' to confirm: ").strip()
        return ans == expected

    sh, sw = scr.getmaxyx()
    confirm_prompt = f"Type '{expected}' to confirm:"
    box_w = min(max(len(confirm_prompt) + 8, len(message) + 8, 52), sw - 4)
    box_h = 8
    if box_w < 20 or box_h > sh - 2:
        curses.endwin()
        ans = input(f"{message}\nType '{expected}' to confirm: ").strip()
        curses.doupdate()
        return ans == expected

    win = _center_win(box_h, box_w)
    win.keypad(True)
    curses.curs_set(1)

    buf: list[str] = []
    cur = 0
    mismatch = False

    try:
        while True:
            win.erase()
            _draw_box(win, "Confirm")
            inner_w = box_w - 4
            try:
                win.addstr(1, 2, message[: inner_w], curses.A_BOLD)
                win.addstr(2, 2, confirm_prompt[: inner_w])
            except curses.error:
                pass

            buf_str = "".join(buf)
            if cur >= inner_w:
                start = cur - inner_w + 1
            else:
                start = 0
            display = buf_str[start: start + inner_w]
            input_attr = (curses.A_BOLD | curses.A_REVERSE) if mismatch else curses.A_NORMAL
            try:
                win.addstr(4, 2, display.ljust(inner_w)[: inner_w], input_attr)
                hint = "Enter: confirm   ESC: cancel"
                win.addstr(6, 2, hint[: inner_w], _HINT_STYLE)
            except curses.error:
                pass

            cursor_col = 2 + min(cur - start, inner_w - 1)
            try:
                win.move(4, cursor_col)
            except curses.error:
                pass

            win.refresh()
            key = win.getch()

            mismatch = False
            if key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                if "".join(buf) == expected:
                    return True
                mismatch = True
            elif key == 27:
                return False
            elif key in (curses.KEY_BACKSPACE, 8, 127):
                if cur > 0:
                    buf.pop(cur - 1)
                    cur -= 1
            elif key == curses.KEY_DC:
                if cur < len(buf):
                    buf.pop(cur)
            elif key == curses.KEY_LEFT:
                cur = max(0, cur - 1)
            elif key == curses.KEY_RIGHT:
                cur = min(len(buf), cur + 1)
            elif key == curses.KEY_HOME:
                cur = 0
            elif key == curses.KEY_END:
                cur = len(buf)
            elif 32 <= key <= 126:
                buf.insert(cur, chr(key))
                cur += 1
    finally:
        curses.curs_set(0)
        del win
        _restore()
