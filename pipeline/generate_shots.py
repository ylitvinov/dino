"""Shot video generation.

Generates videos for each shot defined in the scenario, using element
reference images from the element generation step as kling_elements.
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


def _collect_element_urls(
    element_name: str,
    status: dict,
) -> list[str]:
    """Collect CDN URLs for a given element from the status file.

    Returns a list of image URLs that were generated during the
    element generation step. These are used as kling_element input URLs.
    """
    elem_status = status.get("elements", {}).get(element_name, {})
    views = elem_status.get("views", {})
    urls = []
    for view_key in sorted(views.keys()):
        view = views[view_key]
        url = view.get("url")
        if url and view.get("status") == "completed":
            urls.append(url)
    return urls


def _build_shot_prompt(
    shot_prompt: str,
    style_prefix: str,
    scene_background: str,
    scene_lighting: str,
) -> str:
    """Build the full prompt for a shot by combining components.

    Combines:
    - Style prefix (global visual style)
    - Scene continuity (background + lighting)
    - Shot-specific prompt
    """
    parts = []
    if style_prefix:
        parts.append(style_prefix)
    continuity = []
    if scene_background:
        continuity.append(f"Setting: {scene_background}")
    if scene_lighting:
        continuity.append(f"Lighting: {scene_lighting}")
    if continuity:
        parts.append(". ".join(continuity))
    parts.append(shot_prompt)
    return ". ".join(parts)


def _shot_key(scene_id: str, shot_id: str) -> str:
    """Create a unique key for a shot in the status dict."""
    return f"{scene_id}__{shot_id}"


async def generate_shots(
    scenario_path: str,
    config_path: str | None = None,
) -> None:
    """Generate videos for all shots defined in the scenario.

    For each shot:
    1. Build the full prompt (style_prefix + continuity + shot prompt)
    2. Collect element image CDN URLs from previous element generation
    3. Submit video generation task with kling_elements
    4. Track task_id in status.json
    5. Poll all tasks and download completed videos
    6. Resume support: skip shots that already have completed videos

    Args:
        scenario_path: Path to the scenario YAML file.
        config_path: Optional override for config.yaml path.
    """
    config = load_config(config_path)
    api_key = get_api_key(config_path)
    scenario = load_scenario(scenario_path)

    paths = resolve_output_paths(config, scenario_path)
    shots_dir = paths["shots_dir"]
    status_path = paths["status_file"]
    elements_status_path = paths["elements_status_file"]
    poll_interval = config["polling"]["interval_seconds"]
    max_wait = config["polling"]["max_wait_seconds"]
    mode = config["generation"]["mode"]
    aspect_ratio = config["generation"]["aspect_ratio"]
    cfg_scale = config["generation"].get("cfg_scale", 0.5)
    global_negative = scenario.global_config.get("negative_prompt", "")
    style_prefix = scenario.global_config.get("style_prefix", "")

    status = _load_status(status_path)
    if "shots" not in status:
        status["shots"] = {}

    # Read element URLs from shared elements status
    elements_status = _load_status(elements_status_path)
    elem_status = elements_status.get("elements", {})
    if not elem_status:
        console.print(
            "[yellow]Warning: No element images found in status.json. "
            "Run 'generate-elements' first for best results.[/yellow]"
        )

    # Collect shots to generate
    shots_to_generate: list[tuple[str, str, str, list[Element], int, str]] = []
    # (scene_id, shot_id, full_prompt, elements, duration, negative_prompt)

    total_shots = 0
    for scene in scenario.scenes:
        for shot in scene.shots:
            total_shots += 1
            skey = _shot_key(scene.id, shot.shot_id)
            shot_status = status["shots"].get(skey, {})

            if shot_status.get("completed", False):
                console.print(f"  [dim]Skipping {skey} (already completed)[/dim]")
                continue

            # Build full prompt
            full_prompt = _build_shot_prompt(
                shot_prompt=shot.prompt,
                style_prefix=style_prefix,
                scene_background=scene.background,
                scene_lighting=scene.lighting,
            )

            # Collect elements for this shot
            shot_elements: list[Element] = []
            for elem_name in shot.elements_needed:
                urls = _collect_element_urls(elem_name, elements_status)
                elem_def = scenario.elements.get(elem_name)
                if elem_def:
                    shot_elements.append(Element(
                        name=elem_def.name,
                        description=elem_def.description,
                        image_urls=urls,
                    ))
                elif urls:
                    shot_elements.append(Element(
                        name=elem_name,
                        description=elem_name,
                        image_urls=urls,
                    ))

            negative = shot.negative_prompt or global_negative

            shots_to_generate.append((
                scene.id, shot.shot_id, full_prompt,
                shot_elements, shot.duration, negative,
            ))

    if not shots_to_generate:
        console.print("[green]All shots already generated.[/green]")
        return

    console.print(
        f"\n[bold]Generating {len(shots_to_generate)} of {total_shots} "
        f"video shots...[/bold]\n"
    )

    async with KieClient(api_key=api_key, base_url=config["api"]["base_url"]) as client:
        # Phase 1: Submit all video tasks
        submitted: list[tuple[str, str]] = []  # (shot_key, task_id)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            submit_task = progress.add_task(
                "Submitting video tasks...", total=len(shots_to_generate)
            )

            for scene_id, shot_id, full_prompt, elements, duration, negative in shots_to_generate:
                skey = _shot_key(scene_id, shot_id)
                try:
                    task_id = await client.create_video_task(
                        prompt=full_prompt,
                        negative_prompt=negative,
                        elements=elements if elements else None,
                        duration=duration,
                        mode=mode,
                        aspect_ratio=aspect_ratio,
                        cfg_scale=cfg_scale,
                    )
                    submitted.append((skey, task_id))

                    status["shots"][skey] = {
                        "task_id": task_id,
                        "status": "submitted",
                        "completed": False,
                        "url": None,
                        "local_path": None,
                        "prompt": full_prompt,
                        "elements": [e.name for e in elements],
                    }
                    _save_status(status_path, status)

                    progress.update(submit_task, advance=1)
                    console.print(f"  [blue]Submitted {skey} -> {task_id}[/blue]")

                    # Small delay to avoid rate limits
                    await asyncio.sleep(0.5)

                except KieApiError as exc:
                    console.print(f"  [red]Failed to submit {skey}: {exc}[/red]")
                    status["shots"][skey] = {
                        "status": "submit_failed",
                        "completed": False,
                        "error": str(exc),
                    }
                    _save_status(status_path, status)

            # Phase 2: Poll all submitted tasks
            poll_task_bar = progress.add_task(
                "Waiting for video generation...", total=len(submitted)
            )

            for skey, task_id in submitted:
                try:
                    result = await client.wait_for_task(
                        task_id,
                        poll_interval=poll_interval,
                        max_wait=max_wait,
                    )

                    if result.is_success and result.output_url:
                        # Download the video
                        local_path = shots_dir / f"{skey}.mp4"
                        await client.download_file(result.output_url, local_path)

                        status["shots"][skey].update({
                            "status": "completed",
                            "completed": True,
                            "url": result.output_url,
                            "local_path": str(local_path),
                        })
                        console.print(f"  [green]{skey} completed -> {local_path}[/green]")
                    else:
                        error_msg = result.error or "Unknown error"
                        status["shots"][skey].update({
                            "status": "failed",
                            "completed": False,
                            "error": error_msg,
                        })
                        console.print(f"  [red]{skey} failed: {error_msg}[/red]")

                except KieApiError as exc:
                    status["shots"][skey].update({
                        "status": "failed",
                        "completed": False,
                        "error": str(exc),
                    })
                    console.print(f"  [red]{skey} error: {exc}[/red]")

                _save_status(status_path, status)
                progress.update(poll_task_bar, advance=1)

    # Summary
    completed = sum(1 for s in status["shots"].values() if s.get("completed"))
    console.print(
        f"\n[bold green]Shot generation complete: "
        f"{completed}/{total_shots} shots generated.[/bold green]"
    )
