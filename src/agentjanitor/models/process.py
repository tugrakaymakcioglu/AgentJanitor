"""Process domain models.

These describe raw OS process data and the agent-specific interpretation
layered on top of it. Classification is intentionally conservative: see
``ProcessClassification`` for the full state machine.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class ProcessInfo(BaseModel):
    """Raw, OS-level information about a running process.

    This is a normalized view of ``psutil.Process`` (or an equivalent fake
    for tests) and carries no agent-specific interpretation.
    """

    pid: int
    ppid: int | None = None
    name: str
    exe: str | None = None
    cmdline: list[str] = Field(default_factory=list)
    create_time: float | None = None
    status: str | None = None
    cpu_percent: float | None = None
    rss_bytes: int | None = None
    username: str | None = None
    cwd: str | None = None
    parent_chain: list[int] = Field(default_factory=list)

    @property
    def cmdline_str(self) -> str:
        return " ".join(self.cmdline)


class ProcessClassification(StrEnum):
    """Confidence ladder for whether a process is safe to touch.

    Only ``CONFIRMED_ORPHANED`` may ever be auto-selected by a normal
    ``fix`` run. Everything else requires explicit user review/selection.
    """

    ACTIVE = "ACTIVE"
    LIKELY_ACTIVE = "LIKELY_ACTIVE"
    UNKNOWN = "UNKNOWN"
    LIKELY_ORPHANED = "LIKELY_ORPHANED"
    CONFIRMED_ORPHANED = "CONFIRMED_ORPHANED"


class AgentProcess(BaseModel):
    """A process AgentJanitor believes is related to a coding agent."""

    process: ProcessInfo
    agent: str
    role: str
    """e.g. 'main', 'mcp-server', 'helper', 'wrapper'"""
    classification: ProcessClassification = ProcessClassification.UNKNOWN
    classification_reasons: list[str] = Field(default_factory=list)
    """Every signal that contributed to the classification, for auditability."""
    protected: bool = False
    protected_reason: str | None = None
    working_dir: Path | None = None
    estimated_ram_bytes: int | None = None

    def mark_protected(self, reason: str) -> None:
        self.protected = True
        self.protected_reason = reason
        if self.classification in (
            ProcessClassification.LIKELY_ORPHANED,
            ProcessClassification.CONFIRMED_ORPHANED,
        ):
            self.classification = ProcessClassification.LIKELY_ACTIVE
            self.classification_reasons.append(f"protected: {reason}")
