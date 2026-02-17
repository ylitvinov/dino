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

    Expected YAML structure::

        global_config:
          style_prefix: "3D animation style, Pixar quality, ..."
          negative_prompt: "blurry, distorted, ..."

        elements:
          dino:
            description: "A cute green dinosaur with big eyes..."
            type: character
            reference_prompts:
              - "front view: A cute green dinosaur..."
              - "side view: A cute green dinosaur..."
          background_park:
            description: "A sunny park with green grass..."
            type: background
            reference_prompts:
              - "Wide establishing shot of a sunny park..."

        scenes:
          - id: scene_01
            title: "Opening"
            time: "00:00-00:15"
            background: "Sunny park with playground"
            lighting: "Bright daylight, soft shadows"
            shots:
              - shot_id: shot_01
                time: "00:00-00:05"
                prompt: "Camera slowly pans across the park..."
                elements_needed:
                  - dino
                duration: 5
                negative_prompt: ""

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

    # -- Global config --
    global_config = raw.get("global_config", {})

    # -- Elements --
    # Supports both flat format (elements: {Name: {...}})
    # and grouped format (elements: {characters: [...], backgrounds: [...]})
    elements: dict[str, Element] = {}
    raw_elements = raw.get("elements", {})
    if isinstance(raw_elements, dict):
        for key, value in raw_elements.items():
            if isinstance(value, list):
                # Grouped format: characters: [{name: "Topa", ...}, ...]
                for elem_data in value:
                    if not isinstance(elem_data, dict):
                        raise ValueError(f"Element in '{key}' must be a mapping")
                    name = elem_data.get("name", key)
                    elements[name] = Element(
                        name=name,
                        description=elem_data.get("description", ""),
                        image_urls=elem_data.get("image_urls", []),
                    )
            elif isinstance(value, dict):
                # Flat format: ElementName: {description: ...}
                elements[key] = Element(
                    name=key,
                    description=value.get("description", ""),
                    image_urls=value.get("image_urls", []),
                )
            else:
                raise ValueError(f"Element '{key}' must be a mapping or list")

    # -- Scenes --
    scenes: list[Scene] = []
    for scene_data in raw.get("scenes", []):
        if not isinstance(scene_data, dict):
            raise ValueError(f"Each scene must be a mapping, got {type(scene_data).__name__}")

        scene_id = scene_data.get("id", "")
        if not scene_id:
            raise ValueError("Each scene must have an 'id' field")

        shots: list[Shot] = []
        for shot_data in scene_data.get("shots", []):
            if not isinstance(shot_data, dict):
                raise ValueError(f"Each shot must be a mapping in scene '{scene_id}'")

            shot = Shot(
                scene_id=scene_id,
                shot_id=str(shot_data.get("id", "")),
                time=shot_data.get("time", ""),
                prompt=shot_data.get("prompt", ""),
                elements_needed=shot_data.get("elements_needed", []),
                duration=int(shot_data.get("duration", 5)),
                negative_prompt=shot_data.get("negative_prompt", ""),
            )
            shots.append(shot)

        scene = Scene(
            id=scene_id,
            title=scene_data.get("title", ""),
            time=scene_data.get("time", ""),
            background=scene_data.get("background", ""),
            lighting=scene_data.get("lighting", ""),
            shots=shots,
        )
        scenes.append(scene)

    return Scenario(
        global_config=global_config,
        elements=elements,
        scenes=scenes,
    )
