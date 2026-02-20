"""Data models for the KIE.ai Kling 3.0 video generation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

from kie_client import TaskStatus, Element  # noqa: F401 — re-exported


@dataclass
class Shot:
    """A single shot within a scene (maps to one entry in multi_prompt).

    Attributes:
        scene_id: ID of the parent scene.
        prompt: The generation prompt for this shot.
        duration: Duration in seconds (5 or 10).
    """
    scene_id: str
    prompt: str
    duration: int = 5


@dataclass
class Scene:
    """A scene containing multiple shots (maps to one API request).

    Attributes:
        id: Unique scene identifier.
        background: Background description injected into prompts.
        lighting: Lighting description injected into prompts.
        kling_elements: Names of elements needed for this scene.
        shots: Ordered list of shots in this scene.
    """
    id: str
    background: str = ""
    lighting: str = ""
    kling_elements: list[str] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)


@dataclass
class Scenario:
    """Top-level scenario containing all generation parameters.

    Attributes:
        global_config: Global settings (style_prefix, negative_prompt).
        elements: Dict of element name -> Element (populated from status file).
        scenes: Ordered list of scenes.
    """
    global_config: dict = field(default_factory=dict)
    elements: dict[str, Element] = field(default_factory=dict)
    scenes: list[Scene] = field(default_factory=list)
