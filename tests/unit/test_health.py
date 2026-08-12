"""Health score must be deterministic and fully explainable."""

from __future__ import annotations

from agentjanitor.core.health import compute_health_score
from agentjanitor.models.finding import Confidence, Finding, Severity


def _finding(category: str, severity: Severity, confidence: Confidence, fid: str) -> Finding:
    return Finding(
        id=fid,
        category=category,
        severity=severity,
        confidence=confidence,
        title=f"finding {fid}",
        description="test",
    )


def test_no_findings_is_perfect_score():
    result = compute_health_score([])
    assert result.score == 100
    assert result.deductions == []


def test_deterministic_for_same_input():
    findings = [
        _finding("processes", Severity.MEDIUM, Confidence.HIGH, "p1"),
        _finding("security", Severity.HIGH, Confidence.MEDIUM, "s1"),
    ]
    result_a = compute_health_score(findings)
    result_b = compute_health_score(findings)
    assert result_a == result_b


def test_every_deduction_traces_to_a_finding():
    findings = [
        _finding("processes", Severity.MEDIUM, Confidence.HIGH, "p1"),
        _finding("mcp", Severity.HIGH, Confidence.HIGH, "m1"),
    ]
    result = compute_health_score(findings)
    deducted_ids = {d.finding_id for d in result.deductions}
    assert deducted_ids == {"p1", "m1"}
    assert result.score < 100


def test_category_score_never_goes_negative():
    findings = [_finding("security", Severity.CRITICAL, Confidence.CONFIRMED, f"s{i}") for i in range(20)]
    result = compute_health_score(findings)
    assert result.category_scores["security"] == 0
    assert result.score >= 0


def test_info_severity_never_deducts():
    findings = [_finding("storage", Severity.INFO, Confidence.CONFIRMED, "i1")]
    result = compute_health_score(findings)
    assert result.score == 100
    assert result.deductions == []


def test_unknown_category_is_ignored_not_crashed():
    findings = [_finding("not-a-real-category", Severity.CRITICAL, Confidence.CONFIRMED, "x1")]
    result = compute_health_score(findings)
    assert result.score == 100
