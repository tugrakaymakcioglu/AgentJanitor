"""Adapter for OpenAI Codex CLI.

Known on-disk layout (consistent across Windows/macOS/Linux — Codex CLI
uses a home-relative dotfile, not OS-convention directories):

- ``~/.codex/config.toml``      user configuration, including ``mcp_servers``
- ``~/.codex/sessions/``        JSONL rollout files, one subtree per session
- ``~/.codex/log/``             log files
- executable: ``codex`` on PATH
"""

from __future__ import annotations

import shutil
from pathlib import Path

from agentjanitor.adapters.base import AgentAdapter
from agentjanitor.models.agent import AgentInstallation, DetectionConfidence, DetectionEvidence
from agentjanitor.models.mcp import MCPConfigFormat, MCPConfigScope, MCPConfigSource
from agentjanitor.models.process import AgentProcess, ProcessClassification, ProcessInfo
from agentjanitor.platform.paths import home_dir

_PROCESS_MARKERS = ("codex",)
_MCP_HELPER_MARKERS = ("mcp", "mcp-server", "mcp_server")


class CodexAdapter(AgentAdapter):
    def __init__(self, home: Path | None = None) -> None:
        self._home = home or home_dir()

    @property
    def name(self) -> str:
        return "OpenAI Codex"

    @property
    def slug(self) -> str:
        return "codex"

    @property
    def root_dir(self) -> Path:
        return self._home / ".codex"

    def detect(self) -> AgentInstallation:
        evidence: list[DetectionEvidence] = []
        executable_path = shutil.which("codex")
        if executable_path:
            evidence.append(
                DetectionEvidence(description="'codex' executable found on PATH", path=Path(executable_path))
            )

        config_file = self.root_dir / "config.toml"
        if config_file.exists():
            evidence.append(DetectionEvidence(description="~/.codex/config.toml exists", path=config_file))

        sessions_dir = self.root_dir / "sessions"
        has_sessions = sessions_dir.exists() and any(sessions_dir.iterdir())
        if has_sessions:
            evidence.append(DetectionEvidence(description="session history detected", path=sessions_dir))

        positive_signals = sum([bool(executable_path), config_file.exists(), has_sessions])
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
        candidates = [self.root_dir / "config.toml", self.root_dir / "auth.json"]
        return [p for p in candidates if p.exists()]

    def discover_sessions(self) -> list[Path]:
        sessions_dir = self.root_dir / "sessions"
        if not sessions_dir.exists():
            return []
        return sorted(p for p in sessions_dir.iterdir() if p.is_dir() or p.is_file())

    def discover_cache(self) -> list[Path]:
        cache_dir = self.root_dir / "cache"
        return [cache_dir] if cache_dir.exists() else []

    def discover_logs(self) -> list[Path]:
        log_dir = self.root_dir / "log"
        if not log_dir.exists():
            return []
        return sorted(p for p in log_dir.iterdir() if p.is_file())

    def discover_temp_workspaces(self) -> list[Path]:
        temp_dir = self.root_dir / "tmp"
        if not temp_dir.exists():
            return []
        return sorted(p for p in temp_dir.iterdir() if p.is_dir())

    def identify_processes(self, processes: list[ProcessInfo]) -> list[AgentProcess]:
        results: list[AgentProcess] = []
        for proc in processes:
            haystack = f"{proc.name} {proc.exe or ''} {proc.cmdline_str}".lower()
            if not any(marker in haystack for marker in _PROCESS_MARKERS):
                continue
            # Require the codex home directory to appear somewhere relevant,
            # or an explicit codex-named executable/script, to avoid matching
            # unrelated processes that merely mention "codex" in an argument.
            exe_name = Path(proc.exe).name.lower() if proc.exe else proc.name.lower()
            if "codex" not in exe_name and str(self.root_dir).lower() not in haystack:
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
        config_file = self.root_dir / "config.toml"
        if not config_file.exists():
            return []
        return [
            MCPConfigSource(
                agent=self.name,
                path=config_file,
                scope=MCPConfigScope.USER,
                format=MCPConfigFormat.TOML,
            )
        ]
