"""Builds a deterministic fixture directory tree standing in for a real
agent's on-disk footprint, so scanner/cleanup/health-score tests never
depend on any real coding agent being installed on the test machine.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

DAY = 86400


@dataclass
class FixtureEnvironment:
    root: Path
    now: float
    session_archive_candidate: Path = field(init=False)
    session_stale: Path = field(init=False)
    session_active: Path = field(init=False)
    temp_stale: Path = field(init=False)
    temp_fresh: Path = field(init=False)


def _write(path: Path, content: str, age_seconds: float | None = None, now: float = 0.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if age_seconds is not None:
        stamp = now - age_seconds
        os.utime(path, (stamp, stamp))


def _touch_dir(path: Path, age_seconds: float, now: float) -> None:
    path.mkdir(parents=True, exist_ok=True)
    stamp = now - age_seconds
    os.utime(path, (stamp, stamp))
    for entry in path.rglob("*"):
        os.utime(entry, (stamp, stamp))


def build_fixture_environment(tmp_path: Path, now: float | None = None) -> FixtureEnvironment:
    """Populate ``tmp_path`` and return handles to the interesting pieces.

    ``now`` may be injected for fully deterministic tests; defaults to the
    real current time since this only runs inside pytest, never inside a
    Workflow script.
    """
    now = now if now is not None else time.time()
    root = tmp_path / "fakeagent"
    root.mkdir(parents=True, exist_ok=True)

    settings = {
        "profile": "default",
        "telemetry": False,
        # Deliberately fake/dead credential used only to test redaction.
        "api_key": "sk-FAKE1234567890TESTONLYDONOTUSE",
    }
    _write(root / "config" / "settings.json", json.dumps(settings, indent=2))

    mcp_config = {
        "mcpServers": {
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_TOKEN": "placeholder"},
            },
            "github-project-copy": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_TOKEN": "placeholder"},
            },
            "broken-server": {
                "command": "/nonexistent/path/to/binary-that-does-not-exist",
                "args": [],
            },
            "remote-server": {
                "url": "https://mcp.example.com/sse",
                "transport": "sse",
            },
        }
    }
    _write(root / "config" / "mcp.json", json.dumps(mcp_config, indent=2))

    sessions_dir = root / "sessions"
    session_active = sessions_dir / "session-active"
    session_recent = sessions_dir / "session-recent"
    session_archive = sessions_dir / "session-archive-candidate"
    session_stale = sessions_dir / "session-stale"

    _write(session_active / "transcript.jsonl", '{"role": "user", "content": "hi"}\n')
    _touch_dir(session_active, age_seconds=5 * 60, now=now)

    _write(session_recent / "transcript.jsonl", '{"role": "user", "content": "hi"}\n')
    _touch_dir(session_recent, age_seconds=10 * DAY, now=now)

    _write(session_archive / "transcript.jsonl", '{"role": "user", "content": "hi"}\n')
    _touch_dir(session_archive, age_seconds=90 * DAY, now=now)

    _write(session_stale / "transcript.jsonl", '{"role": "user", "content": "hi"}\n')
    _touch_dir(session_stale, age_seconds=400 * DAY, now=now)

    cache_dir = root / "cache"
    _write(cache_dir / "v1" / "blob.bin", "x" * 4096)
    _write(cache_dir / "v2" / "blob.bin", "x" * 4096)
    _touch_dir(cache_dir, age_seconds=30 * DAY, now=now)

    logs_dir = root / "logs"
    _write(logs_dir / "old.log", "old log content\n" * 100, age_seconds=120 * DAY, now=now)
    _write(logs_dir / "recent.log", "recent log content\n" * 10, age_seconds=1 * DAY, now=now)

    temp_dir = root / "temp"
    temp_stale = temp_dir / "workspace-stale"
    temp_fresh = temp_dir / "workspace-fresh"
    _write(temp_stale / "scratch.txt", "leftover work")
    _touch_dir(temp_stale, age_seconds=14 * DAY, now=now)
    _write(temp_fresh / "scratch.txt", "in progress work")
    _touch_dir(temp_fresh, age_seconds=1 * 3600, now=now)

    env = FixtureEnvironment(root=root, now=now)
    env.session_archive_candidate = session_archive
    env.session_stale = session_stale
    env.session_active = session_active
    env.temp_stale = temp_stale
    env.temp_fresh = temp_fresh
    return env
