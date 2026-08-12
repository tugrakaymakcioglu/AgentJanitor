"""Cleanup plan execution.

``dry_run=True`` must perform zero mutations — every branch below checks
it before touching a process or the filesystem. Every performed action is
recorded so ``agentjanitor undo`` has something to work from.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from pydantic import BaseModel, Field

from agentjanitor.backup.manager import BackupManager
from agentjanitor.models.cleanup import Backup, CleanupAction, CleanupActionType
from agentjanitor.platform.processes import terminate_process


class ActionResult(BaseModel):
    action_id: str
    performed: bool
    dry_run: bool
    detail: str = ""
    error: str | None = None


class ExecutionReport(BaseModel):
    dry_run: bool
    results: list[ActionResult] = Field(default_factory=list)
    backup: Backup | None = None

    @property
    def all_succeeded(self) -> bool:
        return all(r.error is None for r in self.results)


_NEEDS_BACKUP = {
    CleanupActionType.REMOVE_TEMP_WORKSPACE,
    CleanupActionType.DELETE_LOG,
}
_NEEDS_ARCHIVE = {CleanupActionType.ARCHIVE_SESSIONS}


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def execute_action(
    action: CleanupAction,
    *,
    dry_run: bool,
    backup: Backup | None,
    backup_manager: BackupManager | None,
) -> ActionResult:
    if dry_run:
        return ActionResult(
            action_id=action.id,
            performed=False,
            dry_run=True,
            detail=f"would perform: {action.description}",
        )

    try:
        if action.action_type == CleanupActionType.TERMINATE_PROCESS:
            failures = [pid for pid in action.affected_pids if not terminate_process(pid)]
            if failures:
                return ActionResult(
                    action_id=action.id,
                    performed=True,
                    dry_run=False,
                    detail=f"terminated {len(action.affected_pids) - len(failures)} process(es)",
                    error=f"failed to terminate pid(s): {failures}",
                )
            return ActionResult(
                action_id=action.id,
                performed=True,
                dry_run=False,
                detail=f"terminated {len(action.affected_pids)} process(es)",
            )

        if action.action_type == CleanupActionType.DELETE_CACHE:
            for path in action.affected_paths:
                _remove_path(path)
            return ActionResult(
                action_id=action.id,
                performed=True,
                dry_run=False,
                detail=f"removed {len(action.affected_paths)} cache path(s)",
            )

        if action.action_type in _NEEDS_BACKUP:
            if backup is None or backup_manager is None:
                raise RuntimeError("backup required for this action but none was provided")
            for path in action.affected_paths:
                backup_manager.backup_path(backup, path, action.id)
                _remove_path(path)
            return ActionResult(
                action_id=action.id,
                performed=True,
                dry_run=False,
                detail=f"backed up and removed {len(action.affected_paths)} path(s)",
            )

        if action.action_type in _NEEDS_ARCHIVE:
            if backup is None or backup_manager is None:
                raise RuntimeError("backup required for this action but none was provided")
            for path in action.affected_paths:
                backup_manager.archive_path(backup, path, action.id)
                _remove_path(path)
            return ActionResult(
                action_id=action.id,
                performed=True,
                dry_run=False,
                detail=f"archived and removed {len(action.affected_paths)} session path(s)",
            )

        raise RuntimeError(f"unknown action type: {action.action_type}")

    except OSError as exc:
        return ActionResult(action_id=action.id, performed=False, dry_run=False, error=str(exc))


def execute_plan(
    actions: list[CleanupAction],
    *,
    dry_run: bool,
    backup_manager: BackupManager | None = None,
) -> ExecutionReport:
    """Run a list of already-selected actions.

    A backup is created lazily, only if at least one action actually needs
    one — a terminate-only or cache-only run never touches
    ``~/.agentjanitor/backups`` at all.
    """
    backup_manager = backup_manager or BackupManager()
    needs_backup = any(a.action_type in (_NEEDS_BACKUP | _NEEDS_ARCHIVE) for a in actions)

    backup: Backup | None = None
    if needs_backup and not dry_run:
        backup = backup_manager.create_backup()

    results = [
        execute_action(action, dry_run=dry_run, backup=backup, backup_manager=backup_manager)
        for action in actions
    ]

    if backup is not None:
        backup.action_ids = [a.id for a in actions]
        backup_manager.save_manifest(backup)

    return ExecutionReport(dry_run=dry_run, results=results, backup=backup)
