"""Agent adapter interface.

Every provider-specific fact (paths, executable names, process signatures,
config formats) must live inside a concrete adapter, never in a scanner.
Scanners consume adapters through this interface only, which is what lets
a new agent be added without touching scanner code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from agentjanitor.models.agent import AgentInstallation
from agentjanitor.models.mcp import MCPConfigSource
from agentjanitor.models.process import AgentProcess, ProcessInfo


class AgentAdapter(ABC):
    """Provider-specific knowledge for one coding agent."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable, human-readable agent name, e.g. 'Claude Code'."""

    @property
    def slug(self) -> str:
        """Filesystem/JSON-safe identifier, e.g. 'claude-code'."""
        return self.name.lower().replace(" ", "-")

    @abstractmethod
    def detect(self) -> AgentInstallation:
        """Probe for installation and return a confidence-scored verdict."""

    @abstractmethod
    def discover_config(self) -> list[Path]:
        """Return existing agent configuration file paths."""

    @abstractmethod
    def discover_sessions(self) -> list[Path]:
        """Return existing session/history storage directories."""

    @abstractmethod
    def discover_cache(self) -> list[Path]:
        """Return existing cache/plugin-cache directories."""

    @abstractmethod
    def discover_logs(self) -> list[Path]:
        """Return existing log file/directory paths."""

    @abstractmethod
    def discover_temp_workspaces(self) -> list[Path]:
        """Return existing temporary task-workspace directories."""

    @abstractmethod
    def identify_processes(self, processes: list[ProcessInfo]) -> list[AgentProcess]:
        """Classify which of the given OS processes belong to this agent.

        Implementations must use combinations of signals (command line,
        executable path, parent process, working directory) rather than
        matching on process name alone.
        """

    @abstractmethod
    def discover_mcp_configs(self) -> list[MCPConfigSource]:
        """Return locations that may contain this agent's MCP server definitions."""

    def approved_roots(self) -> list[Path]:
        """Every directory this adapter is allowed to measure/mutate within.

        Used by the cleanup engine and storage scanner to validate that no
        action ever touches a path outside what this adapter itself
        discovered. Subclasses may override for a tighter set, but the
        default union of config/sessions/cache/logs/temp is a safe baseline.
        """
        roots: list[Path] = []
        for path in (
            self.discover_config()
            + self.discover_sessions()
            + self.discover_cache()
            + self.discover_logs()
            + self.discover_temp_workspaces()
        ):
            parent = path if path.is_dir() else path.parent
            if parent not in roots:
                roots.append(parent)
        return roots
