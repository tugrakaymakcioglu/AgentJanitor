"""Disk usage analysis across sessions, cache, logs, and temp workspaces.

Every byte counted here is attributed to exactly one of: safe-reclaimable,
archive-candidate, or unknown/kept. Nothing is labeled "reclaimable" purely
because it's old — see the classification rules in ``scanners.sessions``.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from agentjanitor.adapters.base import AgentAdapter
from agentjanitor.core.config import DEFAULT_THRESHOLDS, Thresholds
from agentjanitor.models.finding import Confidence, Finding, Severity
from agentjanitor.models.storage import DiskCategory, SessionStatus, StorageBreakdown, StorageItem
from agentjanitor.scanners.sessions import classify_session_age, classify_temp_workspace_age
from agentjanitor.utils.format import human_bytes as _human_bytes
from agentjanitor.utils.safe_path import is_symlink_or_junction, iter_files_no_symlinks

_VERSION_DIR_PATTERN = re.compile(r"^v?\d+(?:\.\d+)*$")


def _dir_size_bytes(path: Path, thresholds: Thresholds) -> int:
    if is_symlink_or_junction(path):
        return 0
    total = 0
    for file_path in iter_files_no_symlinks(path)[: thresholds.max_scanned_files_per_dir * 10]:
        try:
            total += file_path.stat().st_size
        except OSError:
            continue
    return total


def _detect_old_cache_versions(cache_dir: Path) -> list[Path]:
    """Return version-looking subdirectories that are not the newest one."""
    if not cache_dir.is_dir():
        return []
    version_dirs = [
        d for d in cache_dir.iterdir() if d.is_dir() and _VERSION_DIR_PATTERN.match(d.name)
    ]
    if len(version_dirs) < 2:
        return []
    version_dirs.sort(key=lambda d: d.name)
    return version_dirs[:-1]


def scan_storage(
    adapter: AgentAdapter,
    *,
    now: float | None = None,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> tuple[StorageBreakdown, list[Finding]]:
    now = now if now is not None else time.time()
    breakdown = StorageBreakdown(agent=adapter.name)
    findings: list[Finding] = []

    for session_dir in adapter.discover_sessions():
        status = classify_session_age(session_dir, now=now, thresholds=thresholds)
        size = _dir_size_bytes(session_dir, thresholds)
        item = StorageItem(
            path=session_dir,
            category=DiskCategory.SESSIONS,
            agent=adapter.name,
            size_bytes=size,
            last_modified=session_dir.stat().st_mtime if session_dir.exists() else None,
            status=status,
            is_symlink=is_symlink_or_junction(session_dir),
        )
        breakdown.items.append(item)
        breakdown.total_bytes += size
        breakdown.by_category[DiskCategory.SESSIONS.value] = (
            breakdown.by_category.get(DiskCategory.SESSIONS.value, 0) + size
        )
        if status in (SessionStatus.ARCHIVE_CANDIDATE, SessionStatus.STALE):
            breakdown.archive_candidate_bytes += size
        elif status == SessionStatus.UNKNOWN:
            breakdown.unknown_bytes += size

    for cache_dir in adapter.discover_cache():
        old_version_paths = _detect_old_cache_versions(cache_dir)

        size = _dir_size_bytes(cache_dir, thresholds)
        old_versions_size = sum(_dir_size_bytes(p, thresholds) for p in old_version_paths)
        fresh_cache_size = size - old_versions_size

        breakdown.items.append(
            StorageItem(
                path=cache_dir,
                category=DiskCategory.CACHE,
                agent=adapter.name,
                size_bytes=fresh_cache_size,
                status=SessionStatus.UNKNOWN,
                is_symlink=is_symlink_or_junction(cache_dir),
            )
        )
        breakdown.total_bytes += size
        breakdown.by_category[DiskCategory.CACHE.value] = (
            breakdown.by_category.get(DiskCategory.CACHE.value, 0) + fresh_cache_size
        )
        breakdown.safe_reclaimable_bytes += fresh_cache_size

        for old_version in old_version_paths:
            ov_size = _dir_size_bytes(old_version, thresholds)
            breakdown.items.append(
                StorageItem(
                    path=old_version,
                    category=DiskCategory.OLD_VERSIONS,
                    agent=adapter.name,
                    size_bytes=ov_size,
                    status=SessionStatus.STALE,
                    is_symlink=is_symlink_or_junction(old_version),
                )
            )
            breakdown.by_category[DiskCategory.OLD_VERSIONS.value] = (
                breakdown.by_category.get(DiskCategory.OLD_VERSIONS.value, 0) + ov_size
            )
            breakdown.safe_reclaimable_bytes += ov_size

    for log_path in adapter.discover_logs():
        try:
            size = log_path.stat().st_size if log_path.is_file() else _dir_size_bytes(
                log_path, thresholds
            )
            mtime = log_path.stat().st_mtime
        except OSError:
            continue
        age_days = max(0.0, now - mtime) / 86400
        is_old = age_days >= thresholds.stale_temp_days
        breakdown.items.append(
            StorageItem(
                path=log_path,
                category=DiskCategory.LOGS,
                agent=adapter.name,
                size_bytes=size,
                last_modified=mtime,
                status=SessionStatus.STALE if is_old else SessionStatus.ACTIVE,
            )
        )
        breakdown.total_bytes += size
        breakdown.by_category[DiskCategory.LOGS.value] = (
            breakdown.by_category.get(DiskCategory.LOGS.value, 0) + size
        )
        if is_old:
            breakdown.safe_reclaimable_bytes += size

    for temp_dir in adapter.discover_temp_workspaces():
        status = classify_temp_workspace_age(temp_dir, now=now, thresholds=thresholds)
        size = _dir_size_bytes(temp_dir, thresholds)
        breakdown.items.append(
            StorageItem(
                path=temp_dir,
                category=DiskCategory.TEMP_WORKSPACE,
                agent=adapter.name,
                size_bytes=size,
                last_modified=temp_dir.stat().st_mtime if temp_dir.exists() else None,
                status=status,
            )
        )
        breakdown.total_bytes += size
        breakdown.by_category[DiskCategory.TEMP_WORKSPACE.value] = (
            breakdown.by_category.get(DiskCategory.TEMP_WORKSPACE.value, 0) + size
        )
        if status == SessionStatus.STALE:
            breakdown.safe_reclaimable_bytes += size

    if breakdown.safe_reclaimable_bytes > 0:
        reclaimable_str = _human_bytes(breakdown.safe_reclaimable_bytes)
        findings.append(
            Finding(
                id=f"storage.reclaimable.{adapter.slug}",
                category="storage",
                severity=Severity.LOW,
                confidence=Confidence.HIGH,
                title=f"{reclaimable_str} safely reclaimable for {adapter.name}",
                description="Regenerable caches, old cache versions, stale logs, and stale temp workspaces.",
                agent=adapter.name,
                recommendation="Run `agentjanitor fix` to reclaim automatically.",
                fix_available=True,
                estimated_bytes=breakdown.safe_reclaimable_bytes,
            )
        )
    if breakdown.archive_candidate_bytes > 0:
        archive_str = _human_bytes(breakdown.archive_candidate_bytes)
        findings.append(
            Finding(
                id=f"storage.archive-candidate.{adapter.slug}",
                category="storage",
                severity=Severity.INFO,
                confidence=Confidence.MEDIUM,
                title=f"{archive_str} of older session data for {adapter.name}",
                description="Sessions past the archive threshold. Compressed, not deleted, by default.",
                agent=adapter.name,
                recommendation="Review with `agentjanitor storage`; archive via `fix` if desired.",
                fix_available=True,
                estimated_bytes=breakdown.archive_candidate_bytes,
            )
        )

    return breakdown, findings
