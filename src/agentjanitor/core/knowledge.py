"""Loader for the static known-issue knowledge base (see ``agentjanitor/knowledge/``).

V1 loads and validates these records so the file format is locked down,
but no scanner consults them yet — matching findings to known upstream
issues is future work. Requires no network access, ever.
"""

from __future__ import annotations

from importlib import resources

import yaml
from pydantic import BaseModel


class KnownIssueReference(BaseModel):
    repository: str
    issue: int | None = None
    note: str | None = None


class KnownIssueMatch(BaseModel):
    process_pattern: str | None = None


class KnownIssue(BaseModel):
    id: str
    agent: str
    description: str
    match: KnownIssueMatch
    reference: KnownIssueReference


def load_known_issues(agent_slug: str) -> list[KnownIssue]:
    """Load known-issue records for one agent slug, e.g. 'codex'."""
    try:
        raw_text = resources.files("agentjanitor.knowledge").joinpath(f"{agent_slug}.yaml").read_text(
            encoding="utf-8"
        )
    except (FileNotFoundError, ModuleNotFoundError):
        return []
    data = yaml.safe_load(raw_text) or []
    if not isinstance(data, list):
        return []
    return [KnownIssue.model_validate(record) for record in data]
