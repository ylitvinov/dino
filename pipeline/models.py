"""Data models for the KIE.ai Kling 3.0 video generation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Element:
    """A visual element (character, object, background) used across shots.

    Attributes:
        name: Unique identifier for this element.
        description: Textual description used in image generation prompts.
        image_urls: List of reference image URLs (CDN URLs from KIE.ai).
    """
    name: str
    description: str
    image_urls: list[str] = field(default_factory=list)


@dataclass
class Shot:
    """A single shot within a scene.

    Attributes:
        scene_id: ID of the parent scene.
        shot_id: Unique ID of this shot within the scene.
        time: Timecode or time description (e.g. "00:05-00:10").
        prompt: The generation prompt for this shot.
        elements_needed: Names of elements required in this shot.
        duration: Duration in seconds (5 or 10).
        negative_prompt: Things to avoid in generation.
    """
    scene_id: str
    shot_id: str
    time: str
    prompt: str
    elements_needed: list[str] = field(default_factory=list)
    duration: int = 5
    negative_prompt: str = ""


@dataclass
class Scene:
    """A scene containing multiple shots.

    Attributes:
        id: Unique scene identifier.
        title: Human-readable scene title.
        time: Time range for this scene.
        background: Background description for continuity.
        lighting: Lighting description for continuity.
        shots: Ordered list of shots in this scene.
    """
    id: str
    title: str
    time: str
    background: str
    lighting: str
    shots: list[Shot] = field(default_factory=list)


@dataclass
class Scenario:
    """Top-level scenario containing all generation parameters.

    Attributes:
        global_config: Global settings (style_prefix, negative_prompt, etc.).
        elements: Dict of element name -> Element.
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
