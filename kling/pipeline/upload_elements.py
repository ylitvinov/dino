"""Upload local element images to KIE.ai file storage.

Uploads existing reference images from output/elements/{Name}/ to KIE.ai's
file upload API and saves the returned URLs to elements_status.json for use
in video generation requests.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from pipeline.auth import get_api_key, load_config, resolve_output_paths
from pipeline.client import KieClient, KieApiError
from pipeline.scenario_parser import load_scenario

logger = logging.getLogger(__name__)
console = Console()


def _load_status(status_path: Path) -> dict:
    if status_path.exists():
        with open(status_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_status(status_path: Path, status: dict) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)


async def upload_elements(
    scenario_path: str,
    config_path: str | None = None,
) -> None:
    """Upload local element images to KIE.ai and save URLs to status.

    For each element defined in the scenario, finds local PNG files in
    output/elements/{Name}/ and uploads them via the KIE file-stream-upload
    API. Saves returned URLs to elements_status.json.

    Skips elements that already have URLs in the status file.

    Args:
        scenario_path: Path to the scenario YAML file.
        config_path: Optional override for config.yaml path.
    """
    config = load_config(config_path)
    api_key = get_api_key(config_path)
    scenario = load_scenario(scenario_path)

    paths = resolve_output_paths(config, scenario_path)
    elements_dir = paths["elements_dir"]
    status_path = paths["elements_status_file"]

    status = _load_status(status_path)
    if "elements" not in status:
        status["elements"] = {}

    # Collect images to upload per element
    to_upload: list[tuple[str, list[Path]]] = []  # (element_name, [image_paths])

    for elem_name in scenario.elements:
        # Skip if already has URLs
        elem_status = status.get("elements", {}).get(elem_name, {})
        views = elem_status.get("views", {})
        has_urls = views and all(
            v.get("url") and v.get("status") == "completed"
            for v in views.values()
        )
        if has_urls:
            console.print(f"  [dim]Skipping {elem_name} (URLs already in status)[/dim]")
            continue

        elem_dir = elements_dir / elem_name
        if not elem_dir.is_dir():
            console.print(f"  [yellow]Warning: No directory for {elem_name} at {elem_dir}[/yellow]")
            continue

        images = sorted(elem_dir.glob("*.png"))
        if not images:
            console.print(f"  [yellow]Warning: No PNG files for {elem_name} in {elem_dir}[/yellow]")
            continue

        to_upload.append((elem_name, images))

    if not to_upload:
        console.print("[green]All elements already uploaded.[/green]")
        return

    total_files = sum(len(imgs) for _, imgs in to_upload)
    console.print(
        f"\n[bold]Uploading {total_files} images "
        f"for {len(to_upload)} element(s)...[/bold]\n"
    )

    async with KieClient(api_key=api_key, base_url=config["api"]["base_url"]) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            upload_bar = progress.add_task("Uploading images...", total=total_files)

            for elem_name, images in to_upload:
                if elem_name not in status["elements"]:
                    status["elements"][elem_name] = {"views": {}, "completed": False}

                for i, img_path in enumerate(images):
                    view_key = f"view_{i}"
                    try:
                        file_url = await client.upload_file(img_path)

                        status["elements"][elem_name]["views"][view_key] = {
                            "status": "completed",
                            "url": file_url,
                            "local_path": str(img_path),
                        }
                        console.print(f"  [green]{elem_name}/{view_key} -> {file_url}[/green]")

                    except KieApiError as exc:
                        _save_status(status_path, status)
                        raise RuntimeError(
                            f"Upload failed for {elem_name}/{view_key}: {exc}"
                        ) from exc

                    _save_status(status_path, status)
                    progress.update(upload_bar, advance=1)

                    await asyncio.sleep(0.3)

        # Mark fully completed elements
        for elem_name in status["elements"]:
            views = status["elements"][elem_name].get("views", {})
            all_done = all(v.get("status") == "completed" for v in views.values())
            if all_done and views:
                status["elements"][elem_name]["completed"] = True

        _save_status(status_path, status)

        completed_count = sum(
            1 for e in status["elements"].values() if e.get("completed")
        )
        console.print(
            f"\n[bold green]Upload complete: "
            f"{completed_count}/{len(scenario.elements)} elements ready.[/bold green]"
        )
