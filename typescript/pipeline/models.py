"""Data models for the quotes-video pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class QuoteLine:
    """A single line within a quote."""
    text: str
    index: int


@dataclass
class Quote:
    """A parsed quote with metadata."""
    id: str
    author: str
    original_language: str
    lines: list[QuoteLine]
    folder: Path | None = None  # path to quote folder


@dataclass
class LanguageConfig:
    """A target language for translation."""
    code: str
    name: str


@dataclass
class TranslatedQuote:
    """A quote translated into a target language."""
    quote_id: str
    language: str
    lines: list[str]
    author: str


@dataclass
class WordTimestamp:
    """A word with its timing information."""
    word: str
    start: float  # seconds
    end: float  # seconds


@dataclass
class LineTimestamp:
    """Timing for one quote line."""
    text: str
    index: int
    start: float
    end: float
    words: list[WordTimestamp] = field(default_factory=list)


@dataclass
class VoiceoverResult:
    """Result of TTS generation for a quote in one language."""
    quote_id: str
    language: str
    audio_path: str
    duration: float
    lines: list[LineTimestamp]


@dataclass
class ClipInfo:
    """A generated video clip from the clip library."""
    image_name: str
    clip_path: str
    duration: float
    task_id: str | None = None
    status: str = "pending"  # pending | submitted | completed | failed
    error: str | None = None


@dataclass
class TaskStatus:
    """Status of an async API task."""
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
class PlatformDeploy:
    """Deployment status for one language on one platform."""
    status: str = "pending"  # pending | published | scheduled
    url: str = ""
    published_at: str = ""
