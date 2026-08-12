# Security Policy

## Reporting a Vulnerability

Please report security vulnerabilities by opening a private security
advisory on GitHub (Security tab → "Report a vulnerability") rather than a
public issue. If that isn't available, open an issue asking for a private
contact channel and avoid including exploit details in it.

Please include:

- A description of the vulnerability and its impact
- Steps to reproduce
- The affected AgentJanitor version and OS

We aim to acknowledge reports within a few days.

## Scope and design notes for reviewers

AgentJanitor runs entirely locally and does not require network access to
function. Relevant properties a security review should verify:

- **No telemetry, no uploads.** AgentJanitor never sends scan data,
  findings, or file contents anywhere.
- **Scoped scanning.** Scanners only touch directories that an agent
  adapter itself discovered (e.g. `~/.claude`, `~/.codex`, `~/.gemini`),
  never the whole home directory.
- **No secret values are ever persisted or printed.** `agentjanitor
  security` reports a short fingerprint (`sk-...7a2f`) only.
- **Path safety.** All destructive filesystem operations go through
  `agentjanitor.utils.safe_path`, which resolves symlinks and rejects any
  path outside an adapter's approved roots.
- **No shell injection.** All subprocess/filesystem operations use argument
  lists, never `shell=True` with interpolated strings.
- **Conservative process termination.** Only `CONFIRMED_ORPHANED`
  processes — multiple independent corroborating signals, never an agent's
  main process — are ever auto-selected for termination by `fix`.

If you find a place where any of the above doesn't hold, that's a
vulnerability report, not just a bug report.
