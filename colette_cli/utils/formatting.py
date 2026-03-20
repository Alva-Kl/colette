"""Output formatting utilities (colors, text styling)."""

import sys
import os


# ANSI colours — disabled when stdout/stderr is not a TTY or NO_COLOR is set
def _colour_support(fd):
    return fd.isatty() and "NO_COLOR" not in os.environ


_COL_OUT = _colour_support(sys.stdout)
_COL_ERR = _colour_support(sys.stderr)


def _c(code, text, use):
    return f"{code}{text}\033[0m" if use else text


def bold(t):
    return _c("\033[1m", t, _COL_OUT)


def dim(t):
    return _c("\033[2m", t, _COL_OUT)


def cyan(t):
    return _c("\033[36m", t, _COL_OUT)


def green(t):
    return _c("\033[32m", t, _COL_OUT)


def red(t):
    return _c("\033[31m", t, _COL_ERR)


def yellow(t):
    return _c("\033[33m", t, _COL_ERR)


def err(msg):
    print(f"{red('Error:')} {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg):
    print(f"{yellow('Warning:')} {msg}", file=sys.stderr)


def info(msg):
    print(f"{green('✓')} {msg}")
