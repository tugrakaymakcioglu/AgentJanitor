"""--json output must be stable, versioned, and fully JSON-serializable."""

from __future__ import annotations

import json

from agentjanitor.core.scan import run_scan
from agentjanitor.reporting.json_schema import scan_result_to_json
from tests.fixtures.builder import build_fixture_environment
from tests.fixtures.fake_adapter import FakeAgentAdapter


def test_scan_json_report_round_trips(tmp_path):
    env = build_fixture_environment(tmp_path)
    adapter = FakeAgentAdapter(env.root)
    result = run_scan([adapter], processes=[])

    payload = scan_result_to_json(result)
    text = json.dumps(payload)
    reloaded = json.loads(text)

    assert reloaded["schema_version"] == "1"
    assert "summary" in reloaded
    assert "health_score" in reloaded["summary"]
    assert isinstance(reloaded["findings"], list)
    assert isinstance(reloaded["agents"], list)
    assert reloaded["agents"][0]["agent"] == "Fake Agent"
