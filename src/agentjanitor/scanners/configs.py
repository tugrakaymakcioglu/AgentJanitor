"""Generic configuration file validation.

Complements ``scanners.mcp`` (which understands MCP-specific structure) by
checking that every discovered config file is at least well-formed for its
apparent format. A parse failure here often explains a downstream "agent
won't start" symptom.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml

from agentjanitor.adapters.base import AgentAdapter
from agentjanitor.models.finding import Confidence, Finding, Severity

_PARSERS = {
    ".json": lambda text: json.loads(text),
    ".yaml": lambda text: yaml.safe_load(text),
    ".yml": lambda text: yaml.safe_load(text),
    ".toml": lambda text: tomllib.loads(text),
}


def _validate_file(path: Path) -> str | None:
    parser = _PARSERS.get(path.suffix.lower())
    if parser is None:
        return None
    try:
        text = path.read_text(encoding="utf-8")
        parser(text)
    except OSError as exc:
        return f"could not read file: {exc}"
    except (json.JSONDecodeError, yaml.YAMLError, tomllib.TOMLDecodeError) as exc:
        return f"failed to parse as {path.suffix.lstrip('.').upper()}: {exc}"
    return None


def scan_configs(adapters: list[AgentAdapter]) -> list[Finding]:
    findings: list[Finding] = []
    for adapter in adapters:
        for config_path in adapter.discover_config():
            error = _validate_file(config_path)
            if error:
                findings.append(
                    Finding(
                        id=f"config.malformed.{adapter.slug}.{config_path.name}",
                        category="configuration",
                        severity=Severity.HIGH,
                        confidence=Confidence.CONFIRMED,
                        title=f"Malformed configuration file for {adapter.name}",
                        description=error,
                        agent=adapter.name,
                        evidence=[str(config_path)],
                        recommendation="Fix or restore this configuration file from backup.",
                        fix_available=False,
                        metadata={"file": str(config_path)},
                    )
                )
    return findings
