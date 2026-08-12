"""Central place a new adapter is registered so the CLI can discover it."""

from __future__ import annotations

from agentjanitor.adapters.base import AgentAdapter
from agentjanitor.adapters.claude import ClaudeCodeAdapter
from agentjanitor.adapters.codex import CodexAdapter
from agentjanitor.adapters.gemini import GeminiCLIAdapter


def all_adapters() -> list[AgentAdapter]:
    return [CodexAdapter(), ClaudeCodeAdapter(), GeminiCLIAdapter()]
