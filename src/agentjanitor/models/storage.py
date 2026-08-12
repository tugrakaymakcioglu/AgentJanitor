"""Storage and session classification models."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class DiskCategory(StrEnum):
    SESSIONS = "sessions"
    LOGS = "logs"
    CACHE = "cache"
    PLUGIN_CACHE = "plugin_cache"
    TEMP_WORKSPACE = "temp_workspace"
    OLD_VERSIONS = "old_versions"
    REPORTS = "reports"
    AGENT_STATE = "agent_state"


class SessionStatus(StrEnum):
    """Lifecycle classification for a single session/workspace directory.

    Only ``STALE`` temp workspaces and ``ARCHIVE_CANDIDATE`` sessions are
    ever proposed for cleanup, and archiving (not deletion) is preferred.
    """

    ACTIVE = "ACTIVE"
    RECENT = "RECENT"
    ARCHIVE_CANDIDATE = "ARCHIVE_CANDIDATE"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class StorageItem(BaseModel):
    """A single directory or file counted toward storage usage."""

    path: Path
    category: DiskCategory
    agent: str
    size_bytes: int
    last_modified: float | None = None
    status: SessionStatus = SessionStatus.UNKNOWN
    is_symlink: bool = False


class StorageBreakdown(BaseModel):
    """Aggregated storage figures for one agent, split by disposition."""

    agent: str
    total_bytes: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)
    safe_reclaimable_bytes: int = 0
    archive_candidate_bytes: int = 0
    unknown_bytes: int = 0
    items: list[StorageItem] = Field(default_factory=list)
