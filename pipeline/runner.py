"""CLI runner for the KIE.ai Kling 3.0 video generation pipeline.

Usage:
    python -m pipeline.runner generate-elements --scenario scenario/scenario.yaml
    python -m pipeline.runner generate-shots --scenario scenario/scenario.yaml
    python -m pipeline.runner download
    python -m pipeline.runner status
    python -m pipeline.runner run-all --scenario scenario/scenario.yaml
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()

# Default paths
_DEFAULT_CONFIG = "config.yaml"


def _setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet down httpx unless debugging
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


def _load_status(config_path: str, scenario_path: str | None = None) -> dict:
    """Load status from the paths specified in config, merging elements + shots."""
    from pipeline.auth import load_config, resolve_output_paths
    config = load_config(config_path)
    paths = resolve_output_paths(config, scenario_path)

    result = {}
    # Load shared elements status
    elem_status_path = paths["elements_status_file"]
    if elem_status_path.exists():
        with open(elem_status_path, "r", encoding="utf-8") as f:
            elem_data = json.load(f)
        result["elements"] = elem_data.get("elements", {})

    # Load per-scenario shots status
    shots_status_path = paths["status_file"]
    if shots_status_path.exists():
        with open(shots_status_path, "r", encoding="utf-8") as f:
            shots_data = json.load(f)
        result["shots"] = shots_data.get("shots", {})

    return result


@click.group()
@click.option("--config", "-c", default=_DEFAULT_CONFIG, help="Path to config.yaml")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx: click.Context, config: str, verbose: bool) -> None:
    """KIE.ai Kling 3.0 Video Generation Pipeline."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    _setup_logging(verbose)


@cli.command("generate-elements")
@click.option("--scenario", "-s", required=True, help="Path to scenario YAML file")
@click.pass_context
def cmd_generate_elements(ctx: click.Context, scenario: str) -> None:
    """Generate reference images for all elements."""
    from pipeline.generate_elements import generate_elements

    config_path = ctx.obj["config"]
    console.print("[bold]Starting element generation...[/bold]")

    try:
        asyncio.run(generate_elements(scenario_path=scenario, config_path=config_path))
    except FileNotFoundError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        sys.exit(1)
    except ValueError as exc:
        console.print(f"[red]Configuration error: {exc}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Progress has been saved to status.json.[/yellow]")
        sys.exit(130)


@cli.command("generate-shots")
@click.option("--scenario", "-s", required=True, help="Path to scenario YAML file")
@click.pass_context
def cmd_generate_shots(ctx: click.Context, scenario: str) -> None:
    """Generate videos for all shots."""
    from pipeline.generate_shots import generate_shots

    config_path = ctx.obj["config"]
    console.print("[bold]Starting shot generation...[/bold]")

    try:
        asyncio.run(generate_shots(scenario_path=scenario, config_path=config_path))
    except FileNotFoundError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        sys.exit(1)
    except ValueError as exc:
        console.print(f"[red]Configuration error: {exc}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Progress has been saved to status.json.[/yellow]")
        sys.exit(130)


