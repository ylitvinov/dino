"""Video assembler: trim clips, add text overlay, concat, mix audio.

Uses FFmpeg to produce final short-form videos from clips + voiceover.
"""

from __future__ import annotations

import json
import logging
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from pipeline.models import VoiceoverResult, LineTimestamp

logger = logging.getLogger(__name__)


def _escape_drawtext(text: str) -> str:
    """Escape text for FFmpeg drawtext filter."""
    # FFmpeg drawtext requires escaping: \ ' : %
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\u2019")  # Replace with unicode right single quote
    text = text.replace(":", "\\:")
    text = text.replace("%", "%%")
    return text


def _wrap_text(text: str, max_chars: int) -> str:
    """Wrap text to fit within max_chars per line for drawtext."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if len(test) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return "\n".join(lines)


def _get_clip_files(
    clips_dir: Path,
    status_path: Path,
) -> list[Path]:
    """Get list of completed clip files from status."""
    if not status_path.exists():
        # Fallback: just list mp4 files
        return sorted(clips_dir.glob("*.mp4"))

    with open(status_path, "r", encoding="utf-8") as f:
        status = json.load(f)

    clips = []
    for name, info in sorted(status.get("clips", {}).items()):
        if info.get("status") == "completed" and info.get("clip_path"):
            clip_path = Path(info["clip_path"])
            if clip_path.exists():
                clips.append(clip_path)
    return clips


def _select_clips(
    available: list[Path],
    count: int,
    mode: str = "sequential",
) -> list[Path]:
    """Select clips for quote lines.

    Args:
        available: Available clip files.
        count: Number of clips needed.
        mode: Selection mode — sequential, random, or round_robin.

    Returns:
        List of clip paths (may repeat if fewer clips than lines).
    """
    if not available:
        raise ValueError("No clips available for assembly")

    if mode == "random":
        return [random.choice(available) for _ in range(count)]
    elif mode == "round_robin":
        return [available[i % len(available)] for i in range(count)]
    else:  # sequential
        selected = []
        for i in range(count):
            selected.append(available[i % len(available)])
        return selected


def _get_video_duration(path: Path) -> float:
    """Get video duration using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 6.0  # fallback


def assemble_quote(
    voiceover: VoiceoverResult,
    clips_dir: Path,
    clips_status_path: Path,
    output_path: Path,
    assembly_config: dict,
) -> Path:
    """Assemble a final video for one quote in one language.

    Steps:
    1. Select clips for each line
    2. Per line: trim/loop clip to line duration, add text overlay
    3. Concat all shots
    4. Mix voiceover audio
    5. Output final .mp4

    Args:
        voiceover: VoiceoverResult with audio and line timestamps.
        clips_dir: Directory containing clip library.
        clips_status_path: Path to clips_status.json.
        output_path: Where to save the final video.
        assembly_config: Assembly settings from config.

    Returns:
        Path to the final video.
    """
    tmpdir = tempfile.mkdtemp(prefix="quotes_video_")
    try:
        return _assemble_inner(voiceover, clips_dir, clips_status_path, output_path, assembly_config, tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _assemble_inner(
    voiceover: VoiceoverResult,
    clips_dir: Path,
    clips_status_path: Path,
    output_path: Path,
    config: dict,
    tmpdir: str,
) -> Path:
    tmp = Path(tmpdir)
    lines = voiceover.lines

    if not lines:
        raise ValueError(f"No lines in voiceover for {voiceover.quote_id}/{voiceover.language}")

    # Get available clips
    available_clips = _get_clip_files(clips_dir, clips_status_path)
    if not available_clips:
        raise ValueError("No clips available. Run 'generate-clips' first.")

    selected = _select_clips(available_clips, len(lines), config.get("clip_selection", "sequential"))

    font = config.get("font", "/System/Library/Fonts/Helvetica.ttc")
    font_size = config.get("font_size", 48)
    font_color = config.get("font_color", "white")
    border_w = config.get("border_width", 2)
    border_color = config.get("border_color", "black")
    text_y = config.get("text_y_position", "h-th-120")
    max_chars = config.get("max_chars_per_line", 30)
    resolution = config.get("resolution", "1080x1920")
    fps = config.get("fps", 30)

    width, height = resolution.split("x")

    # Step 1: Create per-line video segments
    segment_files: list[Path] = []
    concat_list = tmp / "concat.txt"

    for i, line in enumerate(lines):
        clip_path = selected[i]
        clip_duration = _get_video_duration(clip_path)

        # Line duration (with a small buffer for the last line)
        if i < len(lines) - 1:
            line_duration = lines[i + 1].start - line.start
        else:
            line_duration = voiceover.duration - line.start

        # Minimum 1 second per line
        line_duration = max(line_duration, 1.0)

        # Prepare text
        wrapped = _wrap_text(line.text, max_chars)
        escaped = _escape_drawtext(wrapped)

        segment_path = tmp / f"seg_{i:03d}.mp4"

        # Build FFmpeg command
        input_args = []
        if clip_duration < line_duration:
            # Loop the clip
            loop_count = int(line_duration / clip_duration) + 1
            input_args = ["-stream_loop", str(loop_count)]

        filter_parts = [
            f"scale={width}:{height}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}",
            f"fps={fps}",
            (
                f"drawtext=text='{escaped}'"
                f":fontfile='{font}'"
                f":fontsize={font_size}"
                f":fontcolor={font_color}"
                f":borderw={border_w}"
                f":bordercolor={border_color}"
                f":x=(w-tw)/2"
                f":y={text_y}"
            ),
        ]
        vf = ",".join(filter_parts)

        cmd = [
            "ffmpeg", "-y",
            *input_args,
            "-i", str(clip_path),
            "-t", f"{line_duration:.3f}",
            "-vf", vf,
            "-an",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            str(segment_path),
        ]

        logger.info("Creating segment %d: %.1fs, clip=%s", i, line_duration, clip_path.name)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed for segment {i}: {result.stderr[-500:]}")

        segment_files.append(segment_path)

    # Step 2: Write concat file
    with open(concat_list, "w") as f:
        for seg in segment_files:
            f.write(f"file '{seg}'\n")

    # Step 3: Concat all segments
    concat_video = tmp / "concat.mp4"
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(concat_video),
    ]
    result = subprocess.run(cmd_concat, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr[-500:]}")

    # Step 4: Mix in voiceover audio
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path = voiceover.audio_path

    cmd_mux = [
        "ffmpeg", "-y",
        "-i", str(concat_video),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        str(output_path),
    ]
    result = subprocess.run(cmd_mux, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg mux failed: {result.stderr[-500:]}")

    logger.info("Assembled: %s (%.1f KB)", output_path, output_path.stat().st_size / 1024)
    return output_path
