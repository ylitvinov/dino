"""Video assembler: trim clips, add text overlay, concat, mix audio.

Uses FFmpeg to produce final short-form videos from clips + voiceover.
"""

from __future__ import annotations

import logging
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.models import VoiceoverResult

logger = logging.getLogger(__name__)


def _escape_drawtext(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\u2019")
    text = text.replace(":", "\\:")
    text = text.replace("%", "%%")
    return text


def _wrap_text(text: str, max_chars: int) -> str:
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


def _get_clip_files(clips_dir: Path) -> list[Path]:
    return sorted(clips_dir.glob("*.mp4"))


def _select_clips(
    available: list[Path],
    count: int,
    seed: str = "",
) -> list[Path]:
    if not available:
        raise ValueError("No clips available for assembly")
    rng = random.Random(seed)
    shuffled = available[:]
    rng.shuffle(shuffled)
    return [shuffled[i % len(shuffled)] for i in range(count)]


def _get_video_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 6.0


def assemble_quote(
    voiceover: VoiceoverResult,
    clips_dir: Path,
    output_path: Path,
    assembly_config: dict,
    music_path: Path | None = None,
) -> Path:
    """Assemble a final video for one quote."""
    tmpdir = tempfile.mkdtemp(prefix="quotes_video_")
    try:
        return _assemble_inner(voiceover, clips_dir, output_path, assembly_config, tmpdir, music_path)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _assemble_inner(
    voiceover: VoiceoverResult,
    clips_dir: Path,
    output_path: Path,
    config: dict,
    tmpdir: str,
    music_path: Path | None = None,
) -> Path:
    tmp = Path(tmpdir)
    lines = voiceover.lines

    if not lines:
        raise ValueError(f"No lines in voiceover for {voiceover.quote_id}")

    available_clips = _get_clip_files(clips_dir)
    if not available_clips:
        raise ValueError(f"No clip .mp4 files found in {clips_dir}")

    selected = _select_clips(available_clips, len(lines), seed=voiceover.quote_id)

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

    segment_files: list[Path] = []
    concat_list = tmp / "concat.txt"

    for i, line in enumerate(lines):
        clip_path = selected[i]
        clip_duration = _get_video_duration(clip_path)

        if i < len(lines) - 1:
            line_duration = lines[i + 1].start - line.start
        else:
            line_duration = voiceover.duration - line.start

        line_duration = max(line_duration, 1.0)

        wrapped = _wrap_text(line.text, max_chars)
        escaped = _escape_drawtext(wrapped)

        segment_path = tmp / f"seg_{i:03d}.mp4"

        input_args = []
        if clip_duration < line_duration:
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

    with open(concat_list, "w") as f:
        for seg in segment_files:
            f.write(f"file '{seg}'\n")

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

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if music_path and music_path.exists():
        music_vol = config.get("music_volume", 0.15)
        cmd_mux = [
            "ffmpeg", "-y",
            "-i", str(concat_video),
            "-i", str(voiceover.audio_path),
            "-i", str(music_path),
            "-filter_complex",
            f"[1:a]volume=1.0[voice];[2:a]volume={music_vol}[music];[voice][music]amix=inputs=2:duration=first[aout]",
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(output_path),
        ]
    else:
        cmd_mux = [
            "ffmpeg", "-y",
            "-i", str(concat_video),
            "-i", str(voiceover.audio_path),
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
