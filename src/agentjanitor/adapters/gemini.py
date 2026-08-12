"""Adapter for Gemini CLI.

Support is experimental (see README): Gemini CLI's on-disk layout is less
consistently documented across versions than Codex/Claude Code, so
detection confidence here is capped more conservatively and paths are
treated as best-effort probes rather than guaranteed locations.

Probed layout:

- ``~/.gemini/settings.json``   user settings, including ``mcpServers``
- ``~/.gemini/tmp/``            per-project checkpoints/session state
- executable: ``gemini`` on PATH
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


class GeminiCLIAdapter(AgentAdapter):
    def __init__(self, home: Path | None = None) -> None:
        self._home = home or home_dir()

    @property
    def name(self) -> str:
        return "Gemini CLI"

    @property
    def slug(self) -> str:
        return "gemini-cli"

    @property
    def root_dir(self) -> Path:
        return self._home / ".gemini"

    def detect(self) -> AgentInstallation:
        evidence: list[DetectionEvidence] = []
        executable_path = shutil.which("gemini")
        if executable_path:
            evidence.append(
                DetectionEvidence(description="'gemini' executable found on PATH", path=Path(executable_path))
            )

        settings_file = self.root_dir / "settings.json"
        if settings_file.exists():
            evidence.append(
                DetectionEvidence(description="~/.gemini/settings.json exists", path=settings_file)
            )

        tmp_dir = self.root_dir / "tmp"
        has_sessions = tmp_dir.exists() and any(tmp_dir.iterdir())
        if has_sessions:
            evidence.append(DetectionEvidence(description="session/checkpoint data detected", path=tmp_dir))

        positive_signals = sum([bool(executable_path), settings_file.exists(), has_sessions])
        # Capped below HIGH: Gemini CLI's layout is not verified as stable
        # across versions the way Codex/Claude Code's is (see module docstring).
        if positive_signals == 0:
            confidence = DetectionConfidence.NONE
        elif positive_signals == 1:
            confidence = DetectionConfidence.LOW
        else:
            confidence = DetectionConfidence.MEDIUM

        return AgentInstallation(
            agent=self.name,
            detected=positive_signals > 0,
            confidence=confidence,
            evidence=evidence,
            executable_path=Path(executable_path) if executable_path else None,
        )

    def discover_config(self) -> list[Path]:
        settings_file = self.root_dir / "settings.json"
        return [settings_file] if settings_file.exists() else []

    def discover_sessions(self) -> list[Path]:
        tmp_dir = self.root_dir / "tmp"
        if not tmp_dir.exists():
            return []
        return sorted(p for p in tmp_dir.iterdir() if p.is_dir())

    def discover_cache(self) -> list[Path]:
        cache_dir = self.root_dir / "cache"
        return [cache_dir] if cache_dir.exists() else []

    def discover_logs(self) -> list[Path]:
        log_dir = self.root_dir / "logs"
        if not log_dir.exists():
            return []
        return sorted(p for p in log_dir.iterdir() if p.is_file())

    def discover_temp_workspaces(self) -> list[Path]:
        # Gemini CLI does not have a separately documented temp-workspace
        # directory distinct from its session checkpoints; leaving this
        # empty is safer than guessing at an undocumented location.
        return []

    def identify_processes(self, processes: list[ProcessInfo]) -> list[AgentProcess]:
        results: list[AgentProcess] = []
        for proc in processes:
            haystack = f"{proc.name} {proc.exe or ''} {proc.cmdline_str}".lower()
            exe_name = Path(proc.exe).name.lower() if proc.exe else proc.name.lower()
            is_gemini_exe = "gemini" in exe_name
            references_gemini_home = str(self.root_dir).lower() in haystack
            if not (is_gemini_exe or references_gemini_home):
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
        settings_file = self.root_dir / "settings.json"
        if not settings_file.exists():
            return []
        return [
            MCPConfigSource(
                agent=self.name,
                path=settings_file,
                scope=MCPConfigScope.USER,
                format=MCPConfigFormat.JSON,
            )
        ]
