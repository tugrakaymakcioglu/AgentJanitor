"""Deterministic, explainable health scoring.

No model or heuristic guesswork: the score is a pure function of the
findings a scan produced, category weights, and a fixed severity/confidence
deduction table. Every point lost is traceable back to one finding.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agentjanitor.models.finding import Confidence, Finding, Severity

CATEGORY_WEIGHTS: dict[str, int] = {
    "processes": 25,
    "storage": 20,
    "mcp": 20,
    "configuration": 15,
    "security": 20,
}

_SEVERITY_POINTS: dict[Severity, float] = {
    Severity.INFO: 0.0,
    Severity.LOW: 2.0,
    Severity.MEDIUM: 5.0,
    Severity.HIGH: 8.0,
    Severity.CRITICAL: 12.0,
}

_CONFIDENCE_MULTIPLIER: dict[Confidence, float] = {
    Confidence.LOW: 0.4,
    Confidence.MEDIUM: 0.7,
    Confidence.HIGH: 1.0,
    Confidence.CONFIRMED: 1.0,
}


class Deduction(BaseModel):
    finding_id: str
    category: str
    points: int
    description: str


class HealthScoreResult(BaseModel):
    score: int
    category_scores: dict[str, int] = Field(default_factory=dict)
    category_weights: dict[str, int] = Field(default_factory=lambda: dict(CATEGORY_WEIGHTS))
    deductions: list[Deduction] = Field(default_factory=list)


def _finding_deduction_points(finding: Finding) -> int:
    base = _SEVERITY_POINTS.get(finding.severity, 0.0)
    multiplier = _CONFIDENCE_MULTIPLIER.get(finding.confidence, 0.5)
    return round(base * multiplier)


def compute_health_score(
    findings: list[Finding],
    *,
    weights: dict[str, int] | None = None,
) -> HealthScoreResult:
    weights = weights or CATEGORY_WEIGHTS
    remaining: dict[str, float] = {category: float(w) for category, w in weights.items()}
    deductions: list[Deduction] = []

    for finding in sorted(findings, key=lambda f: (-_finding_deduction_points(f), f.id)):
        category = finding.category
        if category not in remaining:
            continue
        points = _finding_deduction_points(finding)
        if points <= 0:
            continue
        applied = min(points, remaining[category])
        if applied <= 0:
            continue
        remaining[category] -= applied
        deductions.append(
            Deduction(
                finding_id=finding.id,
                category=category,
                points=round(applied),
                description=finding.title,
            )
        )

    category_scores = {
        category: max(0, round(remaining_value))
        for category, remaining_value in remaining.items()
    }
    total = sum(category_scores.values())
    total = max(0, min(100, total))

    return HealthScoreResult(
        score=total,
        category_scores=category_scores,
        category_weights=dict(weights),
        deductions=deductions,
    )