@cli.command("download")
@click.option("--scenario", "-s", default=None, help="Path to scenario YAML file")
@click.pass_context
def cmd_download(ctx: click.Context, scenario: str | None) -> None:
    """Download all completed but not-yet-downloaded files."""
    from pipeline.downloader import download_all

    config_path = ctx.obj["config"]
    console.print("[bold]Starting download of completed files...[/bold]")

    try:
        asyncio.run(download_all(scenario_path=scenario, config_path=config_path))
    except FileNotFoundError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        sys.exit(1)
    except ValueError as exc:
        console.print(f"[red]Configuration error: {exc}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)


@cli.command("status")
@click.option("--scenario", "-s", default=None, help="Path to scenario YAML file")
@click.pass_context
def cmd_status(ctx: click.Context, scenario: str | None) -> None:
    """Show current pipeline status."""
    config_path = ctx.obj["config"]

    try:
        status = _load_status(config_path, scenario)
    except FileNotFoundError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        sys.exit(1)

    if not status:
        console.print("[yellow]No status file found. Pipeline has not been run yet.[/yellow]")
        return

    # Elements table
    elements = status.get("elements", {})
    if elements:
        table = Table(title="Elements", show_lines=True)
        table.add_column("Element", style="cyan")
        table.add_column("Views", justify="center")
        table.add_column("Completed", justify="center")
        table.add_column("Failed", justify="center")
        table.add_column("Status", justify="center")

        for elem_name, elem_data in sorted(elements.items()):
            views = elem_data.get("views", {})
            total = len(views)
            done = sum(1 for v in views.values() if v.get("status") == "completed")
            failed = sum(1 for v in views.values() if v.get("status") == "failed")
            is_complete = elem_data.get("completed", False)

            if is_complete:
                status_str = "[green]DONE[/green]"
            elif failed > 0:
                status_str = "[red]PARTIAL[/red]"
            elif done > 0:
                status_str = "[yellow]IN PROGRESS[/yellow]"
            else:
                status_str = "[dim]PENDING[/dim]"

            table.add_row(elem_name, str(total), str(done), str(failed), status_str)

        console.print(table)
        console.print()

    # Shots table
    shots = status.get("shots", {})
    if shots:
        table = Table(title="Shots", show_lines=True)
        table.add_column("Shot", style="cyan")
        table.add_column("Task ID", max_width=20)
        table.add_column("Status", justify="center")
        table.add_column("Local File", max_width=40)

        for shot_key, shot_data in sorted(shots.items()):
            task_id = shot_data.get("task_id", "N/A")
            shot_status = shot_data.get("status", "unknown")
            local_path = shot_data.get("local_path", "")
            error = shot_data.get("error", "")

            if shot_data.get("completed"):
                status_str = "[green]DONE[/green]"
            elif shot_status == "failed":
                status_str = f"[red]FAILED[/red]"
            elif shot_status == "submitted":
                status_str = "[yellow]SUBMITTED[/yellow]"
            else:
                status_str = f"[dim]{shot_status.upper()}[/dim]"

            display_path = local_path or (f"Error: {error}" if error else "")
            table.add_row(shot_key, str(task_id)[:20], status_str, display_path)

        console.print(table)
        console.print()

    # Summary
    total_elems = len(elements)
    done_elems = sum(1 for e in elements.values() if e.get("completed"))
    total_shots = len(shots)
    done_shots = sum(1 for s in shots.values() if s.get("completed"))

    console.print(f"[bold]Summary:[/bold]")
    console.print(f"  Elements: {done_elems}/{total_elems} completed")
    console.print(f"  Shots: {done_shots}/{total_shots} completed")


@cli.command("run-all")
@click.option("--scenario", "-s", required=True, help="Path to scenario YAML file")
@click.pass_context
def cmd_run_all(ctx: click.Context, scenario: str) -> None:
    """Run the full pipeline: elements -> shots -> download."""
    from pipeline.generate_elements import generate_elements
    from pipeline.generate_shots import generate_shots
    from pipeline.downloader import download_all

    config_path = ctx.obj["config"]

    try:
        # Step 1: Generate element reference images
        console.rule("[bold blue]Step 1: Generate Element Reference Images[/bold blue]")
        asyncio.run(generate_elements(scenario_path=scenario, config_path=config_path))

        # Step 2: Generate shot videos
        console.rule("[bold blue]Step 2: Generate Shot Videos[/bold blue]")
        asyncio.run(generate_shots(scenario_path=scenario, config_path=config_path))

        # Step 3: Download any remaining files
        console.rule("[bold blue]Step 3: Download Remaining Files[/bold blue]")
        asyncio.run(download_all(scenario_path=scenario, config_path=config_path))

        console.rule("[bold green]Pipeline Complete[/bold green]")

    except FileNotFoundError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        sys.exit(1)
    except ValueError as exc:
        console.print(f"[red]Configuration error: {exc}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Progress has been saved to status.json.[/yellow]")
        sys.exit(130)


def main() -> None:
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
