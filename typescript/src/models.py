"""Data models for the quotes-video pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Quote:
    """A quote loaded from a .txt file in a language directory."""
    id: str
    language: str
    lines: list[str]
    path: Path


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
class ClipTextZone:
    """Safe rectangle for text overlay in 1080x1920 space."""
    x: int
    y: int
    w: int
    h: int


@dataclass
class VoiceoverResult:
    """Result of TTS generation for a quote."""
    quote_id: str
    audio_path: str
    duration: float
    lines: list[LineTimestamp]
