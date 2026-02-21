"""Auto-annotate clip text zones via Claude Vision API."""

from __future__ import annotations

import base64
import json
import logging
import subprocess
import tempfile
from pathlib import Path

import anthropic
import yaml

from src.models import ClipTextZone

logger = logging.getLogger(__name__)

_VISION_PROMPT = """\
This frame is from a short-form vertical video (1080x1920 pixels). \
I need to overlay white text on it. \
Analyze the frame and determine the best rectangular zone (x, y, width, height) in pixels \
where white text would be most readable and would NOT cover important visual subjects \
(faces, key objects, focal points).

Constraints:
- The zone must be fully inside the 1080x1920 frame
- Prefer areas with darker or uniform backgrounds
- Avoid placing text over faces, hands, or important objects
- The zone should be large enough for 1-3 lines of text (at least 600px wide, 200px tall)

Return ONLY a JSON object with integer values, no explanation:
{"x": ..., "y": ..., "w": ..., "h": ...}
"""


def _extract_middle_frame(clip_path: Path, output_path: Path, resolution: str = "1080x1920") -> None:
    """Extract a single frame from the middle of a clip, scaled to target resolution."""
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


def _call_vision(client: anthropic.Anthropic, image_path: Path) -> ClipTextZone:
    """Send a frame to Claude Vision and parse the returned zone."""
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    media_type = "image/png" if image_path.suffix == ".png" else "image/jpeg"

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data,
                    },
                },
                {"type": "text", "text": _VISION_PROMPT},
            ],
        }],
    )

    text = response.content[0].text.strip()
    # Extract JSON from response (may be wrapped in markdown code block)
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    data = json.loads(text)
    return ClipTextZone(
        x=int(data["x"]),
        y=int(data["y"]),
        w=int(data["w"]),
        h=int(data["h"]),
    )


def annotate_clips(
    clips_dir: Path,
    api_key: str,
    force: bool = False,
) -> dict[str, ClipTextZone]:
    """Annotate all clips in a directory and write clips.yaml."""
    yaml_path = clips_dir / "clips.yaml"

    existing: dict[str, dict] = {}
    if yaml_path.exists() and not force:
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        existing = raw.get("clips") or {}

    clip_files = sorted(clips_dir.glob("*.mp4"))
    if not clip_files:
        logger.warning("No .mp4 files found in %s", clips_dir)
        return {}

    client = anthropic.Anthropic(api_key=api_key)
    zones: dict[str, ClipTextZone] = {}

    with tempfile.TemporaryDirectory(prefix="annotate_") as tmpdir:
        tmp = Path(tmpdir)
        for clip in clip_files:
            stem = clip.stem
            if stem in existing and not force:
                vals = existing[stem]
                if vals:
                    zones[stem] = ClipTextZone(**vals)
                    logger.info("%s: skip (already annotated)", stem)
                    continue

            logger.info("%s: extracting frame...", stem)
            frame_path = tmp / f"{stem}.png"
            _extract_middle_frame(clip, frame_path)

            logger.info("%s: calling Claude Vision...", stem)
            try:
                zone = _call_vision(client, frame_path)
                zones[stem] = zone
                logger.info("%s: zone=(%d, %d, %d, %d)", stem, zone.x, zone.y, zone.w, zone.h)
            except Exception as exc:
                logger.error("%s: vision failed — %s", stem, exc)

    # Write clips.yaml
    defaults = {"x": 40, "y": 400, "w": 1000, "h": 1100}
    clips_data: dict[str, dict] = {}
    for stem, zone in sorted(zones.items()):
        clips_data[stem] = {"x": zone.x, "y": zone.y, "w": zone.w, "h": zone.h}

    output = {"defaults": defaults, "clips": clips_data}
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False)

    logger.info("Wrote %d zones to %s", len(zones), yaml_path)
    return zones
