"""Safe path validation shared by scanners and the cleanup engine.

Every destructive or size-measuring operation in AgentJanitor must go
through this module rather than touching ``Path`` directly, so that
"never delete outside an approved root" and "never follow a symlink out
of the scan tree" are enforced in exactly one place.
"""

from __future__ import annotations

from pathlib import Path


class UnsafePathError(Exception):
    """Raised when a path is outside its approved root or escapes via a symlink."""


def resolve_strict(path: Path) -> Path:
    """Resolve a path fully, following symlinks, without requiring existence."""
    return path.resolve()


def is_within_root(path: Path, root: Path) -> bool:
    """True if ``path`` resolves to somewhere inside ``root``.

    Both sides are fully resolved (symlinks included) before comparison,
    so a symlink inside ``root`` that points outside it is correctly
    rejected rather than appearing to be "within root" by name alone.
    """
    try:
        resolved_path = resolve_strict(path)
        resolved_root = resolve_strict(root)
    except OSError:
        return False
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def assert_within_roots(path: Path, roots: list[Path]) -> Path:
    """Validate ``path`` is inside at least one approved root.

    Returns the resolved path on success. Raises ``UnsafePathError`` if the
    path escapes every approved root, including via a symlink.
    """
    if not roots:
        raise UnsafePathError(f"no approved roots configured; refusing to touch {path}")
    for root in roots:
        if is_within_root(path, root):
            return resolve_strict(path)
    raise UnsafePathError(
        f"path {path} is outside all approved roots ({', '.join(str(r) for r in roots)})"
    )


def is_symlink_or_junction(path: Path) -> bool:
    """True for symlinks and, on Windows, NTFS junctions/reparse points."""
    try:
        if path.is_symlink():
            return True
        # Windows junctions report is_symlink() == False on some Python/OS
        # combinations; a reparse point stat flag catches those too.
        stat_result = path.lstat()
        return bool(getattr(stat_result, "st_reparse_tag", 0))
    except OSError:
        return False


def iter_files_no_symlinks(root: Path) -> list[Path]:
    """Walk ``root`` recursively, never descending into symlinked directories.

    Used for size accounting and content scanning so a symlink planted
    inside an agent directory can't cause AgentJanitor to read or measure
    files far outside the intended scan scope.
    """
    files: list[Path] = []
    if not root.exists() or is_symlink_or_junction(root):
        return files
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if is_symlink_or_junction(entry):
                continue
            try:
                if entry.is_dir():
                    stack.append(entry)
                elif entry.is_file():
                    files.append(entry)
            except OSError:
                continue
    return files
