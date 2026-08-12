"""MCP (Model Context Protocol) server configuration models."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class MCPTransport(StrEnum):
    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"
    UNKNOWN = "unknown"


class MCPConfigScope(StrEnum):
    USER = "user"
    PROJECT = "project"
    GLOBAL = "global"


class MCPConfigFormat(StrEnum):
    JSON = "json"
    YAML = "yaml"
    TOML = "toml"


class MCPHealthStatus(StrEnum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class MCPConfigSource(BaseModel):
    """A discovered location that may contain MCP server definitions."""

    agent: str
    path: Path
    scope: MCPConfigScope
    format: MCPConfigFormat


class MCPServerDefinition(BaseModel):
    """A single MCP server entry as read from an agent's configuration.

    ``source_path`` and ``source_key`` together identify exactly where this
    definition came from, which is required for duplicate detection across
    multiple config files/agents.
    """

    name: str
    agent: str
    source_path: Path
    source_key: str
    """The JSON/TOML/YAML key path this was read from, e.g. 'mcpServers.github'."""
    transport: MCPTransport = MCPTransport.UNKNOWN
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    env_keys: list[str] = Field(default_factory=list)
    """Names only, never values, of environment variables the server declares."""
    cwd: str | None = None

    def identity_signature(self) -> tuple[str, str, tuple[str, ...], str, tuple[str, ...]]:
        """A signature used to compare two definitions for equivalence.

        Two definitions with the same signature are almost certainly the
        same logical server duplicated across config scopes, not merely two
        servers that share a display name.
        """
        return (
            self.transport.value,
            (self.command or "").strip().lower(),
            tuple(sorted(a.strip() for a in self.args)),
            (self.url or "").strip().lower(),
            tuple(sorted(self.env_keys)),
        )


class MCPHealthCheck(BaseModel):
    server: MCPServerDefinition
    status: MCPHealthStatus
    problems: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
