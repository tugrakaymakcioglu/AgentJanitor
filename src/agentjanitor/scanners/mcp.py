"""MCP configuration parsing, duplicate detection, and health checks.

Normal ``scan`` never executes a configured MCP command — only static
properties (executable presence, path existence, URL well-formedness) are
checked. Anything that would run third-party code requires explicit
opt-in elsewhere.
"""

from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path
from urllib.parse import urlparse

import yaml

from agentjanitor.adapters.base import AgentAdapter
from agentjanitor.models.finding import Confidence, Finding, Severity
from agentjanitor.models.mcp import (
    MCPConfigFormat,
    MCPConfigSource,
    MCPHealthCheck,
    MCPHealthStatus,
    MCPServerDefinition,
    MCPTransport,
)


def _load_raw(source: MCPConfigSource) -> dict:
    try:
        text = source.path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        if source.format == MCPConfigFormat.JSON:
            return json.loads(text)
        if source.format == MCPConfigFormat.YAML:
            return yaml.safe_load(text) or {}
        if source.format == MCPConfigFormat.TOML:
            return tomllib.loads(text)
    except (json.JSONDecodeError, yaml.YAMLError, tomllib.TOMLDecodeError):
        return {}
    return {}


def _extract_servers_dict(raw: dict) -> dict:
    """Find the server map regardless of which known key an agent uses.

    Handles both a flat map (Claude/Gemini's ``mcpServers``) and Claude
    Code's nested per-project shape (``projects.<path>.mcpServers``),
    merging every project scope's servers into one map for duplicate
    detection purposes.
    """
    for key in ("mcpServers", "mcp_servers", "servers"):
        value = raw.get(key)
        if isinstance(value, dict):
            return value

    merged: dict = {}
    projects = raw.get("projects")
    if isinstance(projects, dict):
        for project_path, project_data in projects.items():
            if not isinstance(project_data, dict):
                continue
            servers = project_data.get("mcpServers")
            if isinstance(servers, dict):
                for server_name, spec in servers.items():
                    merged[f"{project_path}:{server_name}"] = spec
    return merged


def parse_mcp_config(source: MCPConfigSource) -> list[MCPServerDefinition]:
    raw = _load_raw(source)
    servers_dict = _extract_servers_dict(raw)
    definitions: list[MCPServerDefinition] = []

    for server_name, spec in servers_dict.items():
        if not isinstance(spec, dict):
            continue
        url = spec.get("url")
        command = spec.get("command")
        transport = MCPTransport.UNKNOWN
        if url:
            transport_value = str(spec.get("transport", "")).lower()
            if transport_value in (t.value for t in MCPTransport):
                transport = MCPTransport(transport_value)
            else:
                transport = MCPTransport.SSE if "sse" in transport_value else MCPTransport.HTTP
        elif command:
            transport = MCPTransport.STDIO

        env = spec.get("env") or {}
        definitions.append(
            MCPServerDefinition(
                name=server_name,
                agent=source.agent,
                source_path=source.path,
                source_key=f"mcpServers.{server_name}",
                transport=transport,
                command=command,
                args=list(spec.get("args") or []),
                url=url,
                env_keys=sorted(env.keys()) if isinstance(env, dict) else [],
                cwd=spec.get("cwd"),
            )
        )
    return definitions


def discover_all_mcp_servers(adapters: list[AgentAdapter]) -> list[MCPServerDefinition]:
    definitions: list[MCPServerDefinition] = []
    for adapter in adapters:
        for source in adapter.discover_mcp_configs():
            definitions.extend(parse_mcp_config(source))
    return definitions


def find_duplicate_servers(
    definitions: list[MCPServerDefinition],
) -> list[list[MCPServerDefinition]]:
    """Group definitions that are almost certainly the same logical server.

    Grouping is by full identity signature (command/args/url/transport/env
    keys), not by display name — two servers named "github" with different
    commands are not treated as duplicates.
    """
    groups: dict[tuple[str, str, tuple[str, ...], str, tuple[str, ...]], list[MCPServerDefinition]] = {}
    for definition in definitions:
        groups.setdefault(definition.identity_signature(), []).append(definition)
    return [group for group in groups.values() if len(group) > 1]


def check_server_health(definition: MCPServerDefinition) -> MCPHealthCheck:
    problems: list[str] = []
    suggestions: list[str] = []
    status = MCPHealthStatus.OK

    if not definition.source_path.exists():
        problems.append(f"config file no longer exists: {definition.source_path}")
        status = MCPHealthStatus.FAIL

    if definition.url:
        parsed = urlparse(definition.url)
        if not parsed.scheme or not parsed.netloc:
            problems.append(f"URL is not well-formed: {definition.url}")
            suggestions.append("Fix the configured URL.")
            status = MCPHealthStatus.FAIL
    elif definition.command:
        resolved = shutil.which(definition.command)
        if resolved is None and not Path(definition.command).exists():
            problems.append(f"executable '{definition.command}' not found in PATH")
            suggestions.append(
                f"Install the required tool or update the MCP command for '{definition.name}'."
            )
            status = MCPHealthStatus.FAIL
        if definition.cwd and not Path(definition.cwd).exists():
            problems.append(f"configured working directory does not exist: {definition.cwd}")
            status = MCPHealthStatus.FAIL
    else:
        problems.append("no command or URL configured")
        status = MCPHealthStatus.FAIL

    return MCPHealthCheck(server=definition, status=status, problems=problems, suggestions=suggestions)


def scan_mcp(adapters: list[AgentAdapter]) -> tuple[list[MCPHealthCheck], list[Finding]]:
    definitions = discover_all_mcp_servers(adapters)
    health_checks = [check_server_health(d) for d in definitions]
    findings: list[Finding] = []

    duplicate_groups = find_duplicate_servers(definitions)
    if duplicate_groups:
        for group in duplicate_groups:
            locations = [f"{d.agent} ({d.source_path})" for d in group]
            findings.append(
                Finding(
                    id=f"mcp.duplicate.{group[0].name}.{abs(hash(group[0].identity_signature())) % 10_000}",
                    category="mcp",
                    severity=Severity.LOW,
                    confidence=Confidence.HIGH,
                    title=f"Duplicate MCP server definition: '{group[0].name}'",
                    description=(
                        "The same command/args/URL is configured in multiple places. "
                        "This wastes context and can lead to duplicate running servers."
                    ),
                    evidence=locations,
                    recommendation="Consolidate into a single configuration source.",
                    fix_available=False,
                )
            )

    failing = [hc for hc in health_checks if hc.status == MCPHealthStatus.FAIL]
    if failing:
        findings.append(
            Finding(
                id="mcp.unreachable",
                category="mcp",
                severity=Severity.MEDIUM,
                confidence=Confidence.HIGH,
                title=f"{len(failing)} unreachable/broken MCP server definition(s)",
                description="These servers reference a missing executable, bad URL, or missing config.",
                evidence=[f"{hc.server.name}: {'; '.join(hc.problems)}" for hc in failing],
                recommendation="Run `agentjanitor doctor` for per-server remediation steps.",
                fix_available=False,
            )
        )

    return health_checks, findings
