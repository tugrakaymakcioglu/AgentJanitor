"""Real adapters must work against a synthetic home directory — never require
the real agent to be installed on the test machine."""

from __future__ import annotations

import json

from agentjanitor.adapters.claude import ClaudeCodeAdapter
from agentjanitor.adapters.codex import CodexAdapter
from agentjanitor.adapters.gemini import GeminiCLIAdapter
from agentjanitor.models.agent import DetectionConfidence
from agentjanitor.models.process import ProcessInfo


def test_codex_not_detected_on_empty_home(tmp_path):
    adapter = CodexAdapter(home=tmp_path)
    installation = adapter.detect()
    assert installation.detected is False
    assert installation.confidence == DetectionConfidence.NONE
    assert adapter.discover_config() == []
    assert adapter.discover_sessions() == []


def test_codex_detected_from_config_and_sessions(tmp_path):
    codex_dir = tmp_path / ".codex"
    (codex_dir).mkdir()
    (codex_dir / "config.toml").write_text(
        '[mcp_servers.github]\ncommand = "npx"\nargs = ["-y", "server-github"]\n'
    )
    sessions_dir = codex_dir / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "session-1.jsonl").write_text("{}\n")

    adapter = CodexAdapter(home=tmp_path)
    installation = adapter.detect()
    assert installation.detected is True
    assert installation.confidence in (DetectionConfidence.MEDIUM, DetectionConfidence.HIGH)
    assert adapter.discover_config() == [codex_dir / "config.toml"]
    assert adapter.discover_sessions() == [sessions_dir / "session-1.jsonl"]

    configs = adapter.discover_mcp_configs()
    assert len(configs) == 1
    assert configs[0].path == codex_dir / "config.toml"


def test_codex_identifies_own_processes_not_unrelated_ones(tmp_path):
    adapter = CodexAdapter(home=tmp_path)
    codex_proc = ProcessInfo(
        pid=1,
        ppid=1,
        name="codex",
        exe="/usr/local/bin/codex",
        cmdline=["codex", "mcp-server"],
        cwd=None,
    )
    unrelated_proc = ProcessInfo(
        pid=2, ppid=1, name="chrome", exe="/usr/bin/chrome", cmdline=["chrome"], cwd=None
    )
    matched = adapter.identify_processes([codex_proc, unrelated_proc])
    assert {ap.process.pid for ap in matched} == {1}
    assert matched[0].role == "mcp-server"


def test_claude_code_detected_from_dotfile(tmp_path):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (tmp_path / ".claude.json").write_text(
        json.dumps({"mcpServers": {"github": {"command": "npx", "args": ["-y", "x"]}}})
    )
    projects_dir = claude_dir / "projects"
    projects_dir.mkdir()
    (projects_dir / "project-1").mkdir()

    adapter = ClaudeCodeAdapter(home=tmp_path, cwd=tmp_path)
    installation = adapter.detect()
    assert installation.detected is True
    assert adapter.discover_sessions() == [projects_dir / "project-1"]

    configs = adapter.discover_mcp_configs()
    assert len(configs) == 1
    assert configs[0].path == tmp_path / ".claude.json"


def test_claude_code_picks_up_project_scoped_mcp_json(tmp_path):
    (tmp_path / ".claude").mkdir()
    project_dir = tmp_path / "my-project"
    project_dir.mkdir()
    (project_dir / ".mcp.json").write_text(json.dumps({"mcpServers": {}}))

    adapter = ClaudeCodeAdapter(home=tmp_path, cwd=project_dir)
    configs = adapter.discover_mcp_configs()
    assert any(c.path == project_dir / ".mcp.json" for c in configs)


def test_gemini_confidence_is_capped_below_high(tmp_path):
    gemini_dir = tmp_path / ".gemini"
    gemini_dir.mkdir()
    (gemini_dir / "settings.json").write_text(json.dumps({"mcpServers": {}}))
    tmp_dir = gemini_dir / "tmp"
    tmp_dir.mkdir()
    (tmp_dir / "project-hash").mkdir()

    adapter = GeminiCLIAdapter(home=tmp_path)
    installation = adapter.detect()
    assert installation.detected is True
    assert installation.confidence != DetectionConfidence.HIGH


def test_gemini_not_detected_on_empty_home(tmp_path):
    adapter = GeminiCLIAdapter(home=tmp_path)
    installation = adapter.detect()
    assert installation.detected is False
