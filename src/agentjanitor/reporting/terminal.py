"""Rich-based terminal rendering for scan/doctor/processes/storage/mcp/security."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from agentjanitor.core.scan import ScanResult
from agentjanitor.models.agent import DetectionConfidence
from agentjanitor.models.cleanup import CleanupPlan
from agentjanitor.models.mcp import MCPHealthStatus
from agentjanitor.models.process import ProcessClassification
from agentjanitor.utils.format import human_bytes
from agentjanitor.utils.symbols import get_symbols


def _section(console: Console, title: str) -> None:
    sym = get_symbols(console)
    console.print()
    console.print(f"[bold]{title}[/bold]")
    console.print(sym.rule_char * 32)


def render_agents(console: Console, result: ScanResult) -> None:
    sym = get_symbols(console)
    console.print()
    console.print("[bold]Detected agents:[/bold]")
    console.print()
    for installation in result.installations:
        mark = f"[green]{sym.check}[/green]" if installation.detected else f"[dim]{sym.cross}[/dim]"
        console.print(f"{mark} {installation.agent}")


def render_processes(console: Console, result: ScanResult) -> None:
    sym = get_symbols(console)
    _section(console, "Processes")
    process_findings = [f for f in result.findings if f.category == "processes"]
    if not process_findings:
        console.print("[green]No suspicious processes detected.[/green]")
        return
    for finding in process_findings:
        ram = finding.metadata.get("estimated_ram_bytes")
        ram_str = f"\n  Estimated RAM: {human_bytes(int(ram))}" if ram else ""
        console.print(f"[yellow]{sym.warn}[/yellow] {finding.title}{ram_str}")


def render_storage(console: Console, result: ScanResult) -> None:
    _section(console, "Storage")
    total_reclaimable = 0
    for breakdown in result.storage_breakdowns:
        if breakdown.total_bytes == 0:
            continue
        console.print(f"[bold]{breakdown.agent}[/bold]")
        for category, size in breakdown.by_category.items():
            if size > 0:
                console.print(f"  {category:<20} {human_bytes(size)}")
        total_reclaimable += breakdown.safe_reclaimable_bytes
    console.print()
    console.print(f"Potentially reclaimable: [bold]{human_bytes(total_reclaimable)}[/bold]")


def render_mcp(console: Console, result: ScanResult) -> None:
    sym = get_symbols(console)
    _section(console, "MCP")
    total = len(result.mcp_health_checks)
    console.print(f"Configured servers: {total}")
    duplicate_findings = [f for f in result.findings if f.id.startswith("mcp.duplicate")]
    unreachable = [hc for hc in result.mcp_health_checks if hc.status == MCPHealthStatus.FAIL]
    if duplicate_findings:
        console.print(f"[yellow]{sym.warn}[/yellow] {len(duplicate_findings)} duplicate server definitions")
    if unreachable:
        console.print(f"[yellow]{sym.warn}[/yellow] {len(unreachable)} unreachable/broken servers")
    if not duplicate_findings and not unreachable and total:
        console.print("[green]All configured MCP servers look healthy.[/green]")


def render_security(console: Console, result: ScanResult) -> None:
    sym = get_symbols(console)
    _section(console, "Security")
    security_findings = [f for f in result.findings if f.category == "security"]
    if not security_findings:
        console.print("[green]No credential hygiene issues detected.[/green]")
        return
    max_shown = 10
    for finding in security_findings[:max_shown]:
        console.print(f"[yellow]{sym.warn}[/yellow] {finding.title}")
        for line in finding.evidence:
            console.print(f"    {line}")
    remaining = len(security_findings) - max_shown
    if remaining > 0:
        console.print(f"[dim]... and {remaining} more (see `agentjanitor security --json`)[/dim]")


def render_health_score(console: Console, result: ScanResult) -> None:
    _section(console, "Health Score")
    console.print()
    score = result.health.score
    color = "green" if score >= 80 else "yellow" if score >= 50 else "red"
    console.print(f"[bold {color}]{score} / 100[/bold {color}]")
    if result.health.deductions:
        console.print()
        for deduction in result.health.deductions:
            console.print(f"  -{deduction.points:<3} {deduction.description}")


def render_scan(console: Console, result: ScanResult) -> None:
    render_agents(console, result)
    render_processes(console, result)
    render_storage(console, result)
    render_mcp(console, result)
    render_security(console, result)
    render_health_score(console, result)


def render_cleanup_plan(console: Console, plan: CleanupPlan) -> None:
    console.print()
    console.print("[bold]Safe cleanup plan[/bold]")
    console.print()
    if not plan.actions:
        console.print("[green]Nothing to clean up.[/green]")
    for idx, action in enumerate(plan.actions, start=1):
        console.print(f"{idx}. {action.description}")
        if action.estimated_bytes:
            console.print(f"   Estimated disk reclaimed: {human_bytes(action.estimated_bytes)}")
        if action.estimated_ram_bytes:
            console.print(f"   Estimated RAM reclaimed: {human_bytes(action.estimated_ram_bytes)}")
        console.print(f"   Reversible: {action.reversible.value.replace('_', ' ')}")
        console.print()

    if plan.excluded_actions:
        console.print("[dim]The following require manual review (not auto-selected):[/dim]")
        for action in plan.excluded_actions:
            console.print(f"  - [{action.risk_level.value}] {action.description}")
        console.print()

    if plan.protected_notes:
        console.print("[dim]Protected / skipped:[/dim]")
        for note in plan.protected_notes:
            console.print(f"  - {note}")
        console.print()

    console.print("No active sessions will be modified.")
    backed_up_types = {"archive_sessions", "remove_temp_workspace", "delete_log"}
    if any(a.action_type.value in backed_up_types for a in plan.actions):
        console.print("Backup will be created before destructive operations.")


def render_process_table(console: Console, result: ScanResult) -> None:
    table = Table(title="Agent Processes")
    table.add_column("PID")
    table.add_column("Agent")
    table.add_column("Role")
    table.add_column("Classification")
    table.add_column("RAM")
    table.add_column("Protected")
    for ap in result.agent_processes:
        classification_color = {
            ProcessClassification.ACTIVE: "green",
            ProcessClassification.LIKELY_ACTIVE: "green",
            ProcessClassification.UNKNOWN: "yellow",
            ProcessClassification.LIKELY_ORPHANED: "yellow",
            ProcessClassification.CONFIRMED_ORPHANED: "red",
        }.get(ap.classification, "white")
        table.add_row(
            str(ap.process.pid),
            ap.agent,
            ap.role,
            f"[{classification_color}]{ap.classification.value}[/{classification_color}]",
            human_bytes(ap.estimated_ram_bytes or 0),
            "yes" if ap.protected else "",
        )
    console.print(table)


def render_detection(console: Console, result: ScanResult) -> None:
    sym = get_symbols(console)
    for installation in result.installations:
        console.print()
        console.print(f"[bold]{installation.agent}[/bold]")
        console.print(f"Detected: {'yes' if installation.detected else 'no'}")
        console.print(f"Confidence: {installation.confidence.value}")
        if installation.confidence != DetectionConfidence.NONE:
            console.print()
            console.print("Evidence:")
            for ev in installation.evidence:
                mark = sym.check if ev.positive else sym.cross
                console.print(f"{mark} {ev.description}")
