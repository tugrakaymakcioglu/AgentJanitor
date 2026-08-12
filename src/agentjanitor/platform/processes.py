"""Cross-platform process enumeration and termination via psutil.

psutil already abstracts most OS differences; this module's job is to
normalize the data into ``ProcessInfo`` and to fail soft (skip, don't
crash) when a process disappears mid-read or access is denied, which
happens routinely on Windows for other users' processes and on macOS for
sandboxed/system processes.
"""

from __future__ import annotations

import time

import psutil

from agentjanitor.models.process import ProcessInfo


def _parent_chain_from_map(pid: int, ppid_by_pid: dict[int, int | None], max_depth: int = 16) -> list[int]:
    """Walk a pre-built pid->ppid map instead of re-querying the OS per hop.

    Querying ``psutil.Process.parent()`` repeatedly for every process (up to
    ``max_depth`` hops each) is what made process enumeration slow enough to
    matter (measured ~45s for ~400 processes on Windows) — most of that cost
    was redundant syscalls this map avoids entirely.
    """
    chain: list[int] = []
    current = ppid_by_pid.get(pid)
    for _ in range(max_depth):
        if current is None or current not in ppid_by_pid:
            break
        chain.append(current)
        current = ppid_by_pid.get(current)
    return chain


def _to_process_info(proc: psutil.Process) -> ProcessInfo | None:
    try:
        with proc.oneshot():
            pid = proc.pid
            try:
                ppid = proc.ppid()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                ppid = None
            try:
                name = proc.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                name = "<unknown>"
            try:
                exe = proc.exe()
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                exe = None
            try:
                cmdline = proc.cmdline()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                cmdline = []
            try:
                create_time = proc.create_time()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                create_time = None
            try:
                status = proc.status()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                status = None
            try:
                cpu_percent = proc.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                cpu_percent = None
            try:
                rss_bytes = proc.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                rss_bytes = None
            try:
                username = proc.username()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                username = None
            try:
                cwd = proc.cwd()
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                cwd = None
    except psutil.NoSuchProcess:
        return None

    return ProcessInfo(
        pid=pid,
        ppid=ppid,
        name=name,
        exe=exe,
        cmdline=cmdline,
        create_time=create_time,
        status=status,
        cpu_percent=cpu_percent,
        rss_bytes=rss_bytes,
        username=username,
        cwd=cwd,
        parent_chain=[],
    )


def list_processes() -> list[ProcessInfo]:
    """Enumerate all visible processes, skipping ones we can't read.

    Parent chains are filled in afterward from an in-memory pid->ppid map
    built from this same pass, rather than re-querying the OS per process —
    see ``_parent_chain_from_map`` for why that matters.
    """
    results: list[ProcessInfo] = []
    for proc in psutil.process_iter():
        info = _to_process_info(proc)
        if info is not None:
            results.append(info)

    ppid_by_pid = {info.pid: info.ppid for info in results}
    for info in results:
        info.parent_chain = _parent_chain_from_map(info.pid, ppid_by_pid)

    return results


def pid_exists(pid: int) -> bool:
    return psutil.pid_exists(pid)


def terminate_process(pid: int, timeout_seconds: float = 5.0) -> bool:
    """Terminate a process gracefully, escalating to kill on timeout.

    Returns True if the process is confirmed gone afterward. Never raises
    on a process that already exited underneath us.
    """
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return True

    try:
        proc.terminate()
        proc.wait(timeout=timeout_seconds)
        return True
    except psutil.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(timeout=timeout_seconds)
            return True
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            return not psutil.pid_exists(pid)
    except psutil.NoSuchProcess:
        return True
    except psutil.AccessDenied:
        return False


def process_uptime_seconds(process: ProcessInfo, now: float | None = None) -> float | None:
    if process.create_time is None:
        return None
    reference = now if now is not None else time.time()
    return max(0.0, reference - process.create_time)
