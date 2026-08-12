"""Process discovery and conservative orphan classification.

Design constraint (non-negotiable, see project safety principles): no
single signal — age, dead parent, 0% CPU, or "it's an MCP process" — may
ever be enough to mark a process ``CONFIRMED_ORPHANED``. Confirmation
requires the parent to be gone AND sustained idleness AND at least one
corroborating structural signal (missing working directory or an
unexpected duplicate), and it never applies to an agent's main process.
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

from agentjanitor.adapters.base import AgentAdapter
from agentjanitor.core.config import DEFAULT_THRESHOLDS, Thresholds
from agentjanitor.models.finding import Confidence, Finding, Severity
from agentjanitor.models.process import AgentProcess, ProcessClassification, ProcessInfo
from agentjanitor.platform.processes import process_uptime_seconds

MAIN_ROLE = "main"


def _duplicate_signature(proc: ProcessInfo) -> tuple[str, ...]:
    return (proc.exe or proc.name, *proc.cmdline[1:])


def _find_duplicates(agent_processes: list[AgentProcess]) -> set[int]:
    """Return pids that are part of an unexpectedly duplicated command line.

    A single MCP server started once is normal. The *same* command/args
    running multiple times concurrently is the "leaked helper" pattern this
    exists to catch.
    """
    signatures = Counter(_duplicate_signature(ap.process) for ap in agent_processes)
    duplicate_pids: set[int] = set()
    for ap in agent_processes:
        if signatures[_duplicate_signature(ap.process)] > 1:
            duplicate_pids.add(ap.process.pid)
    return duplicate_pids


def classify_processes(
    agent_processes: list[AgentProcess],
    live_pids: set[int],
    *,
    now: float | None = None,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> None:
    """Classify each ``AgentProcess`` in place using multiple corroborating signals."""
    now = now if now is not None else time.time()
    duplicate_pids = _find_duplicates(agent_processes)

    for ap in agent_processes:
        proc = ap.process
        reasons: list[str] = []

        parent_gone = proc.ppid is not None and proc.ppid not in live_pids
        if parent_gone:
            reasons.append(f"parent process (pid {proc.ppid}) no longer exists")

        uptime = process_uptime_seconds(proc, now=now)
        idle_long = (
            proc.cpu_percent is not None
            and proc.cpu_percent == 0.0
            and uptime is not None
            and uptime >= thresholds.process_idle_seconds
        )
        if idle_long:
            hours = thresholds.process_idle_seconds / 3600
            reasons.append(f"idle at 0% CPU for over {hours:.0f}h")

        cwd_missing = proc.cwd is not None and not Path(proc.cwd).exists()
        if cwd_missing:
            reasons.append("working directory no longer exists")

        is_duplicate = proc.pid in duplicate_pids
        if is_duplicate:
            reasons.append("duplicate instance of an identical command is running")

        corroborating_signals = sum([cwd_missing, is_duplicate])
        signal_count = sum([parent_gone, idle_long, cwd_missing, is_duplicate])

        if signal_count == 0:
            classification = ProcessClassification.ACTIVE
        elif signal_count == 1:
            classification = ProcessClassification.LIKELY_ACTIVE
        elif signal_count == 2:
            classification = ProcessClassification.UNKNOWN
        elif ap.role == MAIN_ROLE:
            # Never escalate a main interactive agent process past LIKELY_ORPHANED,
            # regardless of signal count: a user may still be attached to it.
            classification = ProcessClassification.LIKELY_ORPHANED
        elif parent_gone and idle_long and corroborating_signals >= 1:
            classification = ProcessClassification.CONFIRMED_ORPHANED
        else:
            classification = ProcessClassification.LIKELY_ORPHANED

        ap.classification = classification
        ap.classification_reasons = reasons
        ap.estimated_ram_bytes = proc.rss_bytes


def apply_active_session_protection(
    agent_processes: list[AgentProcess],
    active_paths: list[Path],
) -> None:
    """Protect any process whose working directory sits under a currently-active path.

    Protection permanently overrides orphan classification: a protected
    process can never be auto-selected for termination by ``fix``.
    """
    resolved_active = [p.resolve() for p in active_paths if p.exists()]
    for ap in agent_processes:
        if ap.process.cwd is None:
            continue
        try:
            cwd = Path(ap.process.cwd).resolve()
        except OSError:
            continue
        for active in resolved_active:
            if cwd == active or active in cwd.parents:
                ap.mark_protected(f"working directory is inside active session {active}")
                break


def _evidence_lines(agent_processes: list[AgentProcess]) -> list[str]:
    return [
        f"pid {ap.process.pid}: {', '.join(ap.classification_reasons)}" for ap in agent_processes
    ]


def scan_processes(
    adapters: list[AgentAdapter],
    all_processes: list[ProcessInfo],
    *,
    now: float | None = None,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> tuple[list[AgentProcess], list[Finding]]:
    """Identify, classify, and protect agent-related processes across all adapters.

    Returns the full classified process list plus one aggregated finding per
    agent per orphan tier (confirmed vs likely), matching the density of the
    ``scan`` terminal report without one finding per process.
    """
    live_pids = {p.pid for p in all_processes}
    all_agent_processes: list[AgentProcess] = []
    findings: list[Finding] = []

    for adapter in adapters:
        agent_processes = adapter.identify_processes(all_processes)
        classify_processes(agent_processes, live_pids, now=now, thresholds=thresholds)

        active_paths: list[Path] = []
        now_ref = now if now is not None else time.time()
        for session_dir in adapter.discover_sessions():
            try:
                mtime = session_dir.stat().st_mtime
            except OSError:
                continue
            if now_ref - mtime <= thresholds.active_session_window_seconds:
                active_paths.append(session_dir)
        apply_active_session_protection(agent_processes, active_paths)

        all_agent_processes.extend(agent_processes)

        confirmed = [
            ap for ap in agent_processes
            if ap.classification == ProcessClassification.CONFIRMED_ORPHANED
        ]
        likely = [
            ap for ap in agent_processes
            if ap.classification == ProcessClassification.LIKELY_ORPHANED
        ]

        if confirmed:
            ram = sum(ap.estimated_ram_bytes or 0 for ap in confirmed)
            findings.append(
                Finding(
                    id=f"process.confirmed-orphan.{adapter.slug}",
                    category="processes",
                    severity=Severity.MEDIUM,
                    confidence=Confidence.HIGH,
                    title=f"{len(confirmed)} confirmed orphan process(es) for {adapter.name}",
                    description=(
                        "These processes have a dead parent, have been idle for an "
                        "extended period, and show at least one additional corroborating "
                        "signal (missing working directory or unexpected duplication)."
                    ),
                    agent=adapter.name,
                    evidence=_evidence_lines(confirmed),
                    recommendation="Safe to terminate via `agentjanitor fix`.",
                    fix_available=True,
                    estimated_bytes=None,
                    metadata={"estimated_ram_bytes": str(ram)},
                )
            )
        if likely:
            ram = sum(ap.estimated_ram_bytes or 0 for ap in likely)
            findings.append(
                Finding(
                    id=f"process.likely-orphan.{adapter.slug}",
                    category="processes",
                    severity=Severity.LOW,
                    confidence=Confidence.MEDIUM,
                    title=f"{len(likely)} possibly orphaned process(es) for {adapter.name}",
                    description=(
                        "Some, but not all, orphan signals were present. Manual review "
                        "required before terminating."
                    ),
                    agent=adapter.name,
                    evidence=_evidence_lines(likely),
                    recommendation="Review with `agentjanitor processes` before deciding.",
                    fix_available=False,
                    metadata={"estimated_ram_bytes": str(ram)},
                )
            )

    return all_agent_processes, findings
