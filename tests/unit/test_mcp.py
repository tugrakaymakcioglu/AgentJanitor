"""MCP parsing, duplicate detection (by identity, not name), and health checks."""

from __future__ import annotations

from agentjanitor.models.mcp import MCPHealthStatus
from agentjanitor.scanners.mcp import (
    check_server_health,
    discover_all_mcp_servers,
    find_duplicate_servers,
    scan_mcp,
)
from tests.fixtures.builder import build_fixture_environment
from tests.fixtures.fake_adapter import FakeAgentAdapter


def test_parses_all_configured_servers(tmp_path):
    env = build_fixture_environment(tmp_path)
    adapter = FakeAgentAdapter(env.root)
    definitions = discover_all_mcp_servers([adapter])
    names = {d.name for d in definitions}
    assert names == {"github", "github-project-copy", "broken-server", "remote-server"}


def test_duplicate_detection_is_by_identity_not_name(tmp_path):
    env = build_fixture_environment(tmp_path)
    adapter = FakeAgentAdapter(env.root)
    definitions = discover_all_mcp_servers([adapter])
    groups = find_duplicate_servers(definitions)
    assert len(groups) == 1
    duplicate_names = {d.name for d in groups[0]}
    assert duplicate_names == {"github", "github-project-copy"}


def test_broken_command_fails_health_check(tmp_path):
    env = build_fixture_environment(tmp_path)
    adapter = FakeAgentAdapter(env.root)
    definitions = discover_all_mcp_servers([adapter])
    broken = next(d for d in definitions if d.name == "broken-server")
    result = check_server_health(broken)
    assert result.status == MCPHealthStatus.FAIL
    assert result.problems


def test_remote_server_with_valid_url_passes(tmp_path):
    env = build_fixture_environment(tmp_path)
    adapter = FakeAgentAdapter(env.root)
    definitions = discover_all_mcp_servers([adapter])
    remote = next(d for d in definitions if d.name == "remote-server")
    result = check_server_health(remote)
    assert result.status == MCPHealthStatus.OK


def test_scan_mcp_never_executes_configured_commands(tmp_path, monkeypatch):
    """A normal scan must never actually invoke a configured MCP command."""
    import subprocess

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("scan_mcp must never spawn a subprocess")

    monkeypatch.setattr(subprocess, "run", _fail_if_called)
    monkeypatch.setattr(subprocess, "Popen", _fail_if_called)

    env = build_fixture_environment(tmp_path)
    adapter = FakeAgentAdapter(env.root)
    scan_mcp([adapter])  # must not raise


def test_scan_mcp_produces_duplicate_and_unreachable_findings(tmp_path):
    env = build_fixture_environment(tmp_path)
    adapter = FakeAgentAdapter(env.root)
    _, findings = scan_mcp([adapter])
    ids = {f.id for f in findings}
    assert any(i.startswith("mcp.duplicate") for i in ids)
    assert "mcp.unreachable" in ids
