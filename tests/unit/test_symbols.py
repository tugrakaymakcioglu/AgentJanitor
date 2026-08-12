"""Terminal symbol selection must never crash on a non-UTF8 console."""

from __future__ import annotations

import io

from rich.console import Console

from agentjanitor.core.scan import run_scan
from agentjanitor.reporting.terminal import render_agents
from agentjanitor.utils.symbols import ASCII_SYMBOLS, UNICODE_SYMBOLS, get_symbols, supports_unicode
from tests.fixtures.builder import build_fixture_environment
from tests.fixtures.fake_adapter import FakeAgentAdapter


def test_utf8_terminal_gets_unicode_symbols():
    utf8_file = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    console = Console(file=utf8_file, force_terminal=True, legacy_windows=False)
    assert supports_unicode(console) is True
    assert get_symbols(console) == UNICODE_SYMBOLS


def test_legacy_windows_console_gets_ascii_symbols():
    console = Console(file=io.StringIO(), force_terminal=True, legacy_windows=True)
    assert supports_unicode(console) is False
    assert get_symbols(console) == ASCII_SYMBOLS


def test_rendering_never_raises_on_ascii_only_console(tmp_path):
    """Regression test: Rich's legacy-Windows write path bypasses sys.stdout
    entirely, so this must be verified against Console.legacy_windows, not
    just against reconfigured stdout encoding."""
    env = build_fixture_environment(tmp_path)
    adapter = FakeAgentAdapter(env.root)
    result = run_scan([adapter], processes=[])

    console = Console(file=io.StringIO(), force_terminal=True, legacy_windows=True, width=80)
    render_agents(console, result)  # must not raise
    output = console.file.getvalue()
    assert ASCII_SYMBOLS.check in output or ASCII_SYMBOLS.cross in output
