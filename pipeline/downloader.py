"""Standalone downloader for completed pipeline outputs.

Downloads any completed but not-yet-downloaded element images and shot
videos from their CDN URLs to local files.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from pipeline.auth import get_api_key, load_config, resolve_output_paths
from pipeline.client import KieClient

logger = logging.getLogger(__name__)
console = Console()


def _load_status(status_path: Path) -> dict:
    """Load pipeline status from JSON file."""
    if status_path.exists():
        with open(status_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_status(status_path: Path, status: dict) -> None:
    """Save pipeline status to JSON file."""
    status_path.parent.mkdir(parents=True, exist_ok=True)
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)


async def download_all(
    scenario_path: str | None = None,
    config_path: str | None = None,
) -> None:
    """Download all completed but not-yet-downloaded files.

    Scans status files for elements and shots that have a CDN URL
    but no local file (or the local file is missing), and downloads them.

    Args:
        scenario_path: Path to scenario YAML (used to derive per-scenario output dir).
        config_path: Optional override for config.yaml path.
    """
    config = load_config(config_path)
    api_key = get_api_key(config_path)

    paths = resolve_output_paths(config, scenario_path)
    elements_dir = paths["elements_dir"]
    elements_status_path = paths["elements_status_file"]
    shots_dir = paths["shots_dir"]
    shots_status_path = paths["status_file"]

    elements_status = _load_status(elements_status_path)
    shots_status = _load_status(shots_status_path)

    downloads: list[tuple[str, str, Path, Path, dict]] = []
    # (label, url, local_path, status_path, status_dict)

    # Check element images
    for elem_name, elem_data in elements_status.get("elements", {}).items():
        for view_key, view_data in elem_data.get("views", {}).items():
            url = view_data.get("url")
            if not url or view_data.get("status") != "completed":
                continue

            local = view_data.get("local_path")
            if local and Path(local).exists():
                continue

            local_path = elements_dir / elem_name / f"{view_key}.png"
            downloads.append((f"element:{elem_name}/{view_key}", url, local_path, elements_status_path, elements_status))

    # Check shot videos
    for shot_key, shot_data in shots_status.get("shots", {}).items():
        url = shot_data.get("url")
        if not url or not shot_data.get("completed"):
            continue

        local = shot_data.get("local_path")
        if local and Path(local).exists():
            continue

        local_path = shots_dir / f"{shot_key}.mp4"
        downloads.append((f"shot:{shot_key}", url, local_path, shots_status_path, shots_status))

    if not downloads:
        console.print("[green]All files are already downloaded.[/green]")
        return

    console.print(f"\n[bold]Downloading {len(downloads)} files...[/bold]\n")

    async with KieClient(api_key=api_key, base_url=config["api"]["base_url"]) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            dl_task = progress.add_task("Downloading...", total=len(downloads))

            for label, url, local_path, st_path, st_dict in downloads:
                try:
                    await client.download_file(url, local_path)
                    console.print(f"  [green]Downloaded {label} -> {local_path}[/green]")

                    # Update status with local path
                    _update_local_path(st_dict, label, str(local_path))
                    _save_status(st_path, st_dict)

                except Exception as exc:
                    console.print(f"  [red]Failed to download {label}: {exc}[/red]")

                progress.update(dl_task, advance=1)

    console.print(f"\n[bold green]Download complete.[/bold green]")


def _update_local_path(status: dict, label: str, local_path: str) -> None:
    """Update the local_path in the status dict for a given label."""
    if label.startswith("element:"):
        parts = label[len("element:"):].split("/")
        if len(parts) == 2:
            elem_name, view_key = parts
            status.setdefault("elements", {}).setdefault(elem_name, {}).setdefault("views", {}).setdefault(view_key, {})["local_path"] = local_path
    elif label.startswith("shot:"):
        shot_key = label[len("shot:"):]
        if shot_key in status.get("shots", {}):
            status["shots"][shot_key]["local_path"] = local_path
