"""Shared TUI runtime state accessible from any screen or form."""

import threading
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Notification:
    label: str
    success: bool
    output: str
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    seen: bool = False


stdscr = None

notifications: list[Notification] = []
notifications_lock = threading.Lock()

running_tasks: int = 0
running_tasks_lock = threading.Lock()
