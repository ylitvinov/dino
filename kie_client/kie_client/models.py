"""Data models for the KIE.ai API client."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TaskStatus:
    """Status of a KIE.ai generation task."""
    task_id: str
    status: str  # pending | processing | completed | failed
    output_url: str | None = None
    error: str | None = None

    @property
    def is_done(self) -> bool:
        return self.status in ("completed", "failed")

    @property
    def is_success(self) -> bool:
        return self.status == "completed" and self.output_url is not None


@dataclass
class Element:
    """A visual element with reference images for Kling generation."""
    name: str
    description: str = ""
    image_urls: list[str] = field(default_factory=list)
