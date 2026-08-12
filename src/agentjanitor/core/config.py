"""Configurable thresholds used across scanners.

Kept in one place so behavior stays deterministic and explainable, and so
a future config file / CLI flag can override defaults without hunting
through scanner modules.
"""

from __future__ import annotations

from pydantic import BaseModel


class Thresholds(BaseModel):
    session_archive_days: int = 60
    """Sessions older than this are ARCHIVE_CANDIDATE rather than RECENT."""

    session_stale_days: int = 365
    """Sessions older than this are STALE rather than ARCHIVE_CANDIDATE."""

    session_recent_days: int = 3
    """Sessions modified within this window are RECENT rather than ACTIVE-adjacent."""

    stale_temp_days: int = 7
    """Temp workspaces older than this are candidates for removal."""

    process_idle_seconds: float = 4 * 3600
    """A process must be idle (0% CPU) for at least this long to count as a signal."""

    active_session_window_seconds: float = 15 * 60
    """A session touched within this window is treated as actively in use,
    and any process whose working directory falls under it is protected."""

    max_scanned_file_bytes: int = 5 * 1024 * 1024
    """Per-file cap for expensive content inspection (secret scanning)."""

    max_scanned_files_per_dir: int = 2000
    """Cap on number of files inspected per directory tree for secrets/size scans."""

    max_security_scan_files_per_agent: int = 300
    """Global cap on files inspected for secrets per agent, prioritized by
    most-recently-modified. Session trees can hold many thousands of files;
    without this cap, a single `scan` could spend minutes reading them."""


DEFAULT_THRESHOLDS = Thresholds()
