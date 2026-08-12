"""Orphan classification against real OS processes, not synthetic ProcessInfo.

Spawns a real parent process which itself spawns a real "MCP-like" child,
then kills only the parent and verifies the classifier — running against
actual psutil data — recognizes the now-dead-parented, idle child as more
likely orphaned than it was while the parent was alive. No real coding
agent process is ever touched; everything here is a throwaway Python
subprocess this test starts and always cleans up.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from agentjanitor.adapters.base import AgentAdapter
from agentjanitor.core.config import Thresholds
from agentjanitor.models.agent import AgentInstallation, DetectionConfidence
from agentjanitor.models.mcp import MCPConfigSource
from agentjanitor.models.process import AgentProcess, ProcessClassification, ProcessInfo
from agentjanitor.platform.processes import list_processes, terminate_process
from agentjanitor.scanners.processes import classify_processes

_MARKER = "--agentjanitor-real-process-test"

_TINY_THRESHOLDS = Thresholds(process_idle_seconds=0.2)


class _MarkerAdapter(AgentAdapter):
    """Minimal adapter that only matches this test's marker string."""

    @property
    def name(self) -> str:
        return "Marker Test Agent"

    def detect(self) -> AgentInstallation:
        return AgentInstallation(agent=self.name, detected=True, confidence=DetectionConfidence.HIGH)

    def discover_config(self) -> list[Path]:
        return []

    def discover_sessions(self) -> list[Path]:
        return []

    def discover_cache(self) -> list[Path]:
        return []

    def discover_logs(self) -> list[Path]:
        return []

    def discover_temp_workspaces(self) -> list[Path]:
        return []

    def identify_processes(self, processes: list[ProcessInfo]) -> list[AgentProcess]:
        return [
            AgentProcess(process=p, agent=self.name, role="mcp-server")
            for p in processes
            if _MARKER in p.cmdline_str
        ]

    def discover_mcp_configs(self) -> list[MCPConfigSource]:
        return []


def test_real_child_becomes_more_orphan_like_after_parent_dies():
    # CREATE_BREAKAWAY_FROM_JOB / start_new_session detach the child from any
    # job object (Windows) or process group (POSIX) the parent belongs to —
    # otherwise terminating the parent can cascade-kill the child too under
    # some shells/CI runners, which would defeat the point of this test.
    if sys.platform.startswith("win"):
        child_extra_kwargs = "creationflags=subprocess.CREATE_BREAKAWAY_FROM_JOB"
    else:
        child_extra_kwargs = "start_new_session=True"
    parent_script = (
        "import subprocess, sys, time; "
        f"child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)', "
        f"'{_MARKER}'], {child_extra_kwargs}); "
        "print(child.pid, flush=True); "
        "time.sleep(20)"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", parent_script],
        stdout=subprocess.PIPE,
        text=True,
    )
    child_pid: int | None = None
    try:
        child_pid_line = parent.stdout.readline().strip()
        assert child_pid_line, "parent process did not report its child's pid"
        child_pid = int(child_pid_line)

        adapter = _MarkerAdapter()

        # While the parent is alive, the child must not look orphaned.
        all_processes = list_processes()
        agent_processes = adapter.identify_processes(all_processes)
        assert any(ap.process.pid == child_pid for ap in agent_processes)
        live_pids = {p.pid for p in all_processes}
        classify_processes(agent_processes, live_pids, thresholds=_TINY_THRESHOLDS)
        before = next(ap for ap in agent_processes if ap.process.pid == child_pid)
        assert before.classification in (
            ProcessClassification.ACTIVE,
            ProcessClassification.LIKELY_ACTIVE,
        )

        # Kill the parent only; the child (a separate OS process) survives.
        parent.terminate()
        parent.wait(timeout=5)
        time.sleep(0.5)  # clear the tiny idle threshold

        # Under load (e.g. running after the full suite), OS-level process
        # bookkeeping can lag briefly — poll rather than checking exactly once.
        all_processes: list = []
        agent_processes: list = []
        for _ in range(10):
            all_processes = list_processes()
            agent_processes = adapter.identify_processes(all_processes)
            if any(ap.process.pid == child_pid for ap in agent_processes):
                break
            time.sleep(0.5)
        assert any(ap.process.pid == child_pid for ap in agent_processes), (
            "child process should still be running after only its parent was killed"
        )
        live_pids = {p.pid for p in all_processes}
        classify_processes(agent_processes, live_pids, thresholds=_TINY_THRESHOLDS)
        after = next(ap for ap in agent_processes if ap.process.pid == child_pid)

        assert after.classification != ProcessClassification.ACTIVE
        assert any("parent process" in r for r in after.classification_reasons)
    finally:
        if child_pid is not None:
            terminate_process(child_pid)
        if parent.poll() is None:
            parent.terminate()
