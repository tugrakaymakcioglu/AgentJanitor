"""Secret pattern matching and redaction.

Matched values are never returned in full. ``fingerprint`` keeps only a
short prefix/suffix so a finding can be cross-referenced without ever
reproducing anything an attacker (or careless log) could use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SecretPattern:
    id: str
    label: str
    pattern: re.Pattern[str]
    high_precision: bool = True
    """False for patterns prone to false positives in free-form text (e.g.
    conversation transcripts full of code and the word "token"). Only
    ``high_precision`` patterns are applied to session/history content;
    the full set applies to structured configuration files."""


SECRET_PATTERNS: list[SecretPattern] = [
    SecretPattern("openai_key", "Possible OpenAI API key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    SecretPattern(
        "anthropic_key",
        "Possible Anthropic API key",
        re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"),
    ),
    SecretPattern(
        "google_api_key", "Possible Google API key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")
    ),
    SecretPattern(
        "github_token",
        "Possible GitHub token",
        re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    ),
    SecretPattern(
        "aws_access_key", "Possible AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")
    ),
    SecretPattern(
        "slack_token", "Possible Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")
    ),
    SecretPattern(
        "private_key_marker",
        "Possible private key material",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    ),
    SecretPattern(
        "bearer_token",
        "Possible bearer token",
        re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_.=]{20,}"),
        high_precision=False,
    ),
    SecretPattern(
        "generic_secret_assignment",
        "Possible hard-coded credential",
        re.compile(
            r"(?i)(api[_-]?key|secret|token|password|passwd)\s*[:=]\s*"
            r"['\"]([A-Za-z0-9\-_./+=]{16,})['\"]"
        ),
        high_precision=False,
    ),
]


@dataclass(frozen=True)
class SecretMatch:
    pattern_id: str
    label: str
    fingerprint: str
    line_number: int | None = None


def fingerprint(value: str) -> str:
    """Return a heavily redacted stand-in for a matched secret value.

    Never reveals enough to reconstruct or use the credential; only enough
    for a human to recognize "yes, that's the one I rotated."
    """
    value = value.strip().strip("'\"")
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}...{value[-4:]}"


def scan_text_for_secrets(
    text: str,
    max_lines: int = 20000,
    *,
    patterns: list[SecretPattern] | None = None,
    max_matches: int = 200,
) -> list[SecretMatch]:
    """Scan text content for known secret patterns, line by line.

    Bounded by ``max_lines`` so a pathological file can't cause runaway
    scanning time, and by ``max_matches`` so a file that is mostly
    false-positive noise can't blow up downstream reporting; callers are
    expected to have already bounded overall bytes read before calling this.
    """
    patterns = patterns if patterns is not None else SECRET_PATTERNS
    matches: list[SecretMatch] = []
    for line_number, line in enumerate(text.splitlines()[:max_lines], start=1):
        for pattern in patterns:
            found = pattern.pattern.search(line)
            if found:
                value = found.group(0)
                matches.append(
                    SecretMatch(
                        pattern_id=pattern.id,
                        label=pattern.label,
                        fingerprint=fingerprint(value),
                        line_number=line_number,
                    )
                )
                if len(matches) >= max_matches:
                    return matches
    return matches
