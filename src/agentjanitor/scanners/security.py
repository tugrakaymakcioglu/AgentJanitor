"""Basic credential hygiene scanning.

Scope is deliberately narrow: only agent-related directories that adapters
themselves discovered are scanned, never the whole home directory. Matched
values are never stored or printed in full — only a short fingerprint.

Configuration files (structured, small, low false-positive risk) are
scanned with the full pattern set. Session/history content (free-form text
and code, at real-world scale often thousands of files) is scanned with
only the high-precision patterns, and the total number of files inspected
per agent is capped — otherwise a large, legitimate session history turns
a `scan` into a multi-minute operation for very little additional signal.
"""

from __future__ import annotations

from pathlib import Path

from agentjanitor.adapters.base import AgentAdapter
from agentjanitor.core.config import DEFAULT_THRESHOLDS, Thresholds
from agentjanitor.models.finding import Confidence, Finding, Severity
from agentjanitor.utils.redact import SECRET_PATTERNS, SecretPattern, scan_text_for_secrets
from agentjanitor.utils.safe_path import is_symlink_or_junction, iter_files_no_symlinks

_TEXT_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".txt", ".log", ".jsonl", ".env", ".md"}
_HIGH_PRECISION_PATTERNS = [p for p in SECRET_PATTERNS if p.high_precision]


def _candidate_files(paths: list[Path], thresholds: Thresholds) -> list[Path]:
    candidates: list[Path] = []
    for path in paths:
        if path.is_file():
            candidates.append(path)
            continue
        if path.is_dir() and not is_symlink_or_junction(path):
            files = iter_files_no_symlinks(path)[: thresholds.max_scanned_files_per_dir]
            candidates.extend(files)
    return [p for p in candidates if p.suffix.lower() in _TEXT_EXTENSIONS]


def _most_recent_first(paths: list[Path]) -> list[Path]:
    def mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    return sorted(paths, key=mtime, reverse=True)


def _scan_files(
    files: list[Path],
    *,
    adapter: AgentAdapter,
    patterns: list[SecretPattern],
    thresholds: Thresholds,
) -> list[Finding]:
    findings: list[Finding] = []
    for file_path in files:
        try:
            size = file_path.stat().st_size
        except OSError:
            continue
        partial = size > thresholds.max_scanned_file_bytes
        try:
            with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
                text = handle.read(thresholds.max_scanned_file_bytes)
        except OSError:
            continue

        matches = scan_text_for_secrets(text, patterns=patterns)
        for match in matches:
            description = f"Found in {file_path}"
            if partial:
                description += " (partial scan due to file size)"
            findings.append(
                Finding(
                    id=(
                        f"security.secret.{match.pattern_id}."
                        f"{abs(hash((str(file_path), match.line_number))) % 100_000}"
                    ),
                    category="security",
                    severity=Severity.HIGH,
                    confidence=Confidence.MEDIUM,
                    title=match.label,
                    description=description,
                    agent=adapter.name,
                    evidence=[f"fingerprint: {match.fingerprint}", f"line {match.line_number}"],
                    recommendation=(
                        "Move this credential to an environment variable or your OS "
                        "credential store, then rotate it."
                    ),
                    fix_available=False,
                    metadata={"file": str(file_path)},
                )
            )
    return findings


def scan_security(
    adapters: list[AgentAdapter],
    *,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> list[Finding]:
    findings: list[Finding] = []

    for adapter in adapters:
        config_files = _candidate_files(adapter.discover_config(), thresholds)
        findings.extend(
            _scan_files(config_files, adapter=adapter, patterns=SECRET_PATTERNS, thresholds=thresholds)
        )

        session_files = _candidate_files(adapter.discover_sessions(), thresholds)
        prioritized = _most_recent_first(session_files)
        scanned = prioritized[: thresholds.max_security_scan_files_per_agent]
        skipped = len(prioritized) - len(scanned)

        findings.extend(
            _scan_files(scanned, adapter=adapter, patterns=_HIGH_PRECISION_PATTERNS, thresholds=thresholds)
        )

        if skipped > 0:
            findings.append(
                Finding(
                    id=f"security.scan-truncated.{adapter.slug}",
                    category="security",
                    severity=Severity.INFO,
                    confidence=Confidence.CONFIRMED,
                    title=f"Session security scan limited to the {len(scanned)} most recent files",
                    description=(
                        f"{skipped} older session file(s) for {adapter.name} were not scanned "
                        "for credential hygiene, to keep `scan` fast."
                    ),
                    agent=adapter.name,
                    recommendation="Run `agentjanitor security` with a narrower scope for a deeper sweep.",
                    fix_available=False,
                )
            )

    return findings
