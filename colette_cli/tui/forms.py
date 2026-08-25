"""In-TUI overlay forms for text input and confirmation.

All functions draw directly on ``state.stdscr`` so curses never needs to be
suspended for user input.
"""

import curses
from dataclasses import dataclass
from typing import Callable, Union

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

def show_running(message: str = "Running…") -> None:
    """Draw a brief 'Running…' indicator and refresh the screen immediately.

    Call this just before a blocking operation so the user sees feedback.
    The overlay is automatically overwritten by the next screen redraw or
    show_output() call.
    """
    scr = state.stdscr
    if scr is None:
        return
    label = f"  {message}  "
    box_w = len(label) + 2
    win = _center_win(3, box_w)
    try:
        _draw_box(win)
        win.addstr(1, 1, label, curses.A_BOLD)
        win.refresh()
    except curses.error:
        pass


def ask(prompt: str, default: str = "", choices: "list[str] | None" = None) -> "str | None":
    """Show a text-input or choice-selection overlay.

    When *choices* is provided, renders an arrow-key-navigable list.  The
    initially selected item is the one matching *default* (or the first item).
    Returns the selected string, or ``None`` if the user pressed ESC.

    Without *choices*, shows a free-form text input.  Returns the entered
    string (possibly empty), or ``None`` on ESC.  Empty input returns
    *default*.
    """
    if choices is not None:
        return _ask_choices(prompt, choices, default)

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


def _ask_choices(prompt: str, choices: "list[str]", default: str = "") -> "str | None":
    """Render an arrow-key-navigable selection list overlay.

    Returns the selected string, or ``None`` on ESC / empty list.
    """
    if not choices:
        return None

    scr = state.stdscr
    if scr is None:
        for i, c in enumerate(choices):
            print(f"  {i + 1}. {c}")
        raw = input(f"{prompt} [1-{len(choices)}]: ").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        return default if default in choices else choices[0]

    sh, sw = scr.getmaxyx()
    max_visible = max(3, sh - 8)
    inner_w = min(
        max(len(prompt) + 4, max((len(c) for c in choices), default=20) + 4, 30),
        sw - 6,
    )
    box_w = inner_w + 4
    visible = min(len(choices), max_visible)
    box_h = visible + 4  # top border + blank row + choices + hint row + bottom border

    if box_h > sh - 2 or box_w > sw - 2:
        curses.endwin()
        for i, c in enumerate(choices):
            print(f"  {i + 1}. {c}")
        raw = input(f"{prompt} [1-{len(choices)}]: ").strip()
        curses.doupdate()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        return default if default in choices else choices[0]

    sel = choices.index(default) if default in choices else 0
    top = 0

    win = _center_win(box_h, box_w)
    win.keypad(True)

    try:
        while True:
            win.erase()
            _draw_box(win, prompt)

            if sel < top:
                top = sel
            elif sel >= top + visible:
                top = sel - visible + 1

            for i in range(visible):
                idx = top + i
                if idx >= len(choices):
                    break
                label = choices[idx][:inner_w].ljust(inner_w)
                attr = curses.A_REVERSE if idx == sel else curses.A_NORMAL
                try:
                    win.addstr(i + 2, 2, label, attr)
                except curses.error:
                    pass

            hint_parts = []
            if top > 0:
                hint_parts.append("↑")
            if top + visible < len(choices):
                hint_parts.append("↓")
            hint_parts.append("Enter: select  ESC: cancel")
            hint = "  ".join(hint_parts)
            try:
                win.addstr(box_h - 1, 2, hint[:inner_w], _HINT_STYLE)
            except curses.error:
                pass

            win.refresh()
            key = win.getch()

            if key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                return choices[sel]
            elif key == 27:  # ESC
                return None
            elif key in (curses.KEY_DOWN, ord("j")):
                if sel < len(choices) - 1:
                    sel += 1
            elif key in (curses.KEY_UP, ord("k")):
                if sel > 0:
                    sel -= 1
            elif key == curses.KEY_NPAGE:
                sel = min(sel + visible, len(choices) - 1)
            elif key == curses.KEY_PPAGE:
                sel = max(0, sel - visible)
    finally:
        del win
        _restore()


@dataclass
class FormField:
    """One field in a multi-field form() screen.

    label/choices may be a plain value or a callable taking the form's
    in-progress working dict (``{field_name: current_str_value}``) — this is
    how a field's label or choice list can depend on another field's current
    value (e.g. "Template path" vs "Template git URL" depending on `type`).

    visible_if is re-evaluated every render; a hidden field's value is still
    carried in the working dict (and returned to the caller), just not shown
    or editable while hidden.

    validator runs only at submit time, in field order, on currently-visible
    fields — returns (True, "") on success or (False, "error message") to
    keep the form open with that field focused and the message displayed.
    """
    name: str
    label: "Union[str, Callable[[dict], str]]" = ""
    kind: str = "text"  # "text" | "choice"
    default: str = ""
    choices: "Union[list, Callable[[dict], list], None]" = None
    visible_if: "Callable[[dict], bool] | None" = None
    validator: "Callable[[str], tuple] | None" = None
    placeholder: str = ""


