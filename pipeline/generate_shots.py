"""Shot video generation using multi-shot API.

Generates videos for each scene defined in the scenario as a single
multi-shot request per scene, leveraging Kling 3.0's visual continuity.
Falls back to chunking if a scene exceeds 6 shots or 15s total.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from pipeline.auth import get_api_key, load_config, resolve_output_paths
from pipeline.client import KieClient, KieApiError, DryRunInterrupt
from pipeline.models import Element
from pipeline.scenario_parser import load_scenario

logger = logging.getLogger(__name__)
console = Console()

_MAX_SHOTS_PER_REQUEST = 6
_MAX_DURATION_PER_REQUEST = 15


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
    """Collect CDN URLs for a given element from the status file."""
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
    """Build the full prompt for a shot by combining components."""
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


@dataclass
class SceneTask:
    """A scene to submit as a multi-shot request (or chunked into parts)."""
    scene_id: str
    part: int  # 0-based chunk index (0 if no chunking needed)
    shots: list[dict] = field(default_factory=list)  # [{"prompt": str, "duration": int}]
    elements: list[Element] = field(default_factory=list)
    negative_prompt: str = ""


def _chunk_scene_shots(
    scene_id: str,
    shots: list[dict],
    elements: list[Element],
    negative_prompt: str,
) -> list[SceneTask]:
    """Split scene shots into chunks that fit multi-shot limits."""
    chunks: list[SceneTask] = []
    current_shots: list[dict] = []
    current_duration = 0
    part = 0

    for shot in shots:
        dur = shot["duration"]
        if current_shots and (
            len(current_shots) >= _MAX_SHOTS_PER_REQUEST
            or current_duration + dur > _MAX_DURATION_PER_REQUEST
        ):
            chunks.append(SceneTask(
                scene_id=scene_id,
                part=part,
                shots=current_shots,
                elements=list(elements),
                negative_prompt=negative_prompt,
            ))
            part += 1
            current_shots = []
            current_duration = 0
        current_shots.append(shot)
        current_duration += dur

    if current_shots:
        chunks.append(SceneTask(
            scene_id=scene_id,
            part=part,
            shots=current_shots,
            elements=list(elements),
            negative_prompt=negative_prompt,
        ))

    return chunks


def _scene_status_key(scene_id: str, part: int, total_parts: int) -> str:
    """Build the key used in status['scenes']."""
    if total_parts <= 1:
        return scene_id
    return f"{scene_id}_part{part}"


def _scene_filename(scene_id: str, part: int, total_parts: int) -> str:
    """Build the output filename for a scene chunk."""
    if total_parts <= 1:
        return f"scene_{scene_id}.mp4"
    return f"scene_{scene_id}_part{part}.mp4"


async def generate_shots(
    scenario_path: str,
    config_path: str | None = None,
    scene_ids: list[int] | None = None,
    dry_run: bool = False,
) -> None:
    """Generate videos for scenes using multi-shot API.

    Groups all shots in a scene into a single multi-shot request (or
    chunked parts if the scene exceeds 6 shots / 15s). One combined
    video per scene/chunk.

    Args:
        scenario_path: Path to the scenario YAML file.
        config_path: Optional override for config.yaml path.
        scene_ids: Optional list of scene IDs to generate (all if None).
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
    if "scenes" not in status:
        status["scenes"] = {}

    # Read element URLs from shared elements status
    elements_status = _load_status(elements_status_path)
    elem_status = elements_status.get("elements", {})
    if not elem_status:
        console.print(
            "[yellow]Warning: No element images found in status.json. "
            "Run 'generate-elements' first for best results.[/yellow]"
        )

    # Build scene tasks
    scene_tasks: list[SceneTask] = []
    total_scenes = 0

    for scene in scenario.scenes:
        if scene_ids is not None and int(scene.id) not in scene_ids:
            continue
        total_scenes += 1

        # Check if ALL shots in this scene are already completed
        # For chunked scenes, check all parts
        existing_keys = [k for k in status["scenes"] if k == scene.id or k.startswith(f"{scene.id}_part")]
        all_completed = existing_keys and all(
            status["scenes"].get(k, {}).get("completed", False)
            for k in existing_keys
        )
        if all_completed:
            console.print(f"  [dim]Skipping scene {scene.id} (already completed)[/dim]")
            continue

        # Build per-shot data
        shot_dicts: list[dict] = []
        scene_elements_map: dict[str, Element] = {}  # deduplicated

        for shot in scene.shots:
            full_prompt = _build_shot_prompt(
                shot_prompt=shot.prompt,
                style_prefix=style_prefix,
                scene_background=scene.background,
                scene_lighting=scene.lighting,
            )

            # Collect elements for this shot
            for elem_name in shot.elements_needed:
                if elem_name in scene_elements_map:
                    continue
                urls = _collect_element_urls(elem_name, elements_status)
                elem_def = scenario.elements.get(elem_name)
                if elem_def:
                    scene_elements_map[elem_name] = Element(
                        name=elem_def.name,
                        description=elem_def.description,
                        image_urls=urls,
                    )
                elif urls:
                    scene_elements_map[elem_name] = Element(
                        name=elem_name,
                        description=elem_name,
                        image_urls=urls,
                    )

            # Strip @ElementName for elements without images
            for ename, elem in scene_elements_map.items():
                if not elem.image_urls:
                    full_prompt = full_prompt.replace(f"@{ename}", ename)

            shot_dicts.append({
                "prompt": full_prompt,
                "duration": shot.duration,
            })

        # Only keep elements that have images
        scene_elements = [e for e in scene_elements_map.values() if e.image_urls]
        negative = global_negative
        # Use first shot's negative if set (scene-level override)
        for shot in scene.shots:
            if shot.negative_prompt:
                negative = shot.negative_prompt
                break

        # Chunk if needed
        chunks = _chunk_scene_shots(scene.id, shot_dicts, scene_elements, negative)
        scene_tasks.extend(chunks)

    if not scene_tasks:
        console.print("[green]All scenes already generated.[/green]")
        return

    console.print(
        f"\n[bold]{'[DRY RUN] Would generate' if dry_run else 'Generating'} "
        f"{len(scene_tasks)} multi-shot task(s) "
        f"for {total_scenes} scene(s)...[/bold]\n"
    )

    async with KieClient(api_key=api_key, base_url=config["api"]["base_url"], dry_run=dry_run) as client:
        # Phase 1: Submit multi-shot tasks
        submitted: list[tuple[str, str, str]] = []  # (status_key, task_id, filename)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            submit_bar = progress.add_task(
                "Submitting multi-shot tasks...", total=len(scene_tasks)
            )

            for stask in scene_tasks:
                # Figure out total parts for this scene
                total_parts = sum(1 for t in scene_tasks if t.scene_id == stask.scene_id)
                skey = _scene_status_key(stask.scene_id, stask.part, total_parts)
                fname = _scene_filename(stask.scene_id, stask.part, total_parts)

                try:
                    task_id = await client.create_multi_shot_task(
                        shots=stask.shots,
                        negative_prompt=stask.negative_prompt,
                        elements=stask.elements if stask.elements else None,
                        mode=mode,
                        aspect_ratio=aspect_ratio,
                        cfg_scale=cfg_scale,
                    )
                    submitted.append((skey, task_id, fname))

                    status["scenes"][skey] = {
                        "task_id": task_id,
                        "status": "submitted",
                        "completed": False,
                        "url": None,
                        "local_path": None,
                        "shot_count": len(stask.shots),
                        "elements": [e.name for e in stask.elements],
                    }
                    _save_status(status_path, status)

                    progress.update(submit_bar, advance=1)
                    console.print(
                        f"  [blue]Submitted scene {skey} ({len(stask.shots)} shots) -> {task_id}[/blue]"
                    )

                    await asyncio.sleep(0.5)

                except DryRunInterrupt:
                    progress.update(submit_bar, advance=1)
                    continue

                except (KieApiError, ValueError) as exc:
                    console.print(f"  [red]Failed to submit scene {skey}: {exc}[/red]")
                    status["scenes"][skey] = {
                        "status": "submit_failed",
                        "completed": False,
                        "error": str(exc),
                    }
                    _save_status(status_path, status)

            if dry_run:
                console.print("[bold yellow]Dry run complete. No API calls were made.[/bold yellow]")
                return

            # Phase 2: Poll all submitted tasks
            poll_bar = progress.add_task(
                "Waiting for video generation...", total=len(submitted)
            )

            for skey, task_id, fname in submitted:
                try:
                    result = await client.wait_for_task(
                        task_id,
                        poll_interval=poll_interval,
                        max_wait=max_wait,
                    )

                    if result.is_success and result.output_url:
                        local_path = shots_dir / fname
                        await client.download_file(result.output_url, local_path)

                        status["scenes"][skey].update({
                            "status": "completed",
                            "completed": True,
                            "url": result.output_url,
                            "local_path": str(local_path),
                        })
                        console.print(f"  [green]Scene {skey} completed -> {local_path}[/green]")
                    else:
                        error_msg = result.error or "Unknown error"
                        status["scenes"][skey].update({
                            "status": "failed",
                            "completed": False,
                            "error": error_msg,
                        })
                        console.print(f"  [red]Scene {skey} failed: {error_msg}[/red]")

                except KieApiError as exc:
                    status["scenes"][skey].update({
                        "status": "failed",
                        "completed": False,
                        "error": str(exc),
                    })
                    console.print(f"  [red]Scene {skey} error: {exc}[/red]")

                _save_status(status_path, status)
                progress.update(poll_bar, advance=1)

    # Summary
    completed = sum(1 for s in status["scenes"].values() if s.get("completed"))
    total = len(status["scenes"])
    console.print(
        f"\n[bold green]Scene generation complete: "
        f"{completed}/{total} scene task(s) generated.[/bold green]"
    )
