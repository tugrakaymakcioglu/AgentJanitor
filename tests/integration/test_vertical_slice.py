"""End-to-end vertical slice, fully fixture-driven (no real agent required):

fixture environment -> scan -> findings -> health score -> cleanup plan ->
dry-run -> safe mutation -> undo.

This is the trust-critical path: it must prove that dry-run mutates
nothing, that only SAFE actions ever run automatically, that protected
processes are never touched, and that undo actually restores what fix
removed.
"""

from __future__ import annotations

import time

from agentjanitor.backup.manager import BackupManager
from agentjanitor.cleanup.executor import execute_plan
from agentjanitor.cleanup.planner import build_cleanup_plan, select_safe_actions
from agentjanitor.core.scan import run_scan
from agentjanitor.models.process import ProcessClassification
from agentjanitor.reporting.json_schema import scan_result_to_json
from tests.fixtures.builder import build_fixture_environment
from tests.fixtures.fake_adapter import FakeAgentAdapter
from tests.fixtures.processes import make_process, make_unrelated_process


def _build_process_universe(env, tmp_path):
    t0 = time.time()
    missing_cwd = str(tmp_path / "nonexistent-cwd")

    confirmed_orphan = make_process(
        pid=50001,
        ppid=99_999,  # dead parent
        role="mcp-server",
        create_time=t0 - 100_000,  # long idle
        cpu_percent=0.0,
        cwd=missing_cwd,  # corroborating signal
    )
    protected_a = make_process(
        pid=50002,
        ppid=99_998,
        role="mcp-server",
        create_time=t0 - 100_000,
        cpu_percent=0.0,
        cwd=str(env.session_active),  # inside an active session -> protected
        extra_args=["--twin"],
    )
    protected_b = make_process(
        pid=50003,
        ppid=99_998,
        role="mcp-server",
        create_time=t0 - 100_000,
        cpu_percent=0.0,
        cwd=str(env.session_active),
        extra_args=["--twin"],  # identical cmdline to protected_a -> duplicate signal
    )
    healthy_main = make_process(pid=50004, ppid=1, role="main", cpu_percent=15.0)
    unrelated = make_unrelated_process(pid=50005, ppid=1)
    # A stand-in for the OS init/System process (pid 1) so ppid=1 above
    # resolves as "parent alive" the way it would against a real process
    # list, which always includes it.
    init_process = make_unrelated_process(pid=1, ppid=None)

    return [confirmed_orphan, protected_a, protected_b, healthy_main, unrelated, init_process]


def test_full_vertical_slice(tmp_path):
    env = build_fixture_environment(tmp_path)
    adapter = FakeAgentAdapter(env.root)
    processes = _build_process_universe(env, tmp_path)

    # 1. scan -> findings -> health score
    result = run_scan([adapter], processes=processes)

    assert result.installations[0].detected is True
    assert result.findings, "fixture is designed to produce findings"
    assert 0 <= result.health.score < 100

    categories = {f.category for f in result.findings}
    assert {"processes", "storage", "mcp", "security"} <= categories

    # JSON output must serialize without error (stable schema contract).
    payload = scan_result_to_json(result)
    assert payload["schema_version"] == "1"
    assert payload["summary"]["health_score"] == result.health.score

    # Confirmed orphan correctly classified; protected twins overridden despite
    # having the same orphan signal count.
    by_pid = {ap.process.pid: ap for ap in result.agent_processes}
    assert by_pid[50001].classification == ProcessClassification.CONFIRMED_ORPHANED
    assert by_pid[50002].protected is True
    assert by_pid[50003].protected is True
    assert by_pid[50002].classification != ProcessClassification.CONFIRMED_ORPHANED
    assert by_pid[50004].classification == ProcessClassification.ACTIVE

    # 2. cleanup plan
    approved_roots = result.approved_roots([adapter])
    plan = build_cleanup_plan(result.agent_processes, result.storage_breakdowns, approved_roots)

    all_planned_pids = {pid for a in plan.actions for pid in a.affected_pids}
    assert 50001 in all_planned_pids
    assert 50002 not in all_planned_pids
    assert 50003 not in all_planned_pids

    safe_actions = select_safe_actions(plan)
    assert safe_actions, "fixture is designed to produce at least one SAFE action"

    # every affected path must be safely inside the fixture root
    for action in safe_actions:
        for path in action.affected_paths:
            assert str(path).startswith(str(env.root.resolve()))

    # 3. dry-run must mutate nothing
    pre_dry_run_snapshot = {p: p.exists() for p in _all_action_paths(safe_actions)}
    dry_report = execute_plan(safe_actions, dry_run=True)
    assert dry_report.dry_run is True
    assert dry_report.backup is None
    for path, existed in pre_dry_run_snapshot.items():
        assert path.exists() == existed, "dry-run must not mutate the filesystem"
    assert env.temp_stale.exists()
    assert env.session_stale.exists()

    # 4. real safe mutation
    manager = BackupManager(base_dir=tmp_path / "aj-backups")
    real_report = execute_plan(safe_actions, dry_run=False, backup_manager=manager)
    assert real_report.all_succeeded

    assert not env.temp_stale.exists(), "stale temp workspace should be removed"
    assert not env.session_stale.exists(), "stale session should be archived away"
    assert not env.session_archive_candidate.exists(), "archive-candidate session should be archived away"
    assert env.session_active.exists(), "active session must never be touched"
    assert env.temp_fresh.exists(), "fresh temp workspace must never be touched"

    assert real_report.backup is not None
    backup = real_report.backup
    assert len(backup.entries) > 0

    # 5. undo restores everything that was backed up (not cache, which is
    # regenerable and intentionally never backed up).
    notes = manager.restore(backup)
    assert env.temp_stale.exists(), "undo should restore the removed temp workspace"
    assert (env.temp_stale / "scratch.txt").read_text() == "leftover work"
    assert env.session_stale.exists(), "undo should restore the archived session"
    assert backup.restored is True
    assert notes


def _all_action_paths(actions):
    paths = []
    for action in actions:
        paths.extend(action.affected_paths)
    return paths
