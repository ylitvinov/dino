"""Load clip text-zone markup from clips/clips.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.models import ClipTextZone

_DEFAULTS = ClipTextZone(x=40, y=400, w=1000, h=1100)


def load_clip_zones(clips_dir: Path) -> dict[str, ClipTextZone]:
    """Parse clips.yaml and return {clip_stem: ClipTextZone}."""
    yaml_path = clips_dir / "clips.yaml"
    if not yaml_path.exists():
        return {}

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    defaults_raw = data.get("defaults", {})
    defaults = ClipTextZone(
        x=defaults_raw.get("x", _DEFAULTS.x),
        y=defaults_raw.get("y", _DEFAULTS.y),
        w=defaults_raw.get("w", _DEFAULTS.w),
        h=defaults_raw.get("h", _DEFAULTS.h),
    )

    zones: dict[str, ClipTextZone] = {}
    for name, vals in (data.get("clips") or {}).items():
        if not vals:
            zones[name] = defaults
        else:
            zones[name] = ClipTextZone(
                x=vals.get("x", defaults.x),
                y=vals.get("y", defaults.y),
                w=vals.get("w", defaults.w),
                h=vals.get("h", defaults.h),
            )

    return zones


def get_zone_for_clip(
    zones: dict[str, ClipTextZone],
    clip_path: Path,
) -> ClipTextZone | None:
    """Return the text zone for a clip file, or None if no markup exists."""
    if not zones:
        return None
    stem = clip_path.stem
    return zones.get(stem)
