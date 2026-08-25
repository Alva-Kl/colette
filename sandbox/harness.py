#!/usr/bin/env python3
"""Drive `colette tui` non-interactively over a real pty and detect crashes.

Gives the colette process a real controlling terminal (required for both
`sys.stdout.isatty()` in cmd_tui and for curses itself), then feeds it a
scripted key sequence and watches the output for a raw, unhandled Python
traceback — exactly what curses.wrapper's `finally` clause exposes on the
real terminal once it tears down curses and re-raises an exception that
escaped every layer of the TUI.

Usage (inside the sandbox container, after `colette` is built/installed):
    python3 sandbox/harness.py --scenario link-project-cancel-name
    python3 sandbox/harness.py --list
Exit code 0 + "OK" on stderr  = clean run, no crash.
Exit code 1 + "CRASHED"       = a Traceback appeared in the transcript.
"""
import argparse
import os
import pty
import select
import sys
import time

ESC = b"\x1b"
ENTER = b"\r"
# Multi-byte CSI arrow sequences (b"\x1b[A" etc.) exist mainly to document the
# encoding — DON'T use them for scripted navigation below. A lone ESC byte
# immediately followed by more bytes is ambiguous to curses (it can't always
# tell "Escape" from "the start of an arrow-key sequence" within the short
# window set by Menu.run()'s scr.timeout(200)), and Menu.run() treats a bare
# ESC as "quit the whole TUI" — so a misread arrow key can silently exit the
# app instead of moving the cursor. colette_cli/tui/menu.py's Menu.run()
# explicitly also accepts vi-style "j"/"k" for down/up, which are single,
# unambiguous bytes — use those for all scripted navigation instead.
UP = b"\x1b[A"
DOWN = b"\x1b[B"
LEFT = b"\x1b[D"
RIGHT = b"\x1b[C"
NAV_DOWN = b"j"
NAV_UP = b"k"

# Each step is one of:
#   ("wait", seconds)          — just sleep, let the screen redraw/settle
#   ("key", bytes)             — write one (possibly multi-byte) key atomically
#   ("text", "...")            — type each character, then implicit small delays
# Menu navigation is done by typing the item's first distinguishing letter
# is NOT supported by this widget (arrow-key list only) — steps below assume
# whatever screen order colette_cli/tui/screens.py currently produces; if
# that order changes, update DOWN counts here rather than the harness logic.

# The splash screen auto-dismisses after 2s on its own (colette_cli/tui/splash.py)
# — waiting it out avoids the ambiguity of a keypress either dismissing the
# splash OR being consumed by the main menu, depending on timing.
_SPLASH_WAIT = 2.3

# main_menu_items() order: Projects, Machines, Debug, Monitor — the menu
# cursor starts on the first selectable item ("Projects"), so no DOWN
# presses are needed before selecting it.
#
# project_list_items() order, with the sandbox's 2 seeded fake projects
# ("fake-api", "fake-web-app", sorted by name) under the single "local"
# machine: [machine label (unselectable)], fake-api, fake-web-app,
# "Start All — local", "Stop All — local", "Update All — local",
# [separator (unselectable)], "Start All", "Stop All", "Update All",
# "Create project", "Link project" — 10 selectable items total. The cursor
# starts on "fake-api" (the 1st selectable) — "Create project" is the 9th
# selectable (8 DOWN presses away), "Link project" is the 10th (9 DOWN
# presses away). Overshooting by even one wraps the cursor back to
# "fake-api" (Menu._next_selectable wraps around) and silently opens the
# wrong item — verified live while building this harness. If the seeded
# project count/names change (seed_home.py), these counts must be updated
# to match.
_DOWN_TO_CREATE_PROJECT = 8
_DOWN_TO_LINK_PROJECT = 9

