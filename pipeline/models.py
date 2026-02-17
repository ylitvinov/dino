"""Data models for the KIE.ai Kling 3.0 video generation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Element:
    """A visual element (character, object, background) used across shots.

    Attributes:
        name: Unique identifier for this element.
        description: Textual description sent to API as kling_elements[].description.
        image_urls: List of reference image URLs (CDN URLs from KIE.ai).
    """
    name: str
    description: str = ""
    image_urls: list[str] = field(default_factory=list)


@dataclass
class Shot:
    """A single shot within a scene (maps to one entry in multi_prompt).

    Attributes:
        scene_id: ID of the parent scene.
        prompt: The generation prompt for this shot.
        duration: Duration in seconds (5 or 10).
        negative_prompt: Things to avoid in generation.
    """
    scene_id: str
    prompt: str
    duration: int = 5
    negative_prompt: str = ""


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


@dataclass
class TaskStatus:
    """Status of a KIE.ai generation task.

    Attributes:
        task_id: The unique task identifier from KIE.ai.
        status: One of "pending", "processing", "completed", "failed".
        output_url: URL to the generated output (video or image), if completed.
        error: Error message if the task failed.
    """
    task_id: str
    status: str
    output_url: str | None = None
    error: str | None = None

    @property
    def is_done(self) -> bool:
        """Whether the task has reached a terminal state."""
        return self.status in ("completed", "failed")

    @property
    def is_success(self) -> bool:
        """Whether the task completed successfully."""
        return self.status == "completed"
