"""A deterministic, fully synthetic adapter used to test the whole pipeline
(scan -> findings -> health score -> cleanup plan -> dry-run -> mutation ->
undo) without depending on any real coding agent being installed.
"""

from __future__ import annotations

from pathlib import Path

from agentjanitor.adapters.base import AgentAdapter
from agentjanitor.models.agent import AgentInstallation, DetectionConfidence, DetectionEvidence
from agentjanitor.models.mcp import MCPConfigFormat, MCPConfigScope, MCPConfigSource
from agentjanitor.models.process import AgentProcess, ProcessClassification, ProcessInfo

FAKE_MARKER = "--fakeagent-marker"


class FakeAgentAdapter(AgentAdapter):
    """Adapter over a fixture directory tree built by ``tests.fixtures.builder``."""

    def __init__(self, root: Path, agent_name: str = "Fake Agent") -> None:
        self.root = root
        self._name = agent_name

    @property
    def name(self) -> str:
        return self._name

    def detect(self) -> AgentInstallation:
        config_dir = self.root / "config"
        evidence = []
        if config_dir.exists():
            evidence.append(DetectionEvidence(description="config directory exists", path=config_dir))
        return AgentInstallation(
            agent=self.name,
            detected=config_dir.exists(),
            confidence=DetectionConfidence.HIGH if config_dir.exists() else DetectionConfidence.NONE,
            evidence=evidence,
        )

    def discover_config(self) -> list[Path]:
        config_dir = self.root / "config"
        if not config_dir.exists():
            return []
        return sorted(p for p in config_dir.glob("*") if p.is_file())

    def discover_sessions(self) -> list[Path]:
        sessions_dir = self.root / "sessions"
        if not sessions_dir.exists():
            return []
        return sorted(p for p in sessions_dir.iterdir() if p.is_dir())

    def discover_cache(self) -> list[Path]:
        cache_dir = self.root / "cache"
        return [cache_dir] if cache_dir.exists() else []

    def discover_logs(self) -> list[Path]:
        logs_dir = self.root / "logs"
        if not logs_dir.exists():
            return []
        return sorted(p for p in logs_dir.iterdir() if p.is_file())

    def discover_temp_workspaces(self) -> list[Path]:
        temp_dir = self.root / "temp"
        if not temp_dir.exists():
            return []
        return sorted(p for p in temp_dir.iterdir() if p.is_dir())

    def identify_processes(self, processes: list[ProcessInfo]) -> list[AgentProcess]:
        results: list[AgentProcess] = []
        for proc in processes:
            if FAKE_MARKER not in proc.cmdline_str:
                continue
            role = "mcp-server" if "--role=mcp" in proc.cmdline else "main"
            results.append(
                AgentProcess(
                    process=proc,
                    agent=self.name,
                    role=role,
                    classification=ProcessClassification.UNKNOWN,
                )
            )
        return results

    def discover_mcp_configs(self) -> list[MCPConfigSource]:
        config_dir = self.root / "config"
        mcp_file = config_dir / "mcp.json"
        if not mcp_file.exists():
            return []
        return [
            MCPConfigSource(
                agent=self.name,
                path=mcp_file,
                scope=MCPConfigScope.USER,
                format=MCPConfigFormat.JSON,
            )
        ]
