"""OS detection. The only place that should inspect ``sys.platform``."""

from __future__ import annotations

import sys
from enum import StrEnum


class OS(StrEnum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    OTHER = "other"


def current_os() -> OS:
    if sys.platform.startswith("win"):
        return OS.WINDOWS
    if sys.platform == "darwin":
        return OS.MACOS
    if sys.platform.startswith("linux"):
        return OS.LINUX
    return OS.OTHER
