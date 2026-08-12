"""Normalized finding model produced by every scanner."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    """How bad the underlying condition is, independent of certainty."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Confidence(StrEnum):
    """How sure AgentJanitor is that the finding is real, independent of severity."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CONFIRMED = "CONFIRMED"


class Finding(BaseModel):
    """A single, normalized observation surfaced by a scanner.

    Severity and confidence are deliberately separate axes: a finding can be
    severe but uncertain (e.g. "possible secret") or certain but low severity
    (e.g. "440MB of stale temp workspaces").
    """

    id: str
    category: str
    """e.g. 'processes', 'storage', 'mcp', 'security', 'configuration'"""
    severity: Severity
    confidence: Confidence
    title: str
    description: str
    agent: str | None = None
    evidence: list[str] = Field(default_factory=list)
    recommendation: str | None = None
    fix_available: bool = False
    fix_action_ids: list[str] = Field(default_factory=list)
    """Ids of CleanupAction objects that would resolve this finding, if any."""
    estimated_bytes: int | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
