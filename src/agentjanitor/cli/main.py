"""AgentJanitor CLI entry point."""

from __future__ import annotations

import contextlib
import json
import sys
from importlib import metadata
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from agentjanitor.adapters.registry import all_adapters
from agentjanitor.backup.manager import BackupError, BackupManager
from agentjanitor.cleanup.executor import execute_plan
from agentjanitor.cleanup.planner import build_cleanup_plan, select_safe_actions
from agentjanitor.core.scan import run_scan
from agentjanitor.diagnostics.doctor import CheckStatus, run_doctor
from agentjanitor.reporting.json_schema import scan_result_to_json
from agentjanitor.reporting.terminal import (
    render_cleanup_plan,
    render_detection,
    render_mcp,
    render_process_table,
    render_processes,
    render_scan,
    render_security,
    render_storage,
)

# Some Windows terminals (legacy cmd.exe codepages) can't encode the ✓/⚠/─
# characters used in the report output. Replacing rather than crashing keeps
# the tool usable there instead of dying on a UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        _stream.reconfigure(errors="replace")  # type: ignore[union-attr]

app = typer.Typer(
    name="agentjanitor",
    help="Your AI coding agents leave a mess. Clean it up.",
    no_args_is_help=True,
)
console = Console()


def _version_string() -> str:
    try:
        return metadata.version("agentjanitor")
    except metadata.PackageNotFoundError:
        return "0.1.0"


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"AgentJanitor v{_version_string()}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version and exit."),
    ] = False,
) -> None:
    pass


def _print_or_json(result_dict: dict, as_json: bool, render_fn) -> None:
    if as_json:
        console.print_json(json.dumps(result_dict))
    else:
        render_fn()


@app.command()
def scan(
    json_output: Annotated[bool, typer.Option("--json", help="Output machine-readable JSON.")] = False,
) -> None:
    """Detect installed agents and report processes, storage, MCP, and security findings."""
    adapters = all_adapters()
    result = run_scan(adapters)

    if json_output:
        console.print_json(json.dumps(scan_result_to_json(result)))
        return

    console.print(f"[bold]AgentJanitor v{_version_string()}[/bold]")
    render_scan(console, result)


@app.command()
def doctor(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Run deeper, per-agent diagnostics with actionable remediation steps."""
    adapters = all_adapters()
    reports = run_doctor(adapters)

    if json_output:
        console.print_json(json.dumps([r.model_dump(mode="json") for r in reports]))
        return

    for report in reports:
        console.print()
        console.print(f"[bold]{report.agent}[/bold]")
        console.print("─" * 20)
        for check in report.checks:
            color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}[check.status.value]
            console.print(f"{check.name:<16} [{color}]{check.status.value}[/{color}]")
        for check in report.checks:
            if check.status != CheckStatus.PASS and check.details:
                console.print()
                color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}[check.status.value]
                console.print(f"[{color}]{check.name} {check.status.value}[/{color}]")
                for line in check.details:
                    console.print(f"  {line}")


@app.command()
def processes(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """List agent-related processes and their orphan classification."""
    adapters = all_adapters()
    result = run_scan(adapters)
    if json_output:
        console.print_json(json.dumps(scan_result_to_json(result)["processes"]))
        return
    render_process_table(console, result)
    render_processes(console, result)


@app.command()
def storage(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Show agent-related disk usage, broken down by category and disposition."""
    adapters = all_adapters()
    result = run_scan(adapters)
    if json_output:
        console.print_json(json.dumps(scan_result_to_json(result)["storage"]))
        return
    render_storage(console, result)


@app.command()
def mcp(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Show configured MCP servers, duplicates, and health checks."""
    adapters = all_adapters()
    result = run_scan(adapters)
    if json_output:
        console.print_json(json.dumps(scan_result_to_json(result)["mcp"]))
        return
    render_mcp(console, result)


@app.command()
def security(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Scan agent configuration and session data for obvious credential hygiene issues."""
    adapters = all_adapters()
    result = run_scan(adapters)
    if json_output:
        findings = [f.model_dump(mode="json") for f in result.findings if f.category == "security"]
        console.print_json(json.dumps(findings))
        return
    render_security(console, result)


@app.command()
def status() -> None:
    """One-line health summary, suitable for scripts and prompts."""
    adapters = all_adapters()
    result = run_scan(adapters)
    detected = sum(1 for i in result.installations if i.detected)
    reclaimable = sum(b.safe_reclaimable_bytes for b in result.storage_breakdowns)
    from agentjanitor.utils.format import human_bytes

    console.print(
        f"agents={detected} health={result.health.score}/100 "
        f"reclaimable={human_bytes(reclaimable)} findings={len(result.findings)}"
    )


@app.command()
def report(
    output: Annotated[Path, typer.Option("--output", "-o", help="File to write.")] = Path(
        "agentjanitor-report.json"
    ),
) -> None:
    """Write a full scan report to a file (JSON)."""
    adapters = all_adapters()
    result = run_scan(adapters)
    output.write_text(json.dumps(scan_result_to_json(result), indent=2), encoding="utf-8")
    console.print(f"Report written to {output}")


@app.command()
def fix(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the plan; perform zero mutations.")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
) -> None:
    """Show a safe cleanup plan and, on confirmation, perform only SAFE operations."""
    adapters = all_adapters()
    result = run_scan(adapters)
    approved_roots = result.approved_roots(adapters)
    plan = build_cleanup_plan(result.agent_processes, result.storage_breakdowns, approved_roots)

    render_cleanup_plan(console, plan)
    safe_actions = select_safe_actions(plan)

    if not safe_actions:
        return

    if dry_run:
        report_result = execute_plan(safe_actions, dry_run=True)
        for r in report_result.results:
            console.print(f"[dim]{r.detail}[/dim]")
        return

    if not yes and not typer.confirm("Continue?", default=False):
        console.print("Aborted.")
        raise typer.Exit(code=1)

    report_result = execute_plan(safe_actions, dry_run=False)
    console.print()
    for r in report_result.results:
        if r.error:
            console.print(f"[red]✗ {r.action_id}: {r.error}[/red]")
        else:
            console.print(f"[green]✓ {r.action_id}: {r.detail}[/green]")
    if report_result.backup is not None:
        console.print()
        console.print(f"Backup created: {report_result.backup.manifest_path.parent}")


@app.command()
def undo(
    backup_id: Annotated[str | None, typer.Option("--backup-id", help="Specific backup to restore.")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Restore files from the most recent (or a specific) AgentJanitor backup."""
    manager = BackupManager()
    if backup_id:
        try:
            backup = manager.load_manifest(manager.base_dir / backup_id)
        except BackupError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc
    else:
        backup = manager.latest_backup()
        if backup is None:
            console.print("No backups found.")
            raise typer.Exit(code=1)

    if backup.restored:
        console.print(f"Backup {backup.backup_id} was already restored.")
        raise typer.Exit(code=1)

    console.print(f"Restoring backup {backup.backup_id} ({len(backup.entries)} item(s))...")
    if not yes and not typer.confirm("Continue?", default=False):
        console.print("Aborted.")
        raise typer.Exit(code=1)

    notes = manager.restore(backup)
    for note in notes:
        console.print(f"  {note}")


@app.command("detect")
def detect() -> None:
    """Show detailed agent-installation evidence."""
    adapters = all_adapters()
    result = run_scan(adapters)
    render_detection(console, result)


if __name__ == "__main__":
    app()
