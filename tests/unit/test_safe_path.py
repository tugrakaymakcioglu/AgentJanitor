"""Path safety: no destructive/measuring operation may escape its approved root."""

from __future__ import annotations

import os

import pytest

from agentjanitor.utils.safe_path import (
    UnsafePathError,
    assert_within_roots,
    is_within_root,
    iter_files_no_symlinks,
)


def test_path_within_root_is_accepted(tmp_path):
    root = tmp_path / "agent-root"
    target = root / "sessions" / "a"
    target.mkdir(parents=True)
    assert is_within_root(target, root)
    assert assert_within_roots(target, [root]) == target.resolve()


def test_path_outside_all_roots_is_rejected(tmp_path):
    root = tmp_path / "agent-root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    assert not is_within_root(outside, root)
    with pytest.raises(UnsafePathError):
        assert_within_roots(outside, [root])


def test_no_approved_roots_rejects_everything(tmp_path):
    with pytest.raises(UnsafePathError):
        assert_within_roots(tmp_path, [])


@pytest.mark.skipif(os.name == "nt", reason="requires developer-mode symlink privileges on Windows")
def test_symlink_escaping_root_is_rejected(tmp_path):
    root = tmp_path / "agent-root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    escape_link = root / "escape"
    escape_link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafePathError):
        assert_within_roots(escape_link, [root])


@pytest.mark.skipif(os.name == "nt", reason="requires developer-mode symlink privileges on Windows")
def test_iter_files_does_not_descend_into_symlinked_directories(tmp_path):
    root = tmp_path / "agent-root"
    (root / "real").mkdir(parents=True)
    (root / "real" / "file.txt").write_text("hello")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("should not be found")

    (root / "link").symlink_to(outside, target_is_directory=True)

    files = iter_files_no_symlinks(root)
    names = {f.name for f in files}
    assert "file.txt" in names
    assert "secret.txt" not in names
