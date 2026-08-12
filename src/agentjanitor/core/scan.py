"""Top-level scan orchestration: adapters + scanners -> one ScanResult.

This is the single place that wires every scanner together, so the CLI,
JSON output, and tests all observe exactly the same pipeline.
"""

from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel, Field

from agentjanitor.adapters.base import AgentAdapter
from agentjanitor.core.config import DEFAULT_THRESHOLDS, Thresholds
from agentjanitor.core.health import HealthScoreResult, compute_health_score
from agentjanitor.models.agent import AgentInstallation
from agentjanitor.models.finding import Finding
from agentjanitor.models.mcp import MCPHealthCheck
from agentjanitor.models.process import AgentProcess
from agentjanitor.models.storage import StorageBreakdown
from agentjanitor.platform.processes import list_processes
from agentjanitor.scanners.configs import scan_configs
from agentjanitor.scanners.mcp import scan_mcp
from agentjanitor.scanners.processes import scan_processes
from agentjanitor.scanners.security import scan_security
from agentjanitor.scanners.storage import scan_storage

SCHEMA_VERSION = "1"


class ScanResult(BaseModel):
    schema_version: str = SCHEMA_VERSION
    installations: list[AgentInstallation] = Field(default_factory=list)
    agent_processes: list[AgentProcess] = Field(default_factory=list)
    storage_breakdowns: list[StorageBreakdown] = Field(default_factory=list)
    mcp_health_checks: list[MCPHealthCheck] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    health: HealthScoreResult

    def approved_roots(self, adapters: list[AgentAdapter]) -> dict[str, list[Path]]:
        return {adapter.name: adapter.approved_roots() for adapter in adapters}


def run_scan(
    adapters: list[AgentAdapter],
    *,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
    processes=None,
) -> ScanResult:
    now = time.time()
    installations = [adapter.detect() for adapter in adapters]

    all_processes = processes if processes is not None else list_processes()
    agent_processes, process_findings = scan_processes(
        adapters, all_processes, now=now, thresholds=thresholds
    )

    storage_breakdowns: list[StorageBreakdown] = []
    storage_findings: list[Finding] = []
    for adapter in adapters:
        breakdown, findings = scan_storage(adapter, now=now, thresholds=thresholds)
        storage_breakdowns.append(breakdown)
        storage_findings.extend(findings)

    mcp_health_checks, mcp_findings = scan_mcp(adapters)
    config_findings = scan_configs(adapters)
    security_findings = scan_security(adapters, thresholds=thresholds)

    all_findings = (
        process_findings + storage_findings + mcp_findings + config_findings + security_findings
    )
    health = compute_health_score(all_findings)

    return ScanResult(
        installations=installations,
        agent_processes=agent_processes,
        storage_breakdowns=storage_breakdowns,
        mcp_health_checks=mcp_health_checks,
        findings=all_findings,
        health=health,
    )
