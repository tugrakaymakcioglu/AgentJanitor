"""Cleanup plan generation: only well-classified items become actions, and
only within an adapter's approved roots."""

from __future__ import annotations

from agentjanitor.cleanup.planner import build_cleanup_plan, select_safe_actions
from agentjanitor.models.cleanup import CleanupActionType, RiskLevel
from agentjanitor.models.process import AgentProcess, ProcessClassification
from agentjanitor.scanners.storage import scan_storage
from tests.fixtures.builder import build_fixture_environment
from tests.fixtures.fake_adapter import FakeAgentAdapter
from tests.fixtures.processes import make_process


def test_plan_includes_confirmed_orphan_termination_only():
    confirmed = AgentProcess(
        process=make_process(pid=1, ppid=None),
        agent="Fake Agent",
        role="mcp-server",
        classification=ProcessClassification.CONFIRMED_ORPHANED,
    )
    likely = AgentProcess(
        process=make_process(pid=2, ppid=None),
        agent="Fake Agent",
        role="mcp-server",
        classification=ProcessClassification.LIKELY_ORPHANED,
    )
    plan = build_cleanup_plan([confirmed, likely], [], {"Fake Agent": []})

    terminate_actions = [a for a in plan.actions if a.action_type == CleanupActionType.TERMINATE_PROCESS]
    assert len(terminate_actions) == 1
    assert terminate_actions[0].affected_pids == [1]
    assert terminate_actions[0].risk_level == RiskLevel.SAFE

    excluded = [a for a in plan.excluded_actions if a.action_type == CleanupActionType.TERMINATE_PROCESS]
    assert len(excluded) == 1
    assert excluded[0].affected_pids == [2]
    assert excluded[0].risk_level != RiskLevel.SAFE


def test_protected_process_is_never_planned_for_termination():
    protected = AgentProcess(
        process=make_process(pid=3, ppid=None),
        agent="Fake Agent",
        role="mcp-server",
        classification=ProcessClassification.CONFIRMED_ORPHANED,
        protected=True,
        protected_reason="active session",
    )
    plan = build_cleanup_plan([protected], [], {"Fake Agent": []})
    assert plan.actions == []
    assert any("protected" in note for note in plan.protected_notes)


def test_plan_from_fixture_storage_generates_expected_action_types(tmp_path):
    env = build_fixture_environment(tmp_path)
    adapter = FakeAgentAdapter(env.root)
    breakdown, _ = scan_storage(adapter, now=env.now)

    plan = build_cleanup_plan([], [breakdown], {adapter.name: [env.root]})
    action_types = {a.action_type for a in plan.actions}

    assert CleanupActionType.DELETE_CACHE in action_types
    assert CleanupActionType.REMOVE_TEMP_WORKSPACE in action_types
    assert CleanupActionType.DELETE_LOG in action_types
    assert CleanupActionType.ARCHIVE_SESSIONS in action_types

    safe = select_safe_actions(plan)
    assert len(safe) == len(plan.actions)  # everything generated here is SAFE-risk


def test_plan_rejects_paths_outside_approved_roots(tmp_path):
    env = build_fixture_environment(tmp_path)
    adapter = FakeAgentAdapter(env.root)
    breakdown, _ = scan_storage(adapter, now=env.now)

    unrelated_root = tmp_path / "unrelated"
    unrelated_root.mkdir()
    plan = build_cleanup_plan([], [breakdown], {adapter.name: [unrelated_root]})

    assert plan.actions == []
    assert plan.protected_notes  # explains why every action was dropped


def test_plan_is_empty_for_untouched_agent():
    plan = build_cleanup_plan([], [], {})
    assert plan.actions == []
    assert plan.excluded_actions == []
