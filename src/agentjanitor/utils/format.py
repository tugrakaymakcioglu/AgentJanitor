"""Shared human-readable formatting helpers."""

from __future__ import annotations


def human_bytes(n: int | float) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
