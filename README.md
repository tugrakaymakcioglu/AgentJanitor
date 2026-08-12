# AgentJanitor

Your AI coding agents leave a mess. Clean it up.

AgentJanitor finds orphaned processes, bloated sessions,
broken MCP servers, stale caches and exposed credentials
across your AI coding tools.

`$ agentjanitor scan`

![agentjanitor scan output](docs/images/scan-demo.svg)

`$ agentjanitor fix`

![agentjanitor fix output](docs/images/fix-demo.svg)

<sub>Both screenshots are real output from AgentJanitor's own renderer (captured via Rich's SVG
export), run against a representative example scenario — not hand-drawn mockups.</sub>

## Why

AI coding agents (Claude Code, Codex, Gemini CLI, and others) spawn
background processes, MCP servers, and session/cache data that quietly
accumulate. Left unmanaged, that shows up as leaked helper processes eating
RAM, gigabytes of stale session history, duplicated or broken MCP server
definitions, and — occasionally — a plaintext credential sitting in a
config file that never got rotated.

AgentJanitor is a local-first diagnostics and cleanup tool built
specifically for this problem. It understands agent-specific concepts —
MCP servers, sessions, task workspaces, plugin caches — instead of treating
your machine as a generic pile of files to sweep.

**Safety is more important than cleanup effectiveness.** AgentJanitor would
rather leave something behind labeled "possibly stale — manual review
required" than delete or kill something a false positive got wrong. See
[Safety model](#safety-model).

## Features

- **Agent installation detection** with confidence levels and stated evidence, never a guess from one weak signal.
- **Process discovery and conservative orphan classification** (`ACTIVE` → `CONFIRMED_ORPHANED`) using multiple corroborating signals, never age or CPU alone.
- **Active-session protection** — a process working inside a session touched moments ago can never be auto-terminated.
- **Disk usage analysis** split into safe-reclaimable, archive-candidate, and unknown — never one big "reclaimable" number.
- **Session lifecycle classification** (`ACTIVE`/`RECENT`/`ARCHIVE_CANDIDATE`/`STALE`) with archiving preferred over deletion.
- **MCP configuration discovery** across agents, with duplicate-definition detection (by command/args/URL, not display name) and static health checks (executable exists, URL well-formed, path exists) — never launches a third-party MCP command during a normal scan.
- **Credential hygiene scanning** for common secret patterns, with values never printed — only a short fingerprint.
- **Deterministic, explainable health score** (0–100) with every point loss traced back to a specific finding.
- **Safe cleanup engine**: typed actions with explicit risk levels; only `SAFE` actions are auto-selected by `fix`.
- **Dry-run** support that performs zero mutations.
- **Backup and undo** for every reversible mutation.
- **`doctor`** for deep, per-agent, actionable diagnostics.
- **`--json`** output with a stable, versioned schema for CI/automation.

## Supported agents

| Agent | Status |
|---|---|
| OpenAI Codex | Supported |
| Claude Code | Supported |
| Gemini CLI | Experimental — on-disk layout is less consistently documented across versions; detection confidence is capped accordingly |

Future versions may add OpenCode, Cursor, Cline, Aider, Windsurf, Kiro, and others.

## Installation

```bash
pipx install agentjanitor
```

or

```bash
uv tool install agentjanitor
```

## Quick start

```bash
agentjanitor scan
```

```bash
agentjanitor fix --dry-run
```

```bash
agentjanitor fix
```

```bash
agentjanitor undo
```

## Safety model

- Only `CONFIRMED_ORPHANED` processes — dead parent **and** sustained idleness **and** at least one corroborating structural signal — may be auto-terminated, and never an agent's main interactive process.
- A process working inside a currently-active session is **protected** and can never be auto-terminated, regardless of any other signal.
- Old sessions are never deleted by default; they are archived (compressed) once past a configurable threshold.
- `fix` always shows the full plan — description, risk level, reversibility, estimated impact — before anything happens, and only auto-selects `SAFE`-risk actions.
- `fix --dry-run` performs zero mutations.
- A backup manifest is created before any destructive filesystem operation; `agentjanitor undo` restores it.
- MCP servers are never executed during a normal scan.
- Scanning is scoped to agent-related directories that adapters themselves discovered — never the whole home directory.
- Deletion/size-scanning never follows a symlink out of its intended directory.

## What AgentJanitor never does

- ✓ No telemetry
- ✓ No cloud account
- ✓ No uploads
- ✓ No AI API required
- ✓ Runs locally

It also never: silently edits your agent configuration (proposed config changes are shown as a diff and require confirmation), guesses that something is orphaned from a single signal, deletes session history by default, or executes an MCP command during a normal scan.

This describes AgentJanitor itself — it does not make claims about the third-party agents it inspects.

## Architecture

```text
src/agentjanitor/
├── cli/            Typer commands
├── core/           scan orchestration, health scoring, config, knowledge base loader
├── adapters/       one module per agent; all provider-specific paths/rules live here
├── scanners/       processes, storage, sessions, mcp, configs, security — adapter-agnostic
├── diagnostics/    `doctor`'s deeper per-agent checks
├── cleanup/        typed actions, plan generation, dry-run/execution
├── backup/         backup manifest creation and restore
├── reporting/      terminal (Rich) and JSON output
├── models/         Pydantic domain models shared across the codebase
├── platform/       OS abstraction (paths, process APIs) — no OS checks anywhere else
└── knowledge/      static known-issue records (scaffolding, not yet consulted by scanners)
```

Adding a new agent means writing one adapter that implements `AgentAdapter`
— scanners, cleanup, and the CLI never change.

## Platform support

Targets Windows 10/11, macOS, and Linux. Path handling uses `pathlib`
throughout; OS-specific behavior (AppData/Application Support/XDG
directories, process APIs) lives behind `agentjanitor.platform` and nowhere
else.

## Roadmap

- **V2** — more agent adapters (OpenCode, Cursor, Cline, Aider, Windsurf, Kiro)
- **V3** — known-issue matching against the knowledge base
- **V4** — historical health trends
- **V5** — team/org policy auditing
- **V6** — optional enterprise agent-fleet health

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
