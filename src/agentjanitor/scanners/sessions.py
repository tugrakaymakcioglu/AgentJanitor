"""Session/workspace age classification.

Old sessions can contain useful history and are never deleted by default;
they are classified so the storage scanner and cleanup planner can prefer
archiving over deletion. Classification is time-based only — liveness
(whether a process is actually using a session right now) is the process
scanner's job, layered on top via active-session protection.
"""

from __future__ import annotations

import time
from pathlib import Path

from agentjanitor.core.config import DEFAULT_THRESHOLDS, Thresholds
from agentjanitor.models.storage import SessionStatus


def classify_session_age(
    path: Path,
    *,
    now: float | None = None,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> SessionStatus:
    now = now if now is not None else time.time()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return SessionStatus.UNKNOWN

    age_seconds = max(0.0, now - mtime)
    age_days = age_seconds / 86400

    if age_seconds <= thresholds.active_session_window_seconds:
        return SessionStatus.ACTIVE
    if age_days < thresholds.session_archive_days:
        return SessionStatus.RECENT
    if age_days < thresholds.session_stale_days:
        return SessionStatus.ARCHIVE_CANDIDATE
    return SessionStatus.STALE


def classify_temp_workspace_age(
    path: Path,
    *,
    now: float | None = None,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> SessionStatus:
    now = now if now is not None else time.time()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return SessionStatus.UNKNOWN

    age_days = max(0.0, now - mtime) / 86400
    return SessionStatus.STALE if age_days >= thresholds.stale_temp_days else SessionStatus.ACTIVE
