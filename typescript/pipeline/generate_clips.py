"""Clip library generator: image -> Kling 3.0 -> 6-sec video clips.

For each image in images/, uploads it to KIE.ai, creates an image-to-video
task, polls for completion, and downloads the result to output/clips/.
Resumable via clips_status.json.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from pipeline.config import load_config, get_clips_dir, get_clips_status_path, get_images_dir
from pipeline.kie_client import KieClient, KieApiError

logger = logging.getLogger(__name__)
console = Console()

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _load_status(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"clips": {}}


def _save_status(path: Path, status: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)


async def generate_clips(config_path: str | None = None) -> None:
    """Generate video clips from all images in the images directory.

    Args:
        config_path: Path to config.yaml.
    """
    config = load_config(config_path)
    kling_config = config["kling"]
    clips_config = config["clips"]

    api_key = kling_config["api_key"]
    if not api_key:
        raise ValueError("kling.api_key is not set in config.yaml")

    images_dir = get_images_dir(config, config_path)
    clips_dir = get_clips_dir(config, config_path)
    status_path = get_clips_status_path(config, config_path)

    clips_dir.mkdir(parents=True, exist_ok=True)

    # Find all images
    images = sorted(
        p for p in images_dir.iterdir()
        if p.suffix.lower() in _IMAGE_EXTENSIONS
    )
    if not images:
        console.print(f"[yellow]No images found in {images_dir}[/yellow]")
        return

    status = _load_status(status_path)
    clips = status.setdefault("clips", {})

    poll_interval = kling_config.get("poll_interval", 10)
    max_wait = kling_config.get("max_wait", 300)
    mode = kling_config.get("mode", "pro")
    duration = clips_config.get("duration", 6)
    aspect_ratio = clips_config.get("aspect_ratio", "9:16")
    prompt_suffix = clips_config.get("prompt_suffix", "")

    # Filter to images that still need processing
    to_process = []
    for img in images:
        name = img.stem
        existing = clips.get(name, {})
        if existing.get("status") == "completed":
            console.print(f"  [dim]Skipping {name} (already completed)[/dim]")
            continue
        to_process.append(img)

    if not to_process:
        console.print("[green]All clips already generated.[/green]")
        return

    console.print(f"\n[bold]Processing {len(to_process)} image(s)...[/bold]\n")

    async with KieClient(
        api_key=api_key,
        base_url=kling_config.get("base_url", "https://api.kie.ai"),
    ) as client:
        # Phase 1: Upload & submit tasks
        submitted: list[tuple[str, str, Path]] = []  # (name, task_id, img_path)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            bar = progress.add_task("Submitting clips...", total=len(to_process))

            for img in to_process:
                name = img.stem
                existing = clips.get(name, {})

                # Resume: reuse existing task_id
                if existing.get("task_id") and existing.get("status") in ("submitted", "processing"):
                    submitted.append((name, existing["task_id"], img))
                    progress.update(bar, advance=1)
                    console.print(f"  [cyan]{name}: resuming (task {existing['task_id']})[/cyan]")
                    continue

                try:
                    # Upload image
                    image_url = await client.upload_file(img)

                    # Create task
                    task_id = await client.create_image_to_video_task(
                        image_url=image_url,
                        prompt=prompt_suffix,
                        duration=duration,
                        mode=mode,
                        aspect_ratio=aspect_ratio,
                    )

                    submitted.append((name, task_id, img))
                    clips[name] = {
                        "task_id": task_id,
                        "status": "submitted",
                        "image": str(img),
                        "image_url": image_url,
                        "clip_path": None,
                        "error": None,
                    }
                    _save_status(status_path, status)
                    progress.update(bar, advance=1)
                    console.print(f"  [blue]{name}: submitted -> {task_id}[/blue]")

                    await asyncio.sleep(0.5)

                except KieApiError as exc:
                    console.print(f"  [red]{name}: failed to submit — {exc}[/red]")
                    clips[name] = {
                        "status": "failed",
                        "error": str(exc),
                        "image": str(img),
                    }
                    _save_status(status_path, status)
                    progress.update(bar, advance=1)

        # Phase 2: Poll for results
        if not submitted:
            return

        console.print(f"\n[bold]Checking status of {len(submitted)} task(s)...[/bold]\n")

        for name, task_id, img in submitted:
            try:
                result = await client.get_task_status(task_id)

                if result.is_success and result.output_url:
                    console.print(f"  [cyan]{name}: ready, downloading...[/cyan]")
                    clip_path = clips_dir / f"{name}.mp4"
                    await client.download_file(result.output_url, clip_path)

                    clips[name].update({
                        "status": "completed",
                        "clip_path": str(clip_path),
                        "url": result.output_url,
                    })
                    console.print(f"  [green]{name}: saved -> {clip_path}[/green]")

                elif result.is_done:
                    error_msg = result.error or "Unknown error"
                    clips[name].update({
                        "status": "failed",
                        "error": error_msg,
                    })
                    console.print(f"  [red]{name}: failed — {error_msg}[/red]")

                else:
                    clips[name]["status"] = "processing"
                    console.print(f"  [yellow]{name}: still {result.status}, re-run later[/yellow]")

            except KieApiError as exc:
                clips[name].update({
                    "status": "failed",
                    "error": str(exc),
                })
                console.print(f"  [red]{name}: API error — {exc}[/red]")

            _save_status(status_path, status)

    # Summary
    completed = sum(1 for c in clips.values() if c.get("status") == "completed")
    total = len(clips)
    console.print(f"\n[bold]Clips: {completed}/{total} completed[/bold]")
