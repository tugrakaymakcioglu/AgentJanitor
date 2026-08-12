"""Cleanup plan generation.

Turns classified processes and storage breakdowns into explicit, typed
``CleanupAction`` objects. Anything that doesn't meet the conservative bar
for a given action type is left out entirely rather than downgraded —
uncertain items belong in ``agentjanitor processes`` / ``storage`` for
manual review, not in a cleanup plan at any risk level.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from agentjanitor.models.cleanup import (
    CleanupAction,
    CleanupActionType,
    CleanupPlan,
    ReversibilityLevel,
    RiskLevel,
)
from agentjanitor.models.process import AgentProcess, ProcessClassification
from agentjanitor.models.storage import DiskCategory, SessionStatus, StorageBreakdown
from agentjanitor.utils.safe_path import UnsafePathError, assert_within_roots


def _safe_paths(paths: list[Path], roots: list[Path]) -> tuple[list[Path], list[str]]:
    """Validate paths against approved roots, dropping (and explaining) any that fail."""
    valid: list[Path] = []
    warnings: list[str] = []
    for path in paths:
        try:
            valid.append(assert_within_roots(path, roots))
        except UnsafePathError as exc:
            warnings.append(str(exc))
    return valid, warnings


def build_cleanup_plan(
    agent_processes: list[AgentProcess],
    storage_breakdowns: list[StorageBreakdown],
    approved_roots: dict[str, list[Path]],
) -> CleanupPlan:
    plan = CleanupPlan()

    by_agent_processes: dict[str, list[AgentProcess]] = defaultdict(list)
    for ap in agent_processes:
        by_agent_processes[ap.agent].append(ap)

    for agent, procs in by_agent_processes.items():
        confirmed = [
            p for p in procs
            if p.classification == ProcessClassification.CONFIRMED_ORPHANED and not p.protected
        ]
        if confirmed:
            plan.actions.append(
                CleanupAction(
                    id=f"terminate-orphans.{agent}",
                    action_type=CleanupActionType.TERMINATE_PROCESS,
                    description=f"Terminate {len(confirmed)} confirmed orphan process(es) for {agent}",
                    risk_level=RiskLevel.SAFE,
                    reversible=ReversibilityLevel.IRREVERSIBLE,
                    estimated_ram_bytes=sum(p.estimated_ram_bytes or 0 for p in confirmed),
                    affected_pids=[p.process.pid for p in confirmed],
                    reason="Dead parent, sustained idleness, and a corroborating structural signal.",
                    agent=agent,
                )
            )

        likely = [
            p for p in procs
            if p.classification == ProcessClassification.LIKELY_ORPHANED and not p.protected
        ]
        if likely:
            plan.excluded_actions.append(
                CleanupAction(
                    id=f"terminate-likely-orphans.{agent}",
                    action_type=CleanupActionType.TERMINATE_PROCESS,
                    description=f"Terminate {len(likely)} possibly orphaned process(es) for {agent}",
                    risk_level=RiskLevel.MEDIUM,
                    reversible=ReversibilityLevel.IRREVERSIBLE,
                    estimated_ram_bytes=sum(p.estimated_ram_bytes or 0 for p in likely),
                    affected_pids=[p.process.pid for p in likely],
                    reason="Some, but not all, orphan signals present. Requires manual selection.",
                    agent=agent,
                )
            )

        protected = [p for p in procs if p.protected]
        for p in protected:
            plan.protected_notes.append(
                f"pid {p.process.pid} ({agent}) protected: {p.protected_reason}"
            )

    for breakdown in storage_breakdowns:
        agent = breakdown.agent
        roots = approved_roots.get(agent, [])

        cache_paths = [
            item.path for item in breakdown.items
            if item.category in (DiskCategory.CACHE, DiskCategory.OLD_VERSIONS) and item.size_bytes > 0
        ]
        if cache_paths:
            valid_paths, warnings = _safe_paths(cache_paths, roots)
            plan.protected_notes.extend(warnings)
            if valid_paths:
                size = sum(
                    item.size_bytes for item in breakdown.items
                    if item.path in valid_paths
                )
                plan.actions.append(
                    CleanupAction(
                        id=f"delete-cache.{agent}",
                        action_type=CleanupActionType.DELETE_CACHE,
                        description=f"Remove obsolete/regenerable cache data for {agent}",
                        risk_level=RiskLevel.SAFE,
                        reversible=ReversibilityLevel.IRREVERSIBLE,
                        estimated_bytes=size,
                        affected_paths=valid_paths,
                        reason="Cache content is regenerable on next use; not backed up.",
                        agent=agent,
                    )
                )

        temp_paths = [
            item.path for item in breakdown.items
            if item.category == DiskCategory.TEMP_WORKSPACE and item.status == SessionStatus.STALE
        ]
        if temp_paths:
            valid_paths, warnings = _safe_paths(temp_paths, roots)
            plan.protected_notes.extend(warnings)
            if valid_paths:
                size = sum(
                    item.size_bytes for item in breakdown.items
                    if item.path in valid_paths
                )
                plan.actions.append(
                    CleanupAction(
                        id=f"remove-temp.{agent}",
                        action_type=CleanupActionType.REMOVE_TEMP_WORKSPACE,
                        description=f"Remove stale temporary workspaces for {agent}",
                        risk_level=RiskLevel.SAFE,
                        reversible=ReversibilityLevel.REVERSIBLE,
                        estimated_bytes=size,
                        affected_paths=valid_paths,
                        reason="Untouched for longer than the stale-temp threshold.",
                        agent=agent,
                    )
                )

        log_paths = [
            item.path for item in breakdown.items
            if item.category == DiskCategory.LOGS and item.status == SessionStatus.STALE
        ]
        if log_paths:
            valid_paths, warnings = _safe_paths(log_paths, roots)
            plan.protected_notes.extend(warnings)
            if valid_paths:
                size = sum(
                    item.size_bytes for item in breakdown.items
                    if item.path in valid_paths
                )
                plan.actions.append(
                    CleanupAction(
                        id=f"delete-logs.{agent}",
                        action_type=CleanupActionType.DELETE_LOG,
                        description=f"Remove stale log files for {agent}",
                        risk_level=RiskLevel.SAFE,
                        reversible=ReversibilityLevel.REVERSIBLE,
                        estimated_bytes=size,
                        affected_paths=valid_paths,
                        reason="Old logs past the stale threshold; backed up before removal.",
                        agent=agent,
                    )
                )

        session_paths = [
            item.path for item in breakdown.items
            if item.category == DiskCategory.SESSIONS
            and item.status in (SessionStatus.ARCHIVE_CANDIDATE, SessionStatus.STALE)
        ]
        if session_paths:
            valid_paths, warnings = _safe_paths(session_paths, roots)
            plan.protected_notes.extend(warnings)
            if valid_paths:
                size = sum(
                    item.size_bytes for item in breakdown.items
                    if item.path in valid_paths
                )
                plan.actions.append(
                    CleanupAction(
                        id=f"archive-sessions.{agent}",
                        action_type=CleanupActionType.ARCHIVE_SESSIONS,
                        description=f"Archive old session data for {agent}",
                        risk_level=RiskLevel.SAFE,
                        reversible=ReversibilityLevel.REVERSIBLE,
                        estimated_bytes=size,
                        affected_paths=valid_paths,
                        reason="Past the archive threshold; compressed in place, never deleted.",
                        agent=agent,
                    )
                )

    return plan


def select_safe_actions(plan: CleanupPlan) -> list[CleanupAction]:
    """The subset of a plan's actions that a normal `fix` run may auto-select."""
    return [a for a in plan.actions if a.risk_level == RiskLevel.SAFE]