def _resolve(value, working):
    return value(working) if callable(value) else value


def _form_plain_input(fields: "list[FormField]", working: dict) -> dict:
    """No-curses fallback: prompt sequentially via input(), one pass, no cancel."""
    for f in fields:
        if f.visible_if is not None and not f.visible_if(working):
            continue
        label = _resolve(f.label, working)
        if f.kind == "choice":
            choices = _resolve(f.choices, working) or []
            if choices and working.get(f.name) not in choices:
                working[f.name] = choices[0]
            if not choices:
                continue
            for i, c in enumerate(choices):
                print(f"  {i + 1}. {c}")
            raw = input(f"{label} [1-{len(choices)}] (default {working[f.name]}): ").strip()
            if raw:
                try:
                    idx = int(raw) - 1
                    if 0 <= idx < len(choices):
                        working[f.name] = choices[idx]
                except ValueError:
                    pass
        else:
            while True:
                raw = input(f"{label} [{working.get(f.name, '')}]: ").strip()
                value = raw or working.get(f.name, "")
                if f.validator is not None:
                    ok, msg = f.validator(value)
                    if not ok:
                        print(f"Error: {msg}")
                        continue
                working[f.name] = value
                break
    return working


def form(fields: "list[FormField]", title: str = "") -> "dict | None":
    """Show a multi-field form overlay: all fields visible at once, with
    live conditional visibility and a single Submit/Cancel at the end.

    Returns the full working dict (keyed by every field's name, including
    fields that ended up hidden at submit time — the caller decides what to
    keep), or None if the user cancelled (ESC, or selecting Cancel).

    Navigation: Up/Down and Tab/Shift-Tab move focus between visible fields
    and the trailing Submit/Cancel rows (wrapping). Left/Right on a text
    field move the in-row edit cursor; on a choice field they cycle its
    value. Enter on a field advances focus (it never submits by itself) —
    only activating the Submit row runs validation and returns.
    """
    working = {f.name: f.default for f in fields}

    scr = state.stdscr
    if scr is None:
        return _form_plain_input(fields, working)

    win = None
    focus_idx = 0
    text_cursor = 0
    last_focus_key = None
    error_field = None
    error_msg = ""

    try:
        while True:
            visible_fields = [f for f in fields if f.visible_if is None or f.visible_if(working)]

            # Snap any choice field whose value fell out of its (possibly
            # dynamic) choice list back into range.
            for f in visible_fields:
                if f.kind == "choice":
                    choices = _resolve(f.choices, working) or []
                    if choices and working.get(f.name) not in choices:
                        working[f.name] = choices[0]

            num_rows = len(visible_fields) + 2  # + Submit + Cancel
            focus_idx = max(0, min(focus_idx, num_rows - 1))
            if focus_idx < len(visible_fields):
                focus_key = visible_fields[focus_idx].name
            elif focus_idx == len(visible_fields):
                focus_key = "__submit__"
            else:
                focus_key = "__cancel__"

            if focus_key != last_focus_key:
                if focus_idx < len(visible_fields) and visible_fields[focus_idx].kind == "text":
                    text_cursor = len(working.get(visible_fields[focus_idx].name, ""))
                last_focus_key = focus_key

            sh, sw = scr.getmaxyx()
            labels = [_resolve(f.label, working) for f in visible_fields]
            label_w = max([len(l) for l in labels], default=10)
            value_w = max(
                [len(working.get(f.name, "") or f.placeholder) for f in visible_fields],
                default=10,
            )
            box_w = min(max(label_w + value_w + 10, 50), sw - 4)
            box_h = min(len(visible_fields) + 6, sh - 2)  # fields + error + 2 buttons + hint + borders
            box_w = max(box_w, 20)
            box_h = max(box_h, 8)

            if win is not None:
                del win
            win = _center_win(box_h, box_w)
            win.keypad(True)
            win.erase()
            _draw_box(win, title)
            inner_w = box_w - 4

            for i, f in enumerate(visible_fields):
                row = 1 + i
                focused = i == focus_idx
                label = labels[i]
                value = working.get(f.name, "")
                if f.kind == "choice":
                    shown = f"◀ {value} ▶" if focused else value
                else:
                    shown = value or (f.placeholder if not focused else "")
                line = f"{label}: {shown}"
                attr = curses.A_REVERSE if (focused and f.kind == "choice") else curses.A_NORMAL
                try:
                    win.addstr(row, 2, line[:inner_w].ljust(inner_w), attr)
                except curses.error:
                    pass
                if focused and f.kind == "text":
                    cur = min(text_cursor, len(value))
                    prefix_len = len(f"{label}: ")
                    col = min(2 + prefix_len + cur, box_w - 2)
                    try:
                        win.move(row, col)
                    except curses.error:
                        pass

            error_row = len(visible_fields) + 1
            if error_msg:
                try:
                    win.addstr(error_row, 2, f"⚠ {error_msg}"[:inner_w], curses.A_DIM)
                except curses.error:
                    pass

            submit_row = len(visible_fields) + 2
            cancel_row = len(visible_fields) + 3
            try:
                win.addstr(
                    submit_row, 2, "[ Submit ]",
                    curses.A_REVERSE if focus_idx == len(visible_fields) else curses.A_BOLD,
                )
                win.addstr(
                    cancel_row, 2, "[ Cancel ]",
                    curses.A_REVERSE if focus_idx == len(visible_fields) + 1 else curses.A_NORMAL,
                )
                hint = "↑↓/Tab: move   Enter: edit/select   ESC: cancel"
                win.addstr(box_h - 2, 2, hint[:inner_w], _HINT_STYLE)
            except curses.error:
                pass

            if not (focus_idx < len(visible_fields) and visible_fields[focus_idx].kind == "text"):
                curses.curs_set(0)
            else:
                curses.curs_set(1)

            win.refresh()
            key = win.getch()

            if key == 27:  # ESC
                return None
            elif key in (curses.KEY_UP,) or key == curses.KEY_BTAB:
                focus_idx = (focus_idx - 1) % num_rows
                error_msg = ""
            elif key in (curses.KEY_DOWN, 9):  # Down or Tab
                focus_idx = (focus_idx + 1) % num_rows
                error_msg = ""
            elif focus_idx == len(visible_fields):  # Submit row
                if key in (curses.KEY_ENTER, ord("\n"), ord("\r"), curses.KEY_LEFT, curses.KEY_RIGHT):
                    failure = None
                    for f in visible_fields:
                        if f.validator is not None:
                            ok, msg = f.validator(working.get(f.name, ""))
                            if not ok:
                                failure = (f, msg)
                                break
                    if failure is None:
                        return dict(working)
                    fail_field, fail_msg = failure
                    focus_idx = visible_fields.index(fail_field)
                    error_field = fail_field.name
                    error_msg = fail_msg
            elif focus_idx == len(visible_fields) + 1:  # Cancel row
                if key in (curses.KEY_ENTER, ord("\n"), ord("\r"), curses.KEY_LEFT, curses.KEY_RIGHT):
                    return None
            else:
                f = visible_fields[focus_idx]
                if error_field == f.name:
                    error_field = None
                    error_msg = ""
                if f.kind == "choice":
                    choices = _resolve(f.choices, working) or []
                    if choices:
                        idx = choices.index(working[f.name]) if working.get(f.name) in choices else 0
                        if key == curses.KEY_RIGHT:
                            working[f.name] = choices[(idx + 1) % len(choices)]
                        elif key == curses.KEY_LEFT:
                            working[f.name] = choices[(idx - 1) % len(choices)]
                        elif key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                            focus_idx = (focus_idx + 1) % num_rows
                else:
                    buf = list(working.get(f.name, ""))
                    cur = min(text_cursor, len(buf))
                    if key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                        focus_idx = (focus_idx + 1) % num_rows
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
                    working[f.name] = "".join(buf)
                    text_cursor = cur
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


