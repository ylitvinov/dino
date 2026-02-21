"""Generate preview images with text zones drawn on clip frames."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from src.clips import load_clip_zones
from src.models import ClipTextZone

logger = logging.getLogger(__name__)

_DEFAULTS = ClipTextZone(x=40, y=400, w=1000, h=1100)


def _extract_middle_frame(clip_path: Path, output_path: Path, resolution: str = "1080x1920") -> None:
    w, h = resolution.split("x")
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(clip_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        duration = 3.0

    midpoint = duration / 2
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{midpoint:.3f}",
        "-i", str(clip_path),
        "-vframes", "1",
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Frame extraction failed for {clip_path.name}: {result.stderr[-300:]}")


def generate_previews(clips_dir: Path, open_folder: bool = False) -> Path:
    """Draw text zones on clip frames and save to clips/previews/."""
    zones = load_clip_zones(clips_dir)
    previews_dir = clips_dir / "previews"
    previews_dir.mkdir(exist_ok=True)

    clip_files = sorted(clips_dir.glob("*.mp4"))
    if not clip_files:
        logger.warning("No .mp4 files in %s", clips_dir)
        return previews_dir

    with tempfile.TemporaryDirectory(prefix="preview_") as tmpdir:
        tmp = Path(tmpdir)
        for clip in clip_files:
            stem = clip.stem
            zone = zones.get(stem, _DEFAULTS)

            frame_path = tmp / f"{stem}.png"
            _extract_middle_frame(clip, frame_path)

            preview_path = previews_dir / f"{stem}.png"

            # Draw semi-transparent green rectangle using ffmpeg drawbox
            x2 = zone.x + zone.w
            y2 = zone.y + zone.h
            cmd = [
                "ffmpeg", "-y",
                "-i", str(frame_path),
                "-vf", (
                    f"drawbox=x={zone.x}:y={zone.y}"
                    f":w={zone.w}:h={zone.h}"
                    f":color=green@0.3:t=fill,"
                    f"drawbox=x={zone.x}:y={zone.y}"
                    f":w={zone.w}:h={zone.h}"
                    f":color=green:t=3"
                ),
                str(preview_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("%s: drawbox failed — %s", stem, result.stderr[-200:])
                continue

            logger.info("%s: preview saved -> %s", stem, preview_path)

    if open_folder:
        subprocess.run(["open", str(previews_dir)])

    logger.info("Previews saved to %s", previews_dir)
    return previews_dir