SCENARIOS = {
    # Link project is now a single form() screen (fields: path, machine,
    # template) — Enter on a field advances focus to the next one; ESC at
    # any point cancels the WHOLE form (not just the field under focus).
    # This is the confirmed historical crash: cancelling used to fall back
    # to the raw directory basename ("Fake Linked Dir" — invalid slug),
    # reaching cmd_link unwrapped and crashing via an uncaught SystemExit
    # from err(). Here we advance through path and machine, then cancel on
    # the name field — cmd_link must never be called and the TUI must not
    # crash.
    "link-project-cancel-name": [
        ("wait", _SPLASH_WAIT),
        ("key", ENTER),                              # main menu: select "Projects"
        ("wait", 0.3),
        *([("key", NAV_DOWN)] * _DOWN_TO_LINK_PROJECT),
        ("key", ENTER),                              # select "Link project"
        ("wait", 0.3),
        ("text", "/root/colette-projects/Fake Linked Dir"),
        ("key", ENTER),                              # path field -> advance to machine
        ("wait", 0.3),
        ("key", ENTER),                              # machine field (choice) -> advance to name
        ("wait", 0.3),
        ("key", ESC),                                # cancel the whole form
        ("wait", 0.5),
    ],
    # Create project is now a single form() screen (fields: name, machine,
    # template) — same advance-with-Enter / whole-form-ESC mechanism as
    # link-project above.
    "create-project-cancel-machine": [
        ("wait", _SPLASH_WAIT),
        ("key", ENTER),                              # main menu: select "Projects"
        ("wait", 0.3),
        *([("key", NAV_DOWN)] * _DOWN_TO_CREATE_PROJECT),
        ("key", ENTER),                              # select "Create project"
        ("wait", 0.3),
        ("text", "sandbox-test-proj"),
        ("key", ENTER),                              # name field -> advance to machine
        ("wait", 0.3),
        ("key", ESC),                                # cancel the whole form
        ("wait", 0.5),
    ],
    "create-project-cancel-template": [
        ("wait", _SPLASH_WAIT),
        ("key", ENTER),                              # main menu: select "Projects"
        ("wait", 0.3),
        *([("key", NAV_DOWN)] * _DOWN_TO_CREATE_PROJECT),
        ("key", ENTER),                              # select "Create project"
        ("wait", 0.3),
        ("text", "sandbox-test-proj2"),
        ("key", ENTER),                              # name field -> advance to machine
        ("wait", 0.3),
        ("key", ENTER),                              # machine field (choice) -> advance to template
        ("wait", 0.3),
        ("key", ESC),                                # cancel the whole form
        ("wait", 0.5),
    ],
    # New tree smoke test: Machines -> {machine} -> Templates -> Add
    # template, then cancel — exercises the unified Machines home and the
    # new _add_template_interactive form() flow end to end.
    "machines-add-template-cancel": [
        ("wait", _SPLASH_WAIT),
        ("key", NAV_DOWN),                           # main menu: move to "Machines"
        ("key", ENTER),                               # select "Machines"
        ("wait", 0.3),
        ("key", NAV_DOWN),                            # move past "Add machine" to the first machine
        ("key", ENTER),                               # select the machine
        ("wait", 0.3),
        *([("key", NAV_DOWN)] * 4),                   # Edit, Set as default, Rename, Templates
        ("key", ENTER),                                # select "Templates"
        ("wait", 0.3),
        ("key", ENTER),                                # select "Add template"
        ("wait", 0.3),
        ("key", ESC),                                  # cancel the whole form
        ("wait", 0.5),
    ],
}


def spawn(colette_bin):
    pid, fd = pty.fork()
    if pid == 0:
        os.environ["TERM"] = "xterm-256color"
        os.execvp(colette_bin, [colette_bin, "tui"])
    return pid, fd


def send(fd, data: bytes, delay: float = 0.05):
    os.write(fd, data)
    time.sleep(delay)


def drain(fd, timeout: float = 0.2) -> bytes:
    out = b""
    while select.select([fd], [], [], timeout)[0]:
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
    return out


# An unhandled generic Exception dumps a visible traceback once curses tears
# down. An unhandled SystemExit (from err()) does NOT — sys.exit() reaching
# the top of the program is deliberately silent, by design — so scanning for
# this text alone misses that failure mode entirely (verified: an
# err()-raised SystemExit from cmd_link killed the whole process with no
# trace of this string anywhere in the transcript). The authoritative signal
# for either case is that the colette process has already exited on its own
# BEFORE the harness ever sent its own "q" — that should never happen from
# merely cancelling one field.
CRASH_MARKER = b"Traceback (most recent call last):"


def run_scenario(colette_bin: str, steps) -> tuple[bool, bytes]:
    pid, fd = spawn(colette_bin)
    transcript = b""
    exited_early = False
    try:
        transcript += drain(fd, 1.0)  # let the splash screen render
        for step in steps:
            kind = step[0]
            if kind == "wait":
                time.sleep(step[1])
            elif kind == "key":
                send(fd, step[1])
            elif kind == "text":
                for ch in step[1].encode():
                    send(fd, bytes([ch]), delay=0.01)
            else:
                raise ValueError(f"unknown step kind: {kind!r}")
            transcript += drain(fd)

        # Poll rather than checking once: there's a small window between the
        # process finishing its exit (curses.wrapper's endwin() already ran,
        # visible in the transcript) and the kernel actually marking it
        # reapable — a single immediate WNOHANG check can race and miss it.
        for _ in range(10):
            done_pid, _ = os.waitpid(pid, os.WNOHANG)
            if done_pid == pid:
                exited_early = True
                break
            time.sleep(0.2)

        if not exited_early:
            send(fd, b"q")
            time.sleep(0.3)
            transcript += drain(fd, 0.5)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass
    return exited_early or CRASH_MARKER in transcript, transcript


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS))
    parser.add_argument("--list", action="store_true", help="list available scenarios and exit")
    parser.add_argument(
        "--colette-bin",
        default=os.path.expanduser("~/.local/bin/colette"),
        help="path to the colette binary (default: ~/.local/bin/colette)",
    )
    args = parser.parse_args()

    if args.list or not args.scenario:
        for name in sorted(SCENARIOS):
            print(name)
        sys.exit(0)

    if not os.path.exists(args.colette_bin):
        print(f"colette binary not found at {args.colette_bin} — build it first:", file=sys.stderr)
        print("  ./scripts/build.sh && ./scripts/build.sh prod && ./scripts/install.sh", file=sys.stderr)
        sys.exit(2)

    crashed, transcript = run_scenario(args.colette_bin, SCENARIOS[args.scenario])
    sys.stdout.buffer.write(transcript)
    print()
    print("CRASHED" if crashed else "OK", file=sys.stderr)
    sys.exit(1 if crashed else 0)


if __name__ == "__main__":
    main()
