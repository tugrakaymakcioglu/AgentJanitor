# Contributing to AgentJanitor

Thanks for considering a contribution. AgentJanitor is a safety-first tool
by design — please read the [safety model](README.md#safety-model) before
proposing changes to detection, classification, or cleanup logic.

## Development setup

```bash
python -m venv .venv
source .venv/Scripts/activate   # or .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"
```

```bash
pytest
ruff check .
mypy src
```

## Adding a new agent adapter

1. Create `src/agentjanitor/adapters/<agent>.py` implementing `AgentAdapter`
   (see `adapters/base.py`). All provider-specific paths, executable names,
   and process-matching rules belong here — never in a scanner.
2. Register it in `adapters/registry.py`.
3. Add fixture-backed unit tests under `tests/unit/` covering `detect()`,
   process identification, and MCP config discovery. Tests must not require
   the real agent to be installed.
4. If any path or behavior is uncertain or version-dependent, keep detection
   confidence conservative (see `DetectionConfidence`) and document the
   uncertainty in the adapter's module docstring, the way `adapters/gemini.py`
   does.

## Ground rules

- No single weak signal may ever justify a `CONFIRMED_ORPHANED` process
  classification or an automatic `SAFE`-risk destructive action. See
  `scanners/processes.py` for the existing bar.
- Never widen scanning scope beyond directories an adapter discovered.
- Never introduce a code path that executes a configured MCP command during
  a normal scan.
- All destructive filesystem operations must go through
  `utils.safe_path.assert_within_roots`.
- Add tests alongside any new scanner or cleanup logic, including a
  dry-run-performs-no-mutation test for anything destructive.

## Pull requests

- Keep PRs focused; a bug fix doesn't need accompanying refactors.
- Run `pytest`, `ruff check .`, and `mypy src` before opening a PR.
- Describe what changed and why, not just what.
