"""Process orphan classification must never confirm-orphan from a single signal."""

from __future__ import annotations

from agentjanitor.models.process import AgentProcess, ProcessClassification
from agentjanitor.scanners.processes import apply_active_session_protection, classify_processes
from tests.fixtures.processes import make_process

NOW = 1_000_000.0


def _agent_process(proc, role="main") -> AgentProcess:
    return AgentProcess(process=proc, agent="Fake Agent", role=role)


def test_healthy_process_is_active():
    proc = make_process(pid=100, ppid=1, create_time=NOW - 10, cpu_percent=5.0)
    ap = _agent_process(proc)
    classify_processes([ap], live_pids={1, 100}, now=NOW)
    assert ap.classification == ProcessClassification.ACTIVE
    assert ap.classification_reasons == []


def test_dead_parent_alone_is_not_orphaned():
    """A dead parent by itself must never escalate past LIKELY_ACTIVE."""
    proc = make_process(pid=101, ppid=999, create_time=NOW - 10, cpu_percent=5.0)
    ap = _agent_process(proc, role="mcp-server")
    classify_processes([ap], live_pids={101}, now=NOW)
    assert ap.classification == ProcessClassification.LIKELY_ACTIVE
    assert ap.classification not in (
        ProcessClassification.LIKELY_ORPHANED,
        ProcessClassification.CONFIRMED_ORPHANED,
    )


def test_idle_zero_cpu_alone_is_not_orphaned():
    """Long idle + 0% CPU alone (parent alive) must never confirm-orphan."""
    proc = make_process(
        pid=102, ppid=1, create_time=NOW - 100_000, cpu_percent=0.0
    )
    ap = _agent_process(proc, role="mcp-server")
    classify_processes([ap], live_pids={1, 102}, now=NOW)
    assert ap.classification != ProcessClassification.CONFIRMED_ORPHANED


def test_mcp_role_alone_is_not_orphaned():
    """Being an MCP-role process is not itself a signal."""
    proc = make_process(pid=103, ppid=1, create_time=NOW - 10, cpu_percent=10.0)
    ap = _agent_process(proc, role="mcp-server")
    classify_processes([ap], live_pids={1, 103}, now=NOW)
    assert ap.classification == ProcessClassification.ACTIVE


def test_confirmed_orphan_requires_multiple_corroborating_signals():
    """Dead parent + long idle + missing cwd => confirmed, and only for non-main roles."""
    proc = make_process(
        pid=104,
        ppid=999,
        create_time=NOW - 100_000,
        cpu_percent=0.0,
        cwd="/definitely/does/not/exist/agentjanitor-test",
    )
    ap = _agent_process(proc, role="mcp-server")
    classify_processes([ap], live_pids={104}, now=NOW)
    assert ap.classification == ProcessClassification.CONFIRMED_ORPHANED
    assert len(ap.classification_reasons) >= 3


def test_main_role_never_confirmed_orphan_even_with_all_signals():
    proc = make_process(
        pid=105,
        ppid=999,
        create_time=NOW - 100_000,
        cpu_percent=0.0,
        cwd="/definitely/does/not/exist/agentjanitor-test",
    )
    ap = _agent_process(proc, role="main")
    classify_processes([ap], live_pids={105}, now=NOW)
    assert ap.classification != ProcessClassification.CONFIRMED_ORPHANED
    assert ap.classification == ProcessClassification.LIKELY_ORPHANED


def test_duplicate_instances_contribute_a_signal():
    proc_a = make_process(pid=106, ppid=1, create_time=NOW - 10, cpu_percent=1.0, extra_args=["--x"])
    proc_b = make_process(pid=107, ppid=1, create_time=NOW - 10, cpu_percent=1.0, extra_args=["--x"])
    ap_a = _agent_process(proc_a, role="mcp-server")
    ap_b = _agent_process(proc_b, role="mcp-server")
    classify_processes([ap_a, ap_b], live_pids={1, 106, 107}, now=NOW)
    assert any("duplicate" in r for r in ap_a.classification_reasons)
    assert any("duplicate" in r for r in ap_b.classification_reasons)


def test_active_session_protection_overrides_orphan_classification(tmp_path):
    # An active session directory must exist to be protectable, so the
    # corroborating signal here is "duplicate instance" rather than a
    # missing working directory (which would require the dir to be absent).
    session_dir = tmp_path / "active-session"
    session_dir.mkdir()
    proc_a = make_process(
        pid=108, ppid=999, create_time=NOW - 100_000, cpu_percent=0.0, cwd=str(session_dir)
    )
    proc_b = make_process(
        pid=109, ppid=999, create_time=NOW - 100_000, cpu_percent=0.0, cwd=str(session_dir)
    )
    ap_a = _agent_process(proc_a, role="mcp-server")
    ap_b = _agent_process(proc_b, role="mcp-server")
    classify_processes([ap_a, ap_b], live_pids={108, 109}, now=NOW)
    assert ap_a.classification == ProcessClassification.CONFIRMED_ORPHANED

    apply_active_session_protection([ap_a, ap_b], active_paths=[session_dir])
    assert ap_a.protected is True
    assert ap_a.classification == ProcessClassification.LIKELY_ACTIVE
