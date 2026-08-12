"""Cleanup action, plan, and backup models."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    """How dangerous an action is to perform.

    Only ``SAFE`` actions are auto-selected by a normal ``fix`` run.
    ``LOW``/``MEDIUM``/``HIGH`` all require explicit confirmation, and
    ``HIGH`` actions should be presented individually, never bundled.
    """

    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ReversibilityLevel(StrEnum):
    REVERSIBLE = "reversible"
    PARTIALLY_REVERSIBLE = "partially_reversible"
    IRREVERSIBLE = "irreversible"


class CleanupActionType(StrEnum):
    TERMINATE_PROCESS = "terminate_process"
    DELETE_CACHE = "delete_cache"
    ARCHIVE_SESSIONS = "archive_sessions"
    REMOVE_TEMP_WORKSPACE = "remove_temp_workspace"
    DELETE_LOG = "delete_log"


class CleanupAction(BaseModel):
    """A single, explicit, typed unit of cleanup work.

    Every field here exists so the plan shown to the user before execution
    is fully accurate: what happens, how risky it is, whether it can be
    undone, how much space/RAM it recovers, and why it was proposed.
    """

    id: str
    action_type: CleanupActionType
    description: str
    risk_level: RiskLevel
    reversible: ReversibilityLevel
    estimated_bytes: int = 0
    estimated_ram_bytes: int = 0
    affected_paths: list[Path] = Field(default_factory=list)
    affected_pids: list[int] = Field(default_factory=list)
    reason: str = ""
    finding_ids: list[str] = Field(default_factory=list)
    agent: str | None = None


class CleanupPlan(BaseModel):
    """An ordered, presentable set of actions plus what was excluded and why."""

    actions: list[CleanupAction] = Field(default_factory=list)
    excluded_actions: list[CleanupAction] = Field(default_factory=list)
    """Actions that exist but were not auto-selected (risk above SAFE)."""
    protected_notes: list[str] = Field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return sum(a.estimated_bytes for a in self.actions)

    @property
    def total_ram_bytes(self) -> int:
        return sum(a.estimated_ram_bytes for a in self.actions)


class BackupEntry(BaseModel):
    """One file/directory captured inside a backup, and how to restore it."""

    original_path: Path
    backup_path: Path
    was_directory: bool = False
    action_id: str = ""


class Backup(BaseModel):
    """A manifest describing everything captured before a destructive run."""

    backup_id: str
    created_at: str
    manifest_path: Path
    entries: list[BackupEntry] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)
    restored: bool = False