def show_output(text: str, title: str = "Output") -> None:
    """Display captured text output in a scrollable read-only overlay.

    Dismissed with Enter, q, ESC, or ← (left arrow).
    Falls back to printing the text directly when not inside curses.
    """
    scr = state.stdscr
    if scr is None:
        print(text)
        return

    lines = text.splitlines() or ["(no output)"]
    sh, sw = scr.getmaxyx()
    box_h = max(6, min(sh - 4, len(lines) + 4))
    box_w = max(40, min(sw - 4, max((len(l) for l in lines), default=20) + 4))

    if box_h > sh - 2 or box_w > sw - 2:
        curses.endwin()
        print(text)
        input("\nPress Enter to continue…")
        curses.doupdate()
        return

    win = _center_win(box_h, box_w)
    win.keypad(True)
    inner_h = box_h - 2  # rows available for content
    inner_w = box_w - 4
    top = 0  # scroll offset

    try:
        while True:
            win.erase()
            _draw_box(win, title)
            visible = lines[top: top + inner_h]
            for i, line in enumerate(visible):
                try:
                    win.addstr(i + 1, 2, line[:inner_w].ljust(inner_w))
                except curses.error:
                    pass
            # Scroll hint in bottom border
            hint_parts = []
            if top > 0:
                hint_parts.append("↑")
            if top + inner_h < len(lines):
                hint_parts.append("↓")
            hint_parts.append("q/Enter: close")
            hint = "  ".join(hint_parts)
            try:
                win.addstr(box_h - 1, 2, hint[:box_w - 4], _HINT_STYLE)
            except curses.error:
                pass
            win.refresh()

            key = win.getch()
            if key in (ord("q"), ord("Q"), 27, curses.KEY_ENTER, ord("\n"), ord("\r"), curses.KEY_LEFT):
                return
            elif key in (curses.KEY_DOWN, ord("j")):
                if top + inner_h < len(lines):
                    top += 1
            elif key in (curses.KEY_UP, ord("k")):
                if top > 0:
                    top -= 1
            elif key == curses.KEY_NPAGE:
                top = min(top + inner_h, max(0, len(lines) - inner_h))
            elif key == curses.KEY_PPAGE:
                top = max(0, top - inner_h)
    finally:
        del win
        _restore()
