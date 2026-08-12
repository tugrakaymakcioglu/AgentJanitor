"""Session age classification and storage aggregation must never over-claim reclaimability."""

from __future__ import annotations

from agentjanitor.models.storage import DiskCategory, SessionStatus
from agentjanitor.scanners.sessions import classify_session_age, classify_temp_workspace_age
from agentjanitor.scanners.storage import scan_storage
from tests.fixtures.builder import build_fixture_environment
from tests.fixtures.fake_adapter import FakeAgentAdapter


def test_session_age_classification_boundaries(tmp_path):
    env = build_fixture_environment(tmp_path)
    assert classify_session_age(env.session_active, now=env.now) == SessionStatus.ACTIVE
    assert classify_session_age(env.session_archive_candidate, now=env.now) == SessionStatus.ARCHIVE_CANDIDATE
    assert classify_session_age(env.session_stale, now=env.now) == SessionStatus.STALE


def test_missing_path_is_unknown_not_stale(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert classify_session_age(missing) == SessionStatus.UNKNOWN


def test_temp_workspace_classification(tmp_path):
    env = build_fixture_environment(tmp_path)
    assert classify_temp_workspace_age(env.temp_stale, now=env.now) == SessionStatus.STALE
    assert classify_temp_workspace_age(env.temp_fresh, now=env.now) == SessionStatus.ACTIVE


def test_storage_breakdown_splits_reclaimable_from_archive_and_unknown(tmp_path):
    env = build_fixture_environment(tmp_path)
    adapter = FakeAgentAdapter(env.root)

    breakdown, findings = scan_storage(adapter, now=env.now)

    assert breakdown.total_bytes > 0
    assert breakdown.safe_reclaimable_bytes > 0
    assert breakdown.archive_candidate_bytes > 0
    # The stale temp workspace and stale log must count as safely reclaimable...
    temp_items = [i for i in breakdown.items if i.category == DiskCategory.TEMP_WORKSPACE]
    assert any(i.status == SessionStatus.STALE for i in temp_items)
    # ...but the active/recent session must never be folded into reclaimable totals.
    active_session_item = next(i for i in breakdown.items if i.path == env.session_active)
    assert active_session_item.status == SessionStatus.ACTIVE

    finding_ids = {f.id for f in findings}
    assert any(fid.startswith("storage.reclaimable") for fid in finding_ids)
    assert any(fid.startswith("storage.archive-candidate") for fid in finding_ids)


def test_nothing_is_reclaimable_when_everything_is_fresh(tmp_path):
    adapter = FakeAgentAdapter(tmp_path / "empty-agent")
    breakdown, findings = scan_storage(adapter)
    assert breakdown.total_bytes == 0
    assert breakdown.safe_reclaimable_bytes == 0
    assert findings == []
