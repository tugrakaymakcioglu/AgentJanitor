"""Cross-platform path helpers.

Adapters need OS-specific *extra* locations (npm/npx caches, Windows
roaming/local AppData, macOS Application Support) without every adapter
re-deriving ``sys.platform`` logic itself. Known dotfile-style directories
used by Codex/Claude/Gemini (``~/.codex``, ``~/.claude``, ``~/.gemini``) are
consistent across OSes and belong in the adapters themselves, not here.
"""

from __future__ import annotations

import os
from pathlib import Path

from agentjanitor.platform.info import OS, current_os


def home_dir() -> Path:
    return Path.home()


def windows_appdata_roaming() -> Path | None:
    if current_os() != OS.WINDOWS:
        return None
    value = os.environ.get("APPDATA")
    return Path(value) if value else home_dir() / "AppData" / "Roaming"


def windows_appdata_local() -> Path | None:
    if current_os() != OS.WINDOWS:
        return None
    value = os.environ.get("LOCALAPPDATA")
    return Path(value) if value else home_dir() / "AppData" / "Local"


def macos_application_support() -> Path | None:
    if current_os() != OS.MACOS:
        return None
    return home_dir() / "Library" / "Application Support"


def macos_caches() -> Path | None:
    if current_os() != OS.MACOS:
        return None
    return home_dir() / "Library" / "Caches"


def linux_xdg_config() -> Path:
    value = os.environ.get("XDG_CONFIG_HOME")
    return Path(value) if value else home_dir() / ".config"


def linux_xdg_cache() -> Path:
    value = os.environ.get("XDG_CACHE_HOME")
    return Path(value) if value else home_dir() / ".cache"


def linux_xdg_data() -> Path:
    value = os.environ.get("XDG_DATA_HOME")
    return Path(value) if value else home_dir() / ".local" / "share"


def config_dirs(app_slug: str) -> list[Path]:
    """Plausible OS-native config locations for a vendor app slug.

    This is a fallback probe list, not an assumption that all of them
    exist. Callers should check existence before treating a path as real.
    """
    os_kind = current_os()
    candidates: list[Path] = []
    if os_kind == OS.WINDOWS:
        roaming = windows_appdata_roaming()
        if roaming:
            candidates.append(roaming / app_slug)
    elif os_kind == OS.MACOS:
        support = macos_application_support()
        if support:
            candidates.append(support / app_slug)
        candidates.append(linux_xdg_config() / app_slug)
    else:
        candidates.append(linux_xdg_config() / app_slug)
    return candidates


def cache_dirs(app_slug: str) -> list[Path]:
    os_kind = current_os()
    candidates: list[Path] = []
    if os_kind == OS.WINDOWS:
        local = windows_appdata_local()
        if local:
            candidates.append(local / app_slug / "Cache")
    elif os_kind == OS.MACOS:
        caches = macos_caches()
        if caches:
            candidates.append(caches / app_slug)
    else:
        candidates.append(linux_xdg_cache() / app_slug)
    return candidates


def app_data_dirs(app_slug: str) -> list[Path]:
    os_kind = current_os()
    candidates: list[Path] = []
    if os_kind == OS.WINDOWS:
        local = windows_appdata_local()
        if local:
            candidates.append(local / app_slug)
    elif os_kind == OS.MACOS:
        support = macos_application_support()
        if support:
            candidates.append(support / app_slug)
    else:
        candidates.append(linux_xdg_data() / app_slug)
    return candidates
