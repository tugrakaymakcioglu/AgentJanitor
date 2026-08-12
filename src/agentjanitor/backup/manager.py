"""Backup creation, manifest persistence, and restore.

Strategy differs by what's being backed up: small files/directories (temp
workspaces, logs) are copied directly; sessions are compressed to a single
archive so a multi-GB session tree isn't duplicated byte-for-byte before
being reclaimed. Regenerable cache content is intentionally never backed
up — see the callers in ``cleanup.executor``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from agentjanitor.models.cleanup import Backup, BackupEntry

DEFAULT_BACKUP_ROOT = Path.home() / ".agentjanitor" / "backups"


class BackupError(Exception):
    pass


def _safe_name(path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:10]
    return f"{path.name}-{digest}"


class BackupManager:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or DEFAULT_BACKUP_ROOT

    def create_backup(self) -> Backup:
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%S")
        backup_dir = self.base_dir / stamp
        (backup_dir / "files").mkdir(parents=True, exist_ok=True)
        return Backup(
            backup_id=stamp,
            created_at=datetime.now(UTC).isoformat(),
            manifest_path=backup_dir / "manifest.json",
        )

    def _files_dir(self, backup: Backup) -> Path:
        return backup.manifest_path.parent / "files"

    def backup_path(self, backup: Backup, original: Path, action_id: str) -> BackupEntry:
        """Copy a file or directory into the backup verbatim."""
        dest = self._files_dir(backup) / _safe_name(original)
        if original.is_dir():
            shutil.copytree(original, dest, symlinks=False)
            was_directory = True
        else:
            shutil.copy2(original, dest)
            was_directory = False
        entry = BackupEntry(
            original_path=original,
            backup_path=dest,
            was_directory=was_directory,
            action_id=action_id,
        )
        backup.entries.append(entry)
        return entry

    def archive_path(self, backup: Backup, original: Path, action_id: str) -> BackupEntry:
        """Compress a directory into a single archive inside the backup.

        Used for session data, which can be large: this avoids holding two
        full copies of a multi-GB tree at once.
        """
        archive_base = self._files_dir(backup) / _safe_name(original)
        archive_path_str = shutil.make_archive(
            str(archive_base), "zip", root_dir=str(original.parent), base_dir=original.name
        )
        entry = BackupEntry(
            original_path=original,
            backup_path=Path(archive_path_str),
            was_directory=True,
            action_id=action_id,
        )
        backup.entries.append(entry)
        return entry

    def save_manifest(self, backup: Backup) -> None:
        backup.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        backup.manifest_path.write_text(backup.model_dump_json(indent=2), encoding="utf-8")

    def load_manifest(self, backup_dir: Path) -> Backup:
        manifest_path = backup_dir / "manifest.json"
        if not manifest_path.exists():
            raise BackupError(f"no manifest found at {manifest_path}")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return Backup.model_validate(data)

    def list_backups(self) -> list[Backup]:
        if not self.base_dir.exists():
            return []
        backups = []
        for entry in sorted(self.base_dir.iterdir()):
            if entry.is_dir() and (entry / "manifest.json").exists():
                try:
                    backups.append(self.load_manifest(entry))
                except BackupError:
                    continue
        return backups

    def latest_backup(self) -> Backup | None:
        backups = self.list_backups()
        return backups[-1] if backups else None

    def restore(self, backup: Backup) -> list[str]:
        """Restore every entry in a backup. Returns human-readable notes."""
        notes: list[str] = []
        for entry in backup.entries:
            try:
                if entry.original_path.exists():
                    notes.append(f"skipped {entry.original_path}: already exists")
                    continue
                if entry.backup_path.suffix == ".zip":
                    entry.original_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.unpack_archive(str(entry.backup_path), str(entry.original_path.parent))
                elif entry.was_directory:
                    shutil.copytree(entry.backup_path, entry.original_path)
                else:
                    entry.original_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(entry.backup_path, entry.original_path)
                notes.append(f"restored {entry.original_path}")
            except OSError as exc:
                notes.append(f"failed to restore {entry.original_path}: {exc}")
        backup.restored = True
        self.save_manifest(backup)
        return notes
