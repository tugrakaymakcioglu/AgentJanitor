"""ASCII-safe fallback glyphs for terminals that can't render Unicode.

Legacy Windows consoles (plain cmd.exe/PowerShell without UTF-8 code page
or virtual-terminal processing) route Rich's output through a code path
that encodes with the console's active code page rather than UTF-8. On a
non-UTF8 code page, ✓/⚠/✗/─ either raise ``UnicodeEncodeError`` or get
replaced with literal ``?`` characters. Falling back to plain ASCII there
keeps the output readable instead of degrading it silently.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console


@dataclass(frozen=True)
class Symbols:
    check: str
    cross: str
    warn: str
    rule_char: str


UNICODE_SYMBOLS = Symbols(check="✓", cross="✗", warn="⚠", rule_char="─")
ASCII_SYMBOLS = Symbols(check="+", cross="x", warn="!", rule_char="-")


def supports_unicode(console: Console) -> bool:
    if console.legacy_windows:
        return False
    encoding = (getattr(console.file, "encoding", None) or "").lower()
    return "utf" in encoding


def get_symbols(console: Console) -> Symbols:
    return UNICODE_SYMBOLS if supports_unicode(console) else ASCII_SYMBOLS
