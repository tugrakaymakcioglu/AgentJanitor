"""Deeper, per-agent diagnostics for ``agentjanitor doctor``.

Each check is independent and produces its own PASS/WARN/FAIL plus
actionable detail lines, reusing the same scanners as ``scan`` — doctor is
a different presentation of the same conservative analysis, not a
separate, riskier code path.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from agentjanitor.adapters.base import AgentAdapter
from agentjanitor.core.config import DEFAULT_THRESHOLDS, Thresholds
from agentjanitor.models.mcp import MCPHealthStatus
from agentjanitor.models.process import ProcessClassification
from agentjanitor.platform.processes import list_processes
from agentjanitor.scanners.configs import scan_configs
from agentjanitor.scanners.mcp import scan_mcp
from agentjanitor.scanners.processes import scan_processes
from agentjanitor.scanners.security import scan_security
from agentjanitor.scanners.storage import scan_storage
from agentjanitor.utils.format import human_bytes


class CheckStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class DoctorCheck(BaseModel):
    name: str
    status: CheckStatus
    details: list[str] = Field(default_factory=list)


class AgentDoctorReport(BaseModel):
    agent: str
    checks: list[DoctorCheck] = Field(default_factory=list)

    @property
    def overall(self) -> CheckStatus:
        statuses = [c.status for c in self.checks]
        if CheckStatus.FAIL in statuses:
            return CheckStatus.FAIL
        if CheckStatus.WARN in statuses:
            return CheckStatus.WARN
        return CheckStatus.PASS


def _check_installation(adapter: AgentAdapter) -> DoctorCheck:
    installation = adapter.detect()
    if installation.detected:
        return DoctorCheck(name="Installation", status=CheckStatus.PASS)
    return DoctorCheck(
        name="Installation",
        status=CheckStatus.FAIL,
        details=["No installation evidence found for this agent."],
    )


def _check_executable(adapter: AgentAdapter) -> DoctorCheck:
    installation = adapter.detect()
    if installation.executable_path is not None:
        return DoctorCheck(name="Executable", status=CheckStatus.PASS)
    if installation.detected:
        return DoctorCheck(
            name="Executable",
            status=CheckStatus.WARN,
            details=["Configuration/data found, but no executable located on PATH."],
        )
    return DoctorCheck(name="Executable", status=CheckStatus.FAIL, details=["Not found."])


def _check_configuration(adapter: AgentAdapter) -> DoctorCheck:
    findings = scan_configs([adapter])
    if not findings:
        return DoctorCheck(name="Configuration", status=CheckStatus.PASS)
    return DoctorCheck(
        name="Configuration",
        status=CheckStatus.FAIL,
        details=[f.description for f in findings],
    )


def _check_sessions(adapter: AgentAdapter) -> DoctorCheck:
    sessions = adapter.discover_sessions()
    if sessions:
        return DoctorCheck(name="Sessions", status=CheckStatus.PASS)
    if adapter.detect().detected:
        return DoctorCheck(
            name="Sessions",
            status=CheckStatus.WARN,
            details=["Agent is installed but no session history was found."],
        )
    return DoctorCheck(name="Sessions", status=CheckStatus.PASS)


def _check_processes(adapter: AgentAdapter, thresholds: Thresholds) -> DoctorCheck:
    all_processes = list_processes()
    agent_processes, _ = scan_processes([adapter], all_processes, thresholds=thresholds)
    confirmed = [
        p for p in agent_processes if p.classification == ProcessClassification.CONFIRMED_ORPHANED
    ]
    likely = [
        p for p in agent_processes if p.classification == ProcessClassification.LIKELY_ORPHANED
    ]
    if confirmed:
        return DoctorCheck(
            name="Processes",
            status=CheckStatus.FAIL,
            details=[f"{len(confirmed)} confirmed orphan process(es); safe to clean up with `fix`."],
        )
    if likely:
        return DoctorCheck(
            name="Processes",
            status=CheckStatus.WARN,
            details=[f"{len(likely)} possibly orphaned process(es); review with `processes`."],
        )
    return DoctorCheck(name="Processes", status=CheckStatus.PASS)


def _check_mcp(adapter: AgentAdapter) -> DoctorCheck:
    health_checks, _ = scan_mcp([adapter])
    failing = [hc for hc in health_checks if hc.status == MCPHealthStatus.FAIL]
    if failing:
        details = []
        for hc in failing:
            details.append(f"Configured command: {hc.server.command or hc.server.url}")
            details.append(f"Problem: {'; '.join(hc.problems)}")
            details.extend(f"Suggested action: {s}" for s in hc.suggestions)
        return DoctorCheck(name="MCP", status=CheckStatus.FAIL, details=details)
    if not health_checks:
        return DoctorCheck(name="MCP", status=CheckStatus.PASS)
    return DoctorCheck(name="MCP", status=CheckStatus.PASS)


def _check_disk(adapter: AgentAdapter, thresholds: Thresholds) -> DoctorCheck:
    breakdown, _ = scan_storage(adapter, thresholds=thresholds)
    warn_threshold = 500 * 1024 * 1024
    if breakdown.safe_reclaimable_bytes >= warn_threshold:
        return DoctorCheck(
            name="Disk",
            status=CheckStatus.WARN,
            details=[f"{human_bytes(breakdown.safe_reclaimable_bytes)} safely reclaimable."],
        )
    return DoctorCheck(name="Disk", status=CheckStatus.PASS)


def _check_security(adapter: AgentAdapter, thresholds: Thresholds) -> DoctorCheck:
    findings = scan_security([adapter], thresholds=thresholds)
    if findings:
        max_shown = 10
        details = [f.title for f in findings[:max_shown]]
        if len(findings) > max_shown:
            details.append(f"... and {len(findings) - max_shown} more (see `agentjanitor security --json`)")
        return DoctorCheck(name="Security", status=CheckStatus.FAIL, details=details)
    return DoctorCheck(name="Security", status=CheckStatus.PASS)


def run_doctor(
    adapters: list[AgentAdapter],
    *,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> list[AgentDoctorReport]:
    reports = []
    for adapter in adapters:
        checks = [
            _check_installation(adapter),
            _check_executable(adapter),
            _check_configuration(adapter),
            _check_sessions(adapter),
            _check_processes(adapter, thresholds),
            _check_mcp(adapter),
            _check_disk(adapter, thresholds),
            _check_security(adapter, thresholds),
        ]
        reports.append(AgentDoctorReport(agent=adapter.name, checks=checks))
    return reports
