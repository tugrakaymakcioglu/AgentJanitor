"""Agent installation detection models."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class DetectionConfidence(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DetectionEvidence(BaseModel):
    """One signal that contributed to (or against) a detection verdict."""

    description: str
    positive: bool = True
    path: Path | None = None


class AgentInstallation(BaseModel):
    """Result of probing whether a given coding agent is installed."""

    agent: str
    detected: bool
    confidence: DetectionConfidence = DetectionConfidence.NONE
    evidence: list[DetectionEvidence] = Field(default_factory=list)
    version: str | None = None
    executable_path: Path | None = None
