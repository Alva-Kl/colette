"""Shared TUI runtime state accessible from any screen or form."""

import threading

stdscr = None

running_jobs: list[str] = []
_jobs_lock = threading.Lock()


def add_job(name: str) -> None:
    with _jobs_lock:
        running_jobs.append(name)


def remove_job(name: str) -> None:
    with _jobs_lock:
        try:
            running_jobs.remove(name)
        except ValueError:
            pass
