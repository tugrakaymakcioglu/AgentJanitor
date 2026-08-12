"""Stable, versioned JSON output for ``--json`` flags.

``schema_version`` is bumped only on breaking changes, so downstream
scripts/CI integrations have something to pin against.
"""

from __future__ import annotations

from typing import Any

from agentjanitor.core.scan import ScanResult


def scan_result_to_json(result: ScanResult) -> dict[str, Any]:
    return {
        "schema_version": result.schema_version,
        "agents": [i.model_dump(mode="json") for i in result.installations],
        "processes": [ap.model_dump(mode="json") for ap in result.agent_processes],
        "storage": [b.model_dump(mode="json") for b in result.storage_breakdowns],
        "mcp": [h.model_dump(mode="json") for h in result.mcp_health_checks],
        "findings": [f.model_dump(mode="json") for f in result.findings],
        "summary": {
            "health_score": result.health.score,
            "category_scores": result.health.category_scores,
            "category_weights": result.health.category_weights,
        },
    }
