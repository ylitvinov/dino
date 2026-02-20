"""Voiceover generation via ElevenLabs TTS with word timestamps."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

import httpx

from src.models import Quote, VoiceoverResult, LineTimestamp, WordTimestamp

logger = logging.getLogger(__name__)

_ELEVENLABS_BASE = "https://api.elevenlabs.io"


def _build_line_timestamps(
    lines: list[str],
    characters: list[str],
    char_starts: list[float],
    char_ends: list[float],
) -> list[LineTimestamp]:
    """Map character-level timestamps to line-level and word-level."""
    words: list[WordTimestamp] = []
    current_word = ""
    word_start: float | None = None

    for i, char in enumerate(characters):
        if char == " ":
            if current_word and word_start is not None:
                words.append(WordTimestamp(
                    word=current_word,
                    start=word_start,
                    end=char_ends[i - 1] if i > 0 else char_starts[i],
                ))
                current_word = ""
                word_start = None
        else:
            if word_start is None:
                word_start = char_starts[i]
            current_word += char

    if current_word and word_start is not None:
        words.append(WordTimestamp(
            word=current_word,
            start=word_start,
            end=char_ends[-1] if char_ends else word_start,
        ))

    line_timestamps: list[LineTimestamp] = []
    word_idx = 0

    for line_idx, line_text in enumerate(lines):
        line_words_raw = line_text.split()
        line_word_count = len(line_words_raw)

        if line_word_count == 0:
            line_timestamps.append(LineTimestamp(
                text=line_text, index=line_idx, start=0.0, end=0.0,
            ))
            continue

        line_words_ts: list[WordTimestamp] = []
        for _ in range(line_word_count):
            if word_idx < len(words):
                line_words_ts.append(words[word_idx])
                word_idx += 1

        if line_words_ts:
            line_start = line_words_ts[0].start
            line_end = line_words_ts[-1].end
        else:
            prev_end = line_timestamps[-1].end if line_timestamps else 0.0
            line_start = prev_end
            line_end = prev_end

        line_timestamps.append(LineTimestamp(
            text=line_text,
            index=line_idx,
            start=line_start,
            end=line_end,
            words=line_words_ts,
        ))

    return line_timestamps


def generate_voiceover(
    quote: Quote,
    output_dir: Path,
    elevenlabs_config: dict,
) -> VoiceoverResult:
    """Generate TTS audio with timestamps for a quote."""
    api_key = elevenlabs_config["api_key"]
    voice_id = elevenlabs_config["voice_id"]
    model_id = elevenlabs_config.get("model_id", "eleven_multilingual_v2")
    voice_settings = elevenlabs_config.get("voice_settings", {})

    full_text = " ".join(quote.lines)

    url = f"{_ELEVENLABS_BASE}/v1/text-to-speech/{voice_id}/with-timestamps"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    body = {
        "text": full_text,
        "model_id": model_id,
        "voice_settings": {
            "stability": voice_settings.get("stability", 0.5),
            "similarity_boost": voice_settings.get("similarity_boost", 0.75),
            "style": voice_settings.get("style", 0.4),
        },
    }

    logger.info("Generating voiceover for %s: %r", quote.id, full_text[:80])

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=body)
        response.raise_for_status()

    data = response.json()

    audio_b64 = data.get("audio_base64", "")
    if not audio_b64:
        raise ValueError(f"No audio in ElevenLabs response for {quote.id}")

    audio_bytes = base64.b64decode(audio_b64)
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output_dir / f"{quote.id}.mp3"
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    alignment = data.get("normalized_alignment", data.get("alignment", {}))
    characters = alignment.get("characters", [])
    char_starts = alignment.get("character_start_times_seconds", [])
    char_ends = alignment.get("character_end_times_seconds", [])

    line_timestamps = _build_line_timestamps(
        quote.lines, characters, char_starts, char_ends,
    )

    if char_ends:
        duration = max(char_ends)
    elif line_timestamps:
        duration = line_timestamps[-1].end
    else:
        duration = 0.0

    ts_path = output_dir / f"{quote.id}_timestamps.json"
    ts_data = {
        "quote_id": quote.id,
        "duration": duration,
        "lines": [
            {
                "text": lt.text, "index": lt.index,
                "start": lt.start, "end": lt.end,
                "words": [
                    {"word": w.word, "start": w.start, "end": w.end}
                    for w in lt.words
                ],
            }
            for lt in line_timestamps
        ],
    }
    with open(ts_path, "w", encoding="utf-8") as f:
        json.dump(ts_data, f, indent=2, ensure_ascii=False)

    logger.info("Voiceover saved: %s (%.1fs, %d lines)", audio_path, duration, len(line_timestamps))

    return VoiceoverResult(
        quote_id=quote.id,
        audio_path=str(audio_path),
        duration=duration,
        lines=line_timestamps,
    )
