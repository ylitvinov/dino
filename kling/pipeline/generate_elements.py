"""Element reference image generation.

Generates reference images for each element defined in the scenario
using the KIE.ai Kling 3.0 image generation API. These reference images
are then used as kling_elements when generating video shots.
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
from pipeline.models import Element
from pipeline.scenario_parser import load_scenario

logger = logging.getLogger(__name__)
console = Console()

# Default reference prompts per element type
_CHARACTER_VIEWS = [
    "front view, full body, standing pose, white background",
    "side view (profile), full body, standing pose, white background",
    "three-quarter view, full body, standing pose, white background",
    "full body action pose, dynamic angle, white background",
]

_BACKGROUND_VIEWS = [
    "wide establishing shot, panoramic view",
    "medium shot, eye-level perspective",
    "detail close-up of key features",
]


def _get_reference_prompts(element_data: dict) -> list[str]:
    """Build reference prompts for an element.

    If the scenario defines explicit reference_prompts, use those.
    Otherwise, generate default prompts based on element type.
    """
    explicit = element_data.get("reference_prompts", [])
    if explicit:
        return explicit

    elem_type = element_data.get("type", "character")
    description = element_data.get("description", "")

    if elem_type == "background":
        return [f"{description}, {view}" for view in _BACKGROUND_VIEWS]
    else:
        return [f"{description}, {view}" for view in _CHARACTER_VIEWS]


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


async def generate_elements(
    scenario_path: str,
    config_path: str | None = None,
) -> None:
    """Generate reference images for all elements in the scenario.

    For each element:
    - Characters get 4 reference images (front, side, 3/4, full body)
    - Backgrounds get 2-3 reference images
    - Images are downloaded to output/elements/{name}/
    - CDN URLs are saved to status.json for reuse in video generation
    - Already-completed elements are skipped (resume support)

    Args:
        scenario_path: Path to the scenario YAML file.
        config_path: Optional override for config.yaml path.
    """
    config = load_config(config_path)
    api_key = get_api_key(config_path)

    scenario_raw = _load_scenario_raw(scenario_path)
    scenario = load_scenario(scenario_path)

    paths = resolve_output_paths(config, scenario_path)
    elements_dir = paths["elements_dir"]
    status_path = paths["elements_status_file"]
    poll_interval = config["polling"]["interval_seconds"]
    max_wait = config["polling"]["max_wait_seconds"]
    aspect_ratio = config["generation"]["aspect_ratio"]
    negative_prompt = scenario.global_config.get("negative_prompt", "")
    style_prefix = scenario.global_config.get("style_prefix", "")

    status = _load_status(status_path)
    if "elements" not in status:
        status["elements"] = {}

    async with KieClient(api_key=api_key, base_url=config["api"]["base_url"]) as client:
        total_images = 0
        tasks_to_submit: list[tuple[str, str, int]] = []  # (element_name, prompt, view_index)

        # Flatten grouped elements (characters/backgrounds) into a flat dict
        raw_elements = scenario_raw.get("elements", {})
        flat_elements: dict[str, dict] = {}
        for key, value in raw_elements.items():
            if isinstance(value, list):
                for elem_data in value:
                    name = elem_data.get("name", key)
                    flat_elements[name] = elem_data
            elif isinstance(value, dict):
                flat_elements[key] = value

        # Collect all images that need generation
        for elem_name, elem_data_raw in flat_elements.items():
            # Skip if folder exists and has images
            elem_dir = elements_dir / elem_name
            if elem_dir.is_dir() and any(elem_dir.glob("*.png")):
                console.print(f"  [dim]Skipping {elem_name} (images found in {elem_dir})[/dim]")
                continue

            prompts = _get_reference_prompts(elem_data_raw)

            for i, prompt in enumerate(prompts):
                full_prompt = f"{style_prefix} {prompt}".strip() if style_prefix else prompt
                tasks_to_submit.append((elem_name, full_prompt, i))
                total_images += 1

        if not tasks_to_submit:
            console.print("[green]All elements already generated.[/green]")
            return

        console.print(f"\n[bold]Generating {total_images} reference images "
                       f"for {len(scenario.elements)} elements...[/bold]\n")

        # Submit all image generation tasks
        submitted: list[tuple[str, int, str]] = []  # (element_name, view_index, task_id)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            submit_task = progress.add_task("Submitting image tasks...", total=total_images)

            for elem_name, prompt, view_idx in tasks_to_submit:
                try:
                    task_id = await client.create_image_task(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        aspect_ratio=aspect_ratio,
                    )
                    submitted.append((elem_name, view_idx, task_id))

                    # Track in status
                    if elem_name not in status["elements"]:
                        status["elements"][elem_name] = {"views": {}, "completed": False}
                    view_key = f"view_{view_idx}"
                    status["elements"][elem_name]["views"][view_key] = {
                        "task_id": task_id,
                        "status": "submitted",
                        "url": None,
                        "local_path": None,
                        "prompt": prompt,
                    }
                    _save_status(status_path, status)

                    progress.update(submit_task, advance=1)

                    # Small delay to avoid hitting rate limits
                    await asyncio.sleep(0.5)

                except KieApiError as exc:
                    console.print(f"[red]Failed to submit task for {elem_name} view {view_idx}: {exc}[/red]")

            # Poll all submitted tasks
            progress.update(submit_task, description="Waiting for image generation...")
            poll_task = progress.add_task("Polling tasks...", total=len(submitted))

            for elem_name, view_idx, task_id in submitted:
                view_key = f"view_{view_idx}"
                try:
                    result = await client.wait_for_task(
                        task_id,
                        poll_interval=poll_interval,
                        max_wait=max_wait,
                    )

                    if result.is_success and result.output_url:
                        # Download the image locally
                        elem_dir = elements_dir / elem_name
                        file_name = f"{elem_name}{view_idx + 1}.png"
                        local_path = elem_dir / file_name
                        await client.download_file(result.output_url, local_path)

                        # Store CDN URL for later use in video generation
                        status["elements"][elem_name]["views"][view_key].update({
                            "status": "completed",
                            "url": result.output_url,
                            "local_path": str(local_path),
                        })
                        console.print(f"  [green]{elem_name}/{view_key} completed[/green]")
                    else:
                        error_msg = result.error or "Unknown error"
                        status["elements"][elem_name]["views"][view_key].update({
                            "status": "failed",
                            "error": error_msg,
                        })
                        console.print(f"  [red]{elem_name}/{view_key} failed: {error_msg}[/red]")

                except KieApiError as exc:
                    status["elements"][elem_name]["views"][view_key].update({
                        "status": "failed",
                        "error": str(exc),
                    })
                    console.print(f"  [red]{elem_name}/{view_key} error: {exc}[/red]")

                _save_status(status_path, status)
                progress.update(poll_task, advance=1)

        # Mark fully completed elements
        for elem_name in status["elements"]:
            views = status["elements"][elem_name].get("views", {})
            all_done = all(v.get("status") == "completed" for v in views.values())
            if all_done and views:
                status["elements"][elem_name]["completed"] = True

        _save_status(status_path, status)

        # Summary
        completed_count = sum(
            1 for e in status["elements"].values() if e.get("completed")
        )
        console.print(
            f"\n[bold green]Element generation complete: "
            f"{completed_count}/{len(scenario.elements)} elements fully generated.[/bold green]"
        )


def _load_scenario_raw(path: str) -> dict:
    """Load raw YAML data (not parsed into models) for reference_prompts access."""
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
