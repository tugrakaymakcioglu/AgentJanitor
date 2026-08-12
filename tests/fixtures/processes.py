"""Synthetic ``ProcessInfo`` builders for process-classification unit tests."""

from __future__ import annotations

from agentjanitor.models.process import ProcessInfo
from tests.fixtures.fake_adapter import FAKE_MARKER


def make_process(
    pid: int,
    ppid: int | None,
    *,
    role: str = "main",
    create_time: float = 0.0,
    status: str = "running",
    cpu_percent: float = 0.0,
    rss_bytes: int = 50 * 1024 * 1024,
    cwd: str | None = None,
    extra_args: list[str] | None = None,
) -> ProcessInfo:
    cmdline = ["python", FAKE_MARKER]
    if role == "mcp-server":
        cmdline.append("--role=mcp")
    cmdline += extra_args or []
    return ProcessInfo(
        pid=pid,
        ppid=ppid,
        name="python",
        exe="/usr/bin/python",
        cmdline=cmdline,
        create_time=create_time,
        status=status,
        cpu_percent=cpu_percent,
        rss_bytes=rss_bytes,
        username="tester",
        cwd=cwd,
        parent_chain=[ppid] if ppid else [],
    )


def make_unrelated_process(pid: int, ppid: int | None = 1) -> ProcessInfo:
    return ProcessInfo(
        pid=pid,
        ppid=ppid,
        name="chrome",
        exe="/usr/bin/chrome",
        cmdline=["chrome", "--type=renderer"],
        create_time=0.0,
        status="running",
        cpu_percent=0.0,
        rss_bytes=200 * 1024 * 1024,
        username="tester",
        parent_chain=[ppid] if ppid else [],
    )
