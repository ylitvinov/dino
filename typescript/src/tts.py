"""TTS generation via ElevenLabs with word timestamps."""

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

    # Filter out pause separator words
    words = [w for w in words if w.word != "..."]

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


def _save_transcript(
    quote: Quote,
    alignment: dict,
    quote_dir: Path,
) -> VoiceoverResult:
    """Build transcript from raw ElevenLabs alignment data and save to disk."""
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

    ts_path = quote_dir / f"{quote.id}_transcript.json"
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

    audio_path = quote_dir / f"{quote.id}_voice.mp3"
    logger.info("Transcript saved: %s (%.1fs, %d lines)", ts_path, duration, len(line_timestamps))

    return VoiceoverResult(
        quote_id=quote.id,
        audio_path=str(audio_path),
        duration=duration,
        lines=line_timestamps,
    )


def rebuild_transcript(quote: Quote, output_dir: Path) -> VoiceoverResult:
    """Rebuild transcript from existing raw ElevenLabs response file."""
    quote_dir = output_dir / quote.id
    raw_path = quote_dir / f"{quote.id}_elevenlabs_raw.json"

    with open(raw_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    alignment = raw_data.get("normalized_alignment", raw_data.get("alignment", {}))
    return _save_transcript(quote, alignment, quote_dir)


def generate_tts(
    quote: Quote,
    output_dir: Path,
    elevenlabs_config: dict,
    lang: str,
) -> VoiceoverResult:
    """Generate TTS audio with timestamps for a quote."""
    api_key = elevenlabs_config["api_key"]
    voices = elevenlabs_config.get("voices", {})
    voice_id = voices.get(lang)
    if not voice_id:
        raise ValueError(f"No voice configured for language '{lang}' in elevenlabs.voices")
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

    logger.info("Calling ElevenLabs API for %s (voice=%s, model=%s)", quote.id, voice_id, model_id)
    logger.info("Text: %s", full_text)

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=body)
        response.raise_for_status()

    data = response.json()

    # Save raw ElevenLabs response (without audio blob)
    quote_dir = output_dir / quote.id
    quote_dir.mkdir(parents=True, exist_ok=True)
    raw_path = quote_dir / f"{quote.id}_elevenlabs_raw.json"
    raw_data = {k: v for k, v in data.items() if k != "audio_base64"}
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, indent=2, ensure_ascii=False)
    logger.info("Raw response saved: %s", raw_path)

    audio_b64 = data.get("audio_base64", "")
    if not audio_b64:
        raise ValueError(f"No audio in ElevenLabs response for {quote.id}")

    audio_bytes = base64.b64decode(audio_b64)
    audio_path = quote_dir / f"{quote.id}_voice.mp3"
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)
    logger.info("Audio saved: %s (%d bytes)", audio_path, len(audio_bytes))

    alignment = data.get("normalized_alignment", data.get("alignment", {}))
    return _save_transcript(quote, alignment, quote_dir)
