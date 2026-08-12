"""Backup manifest creation, session archiving, and restore."""

from __future__ import annotations

from agentjanitor.backup.manager import BackupManager


def test_backup_and_restore_file(tmp_path):
    manager = BackupManager(base_dir=tmp_path / "backups")
    source = tmp_path / "log.txt"
    source.write_text("hello")

    backup = manager.create_backup()
    manager.backup_path(backup, source, action_id="a1")
    manager.save_manifest(backup)

    source.unlink()
    assert not source.exists()

    reloaded = manager.load_manifest(backup.manifest_path.parent)
    notes = manager.restore(reloaded)

    assert source.exists()
    assert source.read_text() == "hello"
    assert any("restored" in n for n in notes)
    assert reloaded.restored is True


def test_archive_and_restore_directory(tmp_path):
    manager = BackupManager(base_dir=tmp_path / "backups")
    session_dir = tmp_path / "session-1"
    session_dir.mkdir()
    (session_dir / "transcript.jsonl").write_text('{"a": 1}\n')

    backup = manager.create_backup()
    manager.archive_path(backup, session_dir, action_id="a1")
    manager.save_manifest(backup)

    import shutil

    shutil.rmtree(session_dir)
    assert not session_dir.exists()

    manager.restore(backup)
    assert session_dir.exists()
    assert (session_dir / "transcript.jsonl").read_text() == '{"a": 1}\n'


def test_restore_skips_paths_that_already_exist(tmp_path):
    manager = BackupManager(base_dir=tmp_path / "backups")
    source = tmp_path / "log.txt"
    source.write_text("original")

    backup = manager.create_backup()
    manager.backup_path(backup, source, action_id="a1")
    manager.save_manifest(backup)

    # Original was never deleted; restoring must not silently overwrite it.
    notes = manager.restore(backup)
    assert source.read_text() == "original"
    assert any("skipped" in n for n in notes)


def test_list_backups_returns_saved_manifests(tmp_path):
    manager = BackupManager(base_dir=tmp_path / "backups")
    source = tmp_path / "log.txt"
    source.write_text("hi")
    backup = manager.create_backup()
    manager.backup_path(backup, source, action_id="a1")
    manager.save_manifest(backup)

    backups = manager.list_backups()
    assert len(backups) == 1
    assert manager.latest_backup().backup_id == backup.backup_id
