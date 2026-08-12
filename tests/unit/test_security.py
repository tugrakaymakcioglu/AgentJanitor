"""Secret hygiene scanning: detection, redaction, and false-positive scoping."""

from __future__ import annotations

from agentjanitor.scanners.security import scan_security
from agentjanitor.utils.redact import fingerprint, scan_text_for_secrets
from tests.fixtures.builder import build_fixture_environment
from tests.fixtures.fake_adapter import FakeAgentAdapter


def test_fingerprint_never_reveals_the_full_secret():
    secret = "sk-FAKE1234567890TESTONLYDONOTUSE"
    fp = fingerprint(secret)
    assert secret not in fp
    assert fp.startswith("sk-")
    assert len(fp) < len(secret)


def test_scan_finds_openai_style_key_in_config():
    text = '{"api_key": "sk-FAKE1234567890TESTONLYDONOTUSE"}'
    matches = scan_text_for_secrets(text)
    assert any(m.pattern_id == "openai_key" for m in matches)
    for m in matches:
        assert "FAKE1234567890TESTONLYDONOTUSE" not in m.fingerprint


def test_finding_never_contains_the_raw_secret(tmp_path):
    env = build_fixture_environment(tmp_path)
    adapter = FakeAgentAdapter(env.root)
    findings = scan_security([adapter])
    assert findings
    for finding in findings:
        blob = f"{finding.title} {finding.description} {' '.join(finding.evidence)}"
        assert "FAKE1234567890TESTONLYDONOTUSE" not in blob


def test_generic_word_token_in_prose_is_not_flagged():
    """High-volume free text mentioning 'token' must not itself trigger a finding."""
    text = "The user asked how OAuth access tokens and refresh tokens are exchanged."
    matches = scan_text_for_secrets(text)
    assert matches == []
