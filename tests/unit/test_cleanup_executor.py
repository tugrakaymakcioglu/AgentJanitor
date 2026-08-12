"""Cleanup execution: dry-run performs zero mutations; real runs back up first."""

from __future__ import annotations

from agentjanitor.backup.manager import BackupManager
from agentjanitor.cleanup.executor import execute_plan
from agentjanitor.models.cleanup import (
    CleanupAction,
    CleanupActionType,
    ReversibilityLevel,
    RiskLevel,
)


def _remove_temp_action(path) -> CleanupAction:
    return CleanupAction(
        id="remove-temp.test",
        action_type=CleanupActionType.REMOVE_TEMP_WORKSPACE,
        description="Remove stale temporary workspace",
        risk_level=RiskLevel.SAFE,
        reversible=ReversibilityLevel.REVERSIBLE,
        estimated_bytes=path.stat().st_size if path.is_file() else 0,
        affected_paths=[path],
    )


def _delete_cache_action(path) -> CleanupAction:
    return CleanupAction(
        id="delete-cache.test",
        action_type=CleanupActionType.DELETE_CACHE,
        description="Remove cache",
        risk_level=RiskLevel.SAFE,
        reversible=ReversibilityLevel.IRREVERSIBLE,
        affected_paths=[path],
    )


def test_dry_run_performs_zero_mutations(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "scratch.txt").write_text("data")
    action = _remove_temp_action(workspace)

    report = execute_plan([action], dry_run=True)

    assert workspace.exists()
    assert (workspace / "scratch.txt").exists()
    assert report.dry_run is True
    assert report.results[0].performed is False
    assert report.backup is None


def test_real_run_backs_up_before_removing(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "scratch.txt").write_text("data")
    action = _remove_temp_action(workspace)

    manager = BackupManager(base_dir=tmp_path / "backups")
    report = execute_plan([action], dry_run=False, backup_manager=manager)

    assert not workspace.exists()
    assert report.backup is not None
    assert len(report.backup.entries) == 1
    assert report.results[0].performed is True
    assert report.results[0].error is None


def test_cache_deletion_is_not_backed_up(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "blob.bin").write_bytes(b"x" * 1024)
    action = _delete_cache_action(cache_dir)

    manager = BackupManager(base_dir=tmp_path / "backups")
    report = execute_plan([action], dry_run=False, backup_manager=manager)

    assert not cache_dir.exists()
    assert report.backup is None  # cache is regenerable; no backup needed


def test_undo_restores_removed_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "scratch.txt").write_text("important-ish data")
    action = _remove_temp_action(workspace)

    manager = BackupManager(base_dir=tmp_path / "backups")
    report = execute_plan([action], dry_run=False, backup_manager=manager)
    assert not workspace.exists()

    notes = manager.restore(report.backup)
    assert workspace.exists()
    assert (workspace / "scratch.txt").read_text() == "important-ish data"
    assert any("restored" in n for n in notes)


def test_terminating_an_already_gone_pid_does_not_raise():
    """A pid that no longer exists counts as already cleaned up, not a failure."""
    action = CleanupAction(
        id="terminate.missing",
        action_type=CleanupActionType.TERMINATE_PROCESS,
        description="Terminate a pid that does not exist",
        risk_level=RiskLevel.SAFE,
        reversible=ReversibilityLevel.IRREVERSIBLE,
        affected_pids=[999_999_999],
    )
    report = execute_plan([action], dry_run=False)
    assert report.results[0].error is None
    assert report.results[0].performed is True
