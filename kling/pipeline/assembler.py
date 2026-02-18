"""Assemble downloaded scene videos into a single final video using ffmpeg."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Regex to parse scene status keys like "1", "2_part0", "3_part1"
_KEY_RE = re.compile(r"^(\d+)(?:_part(\d+))?$")


def _sort_key(scene_key: str) -> tuple[int, int]:
    """Return (scene_id, part) for numeric sorting."""
    m = _KEY_RE.match(scene_key)
    if not m:
        # Fallback: push unrecognised keys to the end
        return (999999, 0)
    scene_id = int(m.group(1))
    part = int(m.group(2)) if m.group(2) is not None else 0
    return (scene_id, part)


def assemble_video(
    scenario_path: str,
    config_path: str = "config.yaml",
    output_path: str | None = None,
) -> Path:
    """Concatenate completed scene videos into one file.

    Returns the Path to the assembled video.
    """
    from pipeline.auth import load_config, resolve_output_paths

    # Check ffmpeg is available
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg not found on PATH. Install it (e.g. `brew install ffmpeg`) and retry."
        )

    config = load_config(config_path)
    paths = resolve_output_paths(config, scenario_path)

    status_file: Path = paths["status_file"]
    if not status_file.exists():
        raise FileNotFoundError(
            f"Status file not found: {status_file}. Run the pipeline first."
        )

    with open(status_file, "r", encoding="utf-8") as f:
        status = json.load(f)

    scenes: dict = status.get("scenes", {})
    if not scenes:
        raise ValueError("No scenes found in status. Nothing to assemble.")

    # Collect completed scenes with local files
    entries: list[tuple[str, str]] = []
    skipped: list[str] = []
    for key, data in scenes.items():
        if not data.get("completed"):
            skipped.append(key)
            continue
        local = data.get("local_path")
        if not local or not Path(local).exists():
            skipped.append(key)
            continue
        entries.append((key, local))

    if skipped:
        logger.warning("Skipping incomplete/missing scenes: %s", ", ".join(skipped))

    if not entries:
        raise ValueError("No completed scene videos found to assemble.")

    # Sort numerically
    entries.sort(key=lambda e: _sort_key(e[0]))

    logger.info(
        "Assembling %d scene file(s) in order: %s",
        len(entries),
        ", ".join(k for k, _ in entries),
    )

    # Determine output path
    scenario_dir = status_file.parent
    dest = Path(output_path) if output_path else scenario_dir / "final.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Write ffmpeg concat list to a temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, prefix="ffconcat_"
    ) as tmp:
        for _, filepath in entries:
            # ffmpeg concat demuxer needs lines like: file '/absolute/path.mp4'
            tmp.write(f"file '{filepath}'\n")
        concat_list = tmp.name

    try:
        cmd = [
            "ffmpeg",
            "-y",  # overwrite output
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            str(dest),
        ]
        logger.debug("Running: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed (exit {result.returncode}):\n{result.stderr}"
            )
    finally:
        Path(concat_list).unlink(missing_ok=True)

    logger.info("Assembled video saved to %s", dest)
    return dest
