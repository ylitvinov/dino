"""Scenario YAML parser.

Loads a scenario.yaml file and constructs the Scenario model
with all elements, scenes, and shots.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pipeline.models import Element, Scene, Scenario, Shot


def load_scenario(path: str | Path) -> Scenario:
    """Load a scenario from a YAML file.

    Expected YAML structure (mirrors KIE.ai API payload)::

        style_prefix: "3D animation style, Pixar quality, ..."
        negative_prompt: "blurry, distorted, ..."

        scenes:
          - id: 1
            background: "Sunny park"
            lighting: "Bright daylight"
            kling_elements: ["Topa", "Valley"]
            multi_prompt:
              - prompt: "Camera slowly pans across the park..."
                duration: 5
              - prompt: "Close-up of character..."
                duration: 5

    Args:
        path: Path to the scenario YAML file.

    Returns:
        A fully constructed Scenario object.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If required fields are missing.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Scenario file must be a YAML mapping, got {type(raw).__name__}")

    # -- Global config (top-level fields) --
    global_config = {
        "style_prefix": raw.get("style_prefix", ""),
    }

    # -- Elements (kling_elements at top level) --
    elements: dict[str, Element] = {}
    for elem_data in raw.get("kling_elements", []):
        if isinstance(elem_data, dict):
            name = elem_data.get("name", "")
            elements[name] = Element(
                name=name,
                description=elem_data.get("description", name),
            )
        elif isinstance(elem_data, str):
            elements[elem_data] = Element(name=elem_data, description=elem_data)

    # -- Scenes --
    scenes: list[Scene] = []
    for scene_data in raw.get("scenes", []):
        if not isinstance(scene_data, dict):
            raise ValueError(f"Each scene must be a mapping, got {type(scene_data).__name__}")

        scene_id = scene_data.get("id", "")
        if not scene_id:
            raise ValueError("Each scene must have an 'id' field")

        shots: list[Shot] = []
        for shot_data in scene_data.get("multi_prompt", []):
            if not isinstance(shot_data, dict):
                raise ValueError(f"Each shot must be a mapping in scene '{scene_id}'")

            shot = Shot(
                scene_id=scene_id,
                prompt=shot_data.get("prompt", ""),
                duration=int(shot_data.get("duration", 5)),
            )
            shots.append(shot)

        scene = Scene(
            id=scene_id,
            background=scene_data.get("background", ""),
            lighting=scene_data.get("lighting", ""),
            kling_elements=scene_data.get("kling_elements", []),
            shots=shots,
        )
        scenes.append(scene)

    return Scenario(
        global_config=global_config,
        elements=elements,
        scenes=scenes,
    )
