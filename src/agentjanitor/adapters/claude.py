"""Adapter for Claude Code.

Known on-disk layout (consistent across Windows/macOS/Linux):

- ``~/.claude.json``            top-level user config; may contain
                                 ``mcpServers`` and a ``projects`` map with
                                 per-project MCP servers
- ``~/.claude/settings.json``   user settings
- ``~/.claude/projects/``       per-project session transcripts (``*.jsonl``)
- ``~/.claude/todos/``          per-session todo-list state
- ``~/.claude/shell-snapshots/`` captured shell state, safe to treat as cache
- ``~/.claude/statsig/``        local analytics cache
- ``<project>/.mcp.json``       project-scoped MCP servers (checked only in cwd)
- executable: ``claude`` on PATH
"""

from __future__ import annotations

import shutil
from pathlib import Path

from agentjanitor.adapters.base import AgentAdapter
from agentjanitor.models.agent import AgentInstallation, DetectionConfidence, DetectionEvidence
from agentjanitor.models.mcp import MCPConfigFormat, MCPConfigScope, MCPConfigSource
from agentjanitor.models.process import AgentProcess, ProcessClassification, ProcessInfo
from agentjanitor.platform.paths import home_dir

_MCP_HELPER_MARKERS = ("mcp", "mcp-server", "mcp_server")


class ClaudeCodeAdapter(AgentAdapter):
    def __init__(self, home: Path | None = None, cwd: Path | None = None) -> None:
        self._home = home or home_dir()
        self._cwd = cwd or Path.cwd()

    @property
    def name(self) -> str:
        return "Claude Code"

    @property
    def slug(self) -> str:
        return "claude-code"

    @property
    def root_dir(self) -> Path:
        return self._home / ".claude"

    @property
    def user_config_file(self) -> Path:
        return self._home / ".claude.json"

    def detect(self) -> AgentInstallation:
        evidence: list[DetectionEvidence] = []
        executable_path = shutil.which("claude")
        if executable_path:
            evidence.append(
                DetectionEvidence(description="'claude' executable found on PATH", path=Path(executable_path))
            )

        if self.root_dir.exists():
            evidence.append(DetectionEvidence(description="~/.claude exists", path=self.root_dir))

        projects_dir = self.root_dir / "projects"
        has_sessions = projects_dir.exists() and any(projects_dir.iterdir())
        if has_sessions:
            evidence.append(DetectionEvidence(description="session history detected", path=projects_dir))

        positive_signals = sum([bool(executable_path), self.root_dir.exists(), has_sessions])
        if positive_signals == 0:
            confidence = DetectionConfidence.NONE
        elif positive_signals == 1:
            confidence = DetectionConfidence.LOW
        elif positive_signals == 2:
            confidence = DetectionConfidence.MEDIUM
        else:
            confidence = DetectionConfidence.HIGH

        return AgentInstallation(
            agent=self.name,
            detected=positive_signals > 0,
            confidence=confidence,
            evidence=evidence,
            executable_path=Path(executable_path) if executable_path else None,
        )

    def discover_config(self) -> list[Path]:
        candidates = [self.user_config_file, self.root_dir / "settings.json"]
        return [p for p in candidates if p.exists()]

    def discover_sessions(self) -> list[Path]:
        projects_dir = self.root_dir / "projects"
        if not projects_dir.exists():
            return []
        return sorted(p for p in projects_dir.iterdir() if p.is_dir())

    def discover_cache(self) -> list[Path]:
        candidates = [self.root_dir / "statsig", self.root_dir / "shell-snapshots"]
        return [p for p in candidates if p.exists()]

    def discover_logs(self) -> list[Path]:
        log_dir = self.root_dir / "logs"
        if not log_dir.exists():
            return []
        return sorted(p for p in log_dir.iterdir() if p.is_file())

    def discover_temp_workspaces(self) -> list[Path]:
        todos_dir = self.root_dir / "todos"
        if not todos_dir.exists():
            return []
        return sorted(p for p in todos_dir.iterdir() if p.is_dir())

    def identify_processes(self, processes: list[ProcessInfo]) -> list[AgentProcess]:
        results: list[AgentProcess] = []
        for proc in processes:
            haystack = f"{proc.name} {proc.exe or ''} {proc.cmdline_str}".lower()
            exe_name = Path(proc.exe).name.lower() if proc.exe else proc.name.lower()
            is_claude_exe = "claude" in exe_name
            references_claude_home = str(self.root_dir).lower() in haystack
            if not (is_claude_exe or references_claude_home):
                continue
            role = "mcp-server" if any(m in haystack for m in _MCP_HELPER_MARKERS) else "main"
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
        sources: list[MCPConfigSource] = []
        if self.user_config_file.exists():
            sources.append(
                MCPConfigSource(
                    agent=self.name,
                    path=self.user_config_file,
                    scope=MCPConfigScope.USER,
                    format=MCPConfigFormat.JSON,
                )
            )
        project_mcp_file = self._cwd / ".mcp.json"
        if project_mcp_file.exists():
            sources.append(
                MCPConfigSource(
                    agent=self.name,
                    path=project_mcp_file,
                    scope=MCPConfigScope.PROJECT,
                    format=MCPConfigFormat.JSON,
                )
            )
        return sources
