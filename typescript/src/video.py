"""Video builder: trim clips, add text overlay, concat, mix audio.

Uses FFmpeg to produce final short-form videos from clips + TTS audio.
"""

from __future__ import annotations

import logging
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.clips import load_clip_zones, get_zone_for_clip
from src.models import ClipTextZone, VoiceoverResult

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


def _random_walk(
    count: int, rng: random.Random, lo: int, hi: int, max_step: int,
) -> list[int]:
    val = rng.randint(lo, hi)
    positions = []
    for _ in range(count):
        positions.append(val)
        delta = rng.randint(-max_step, max_step)
        val = max(lo, min(hi, val + delta))
    return positions


def _compute_text_positions(
    selected_clips: list[Path],
    zones: dict[str, ClipTextZone],
    rng: random.Random,
    config: dict,
) -> tuple[list[int], list[int]]:
    """Compute Y positions and X offsets for each line.

    If a clip has a zone, the random walk for that line is constrained to the zone.
    Otherwise, falls back to global config bounds.
    """
    n = len(selected_clips)

    y_min_default = config.get("text_y_min", 400)
    y_max_default = config.get("text_y_max", 1500)
    y_step = config.get("text_y_step", 150)
    x_offset_max = config.get("text_x_offset_max", 100)
    x_offset_step = config.get("text_x_offset_step", 80)

    y_positions: list[int] = []
    x_offsets: list[int] = []

    cur_y: int | None = None
    cur_x: int | None = None

    for i in range(n):
        zone = get_zone_for_clip(zones, selected_clips[i])
        if zone:
            y_lo, y_hi = zone.y, zone.y + zone.h
            x_lo = -(zone.w // 2)
            x_hi = zone.w // 2
            # x_center_offset: zone center relative to frame center
            zone_center_x = zone.x + zone.w // 2
            frame_center_x = 540  # 1080 / 2
            x_base_offset = zone_center_x - frame_center_x
        else:
            y_lo, y_hi = y_min_default, y_max_default
            x_lo, x_hi = -x_offset_max, x_offset_max
            x_base_offset = 0

        if cur_y is None:
            cur_y = rng.randint(y_lo, y_hi)
        else:
            delta = rng.randint(-y_step, y_step)
            cur_y = max(y_lo, min(y_hi, cur_y + delta))

        if cur_x is None:
            cur_x = rng.randint(x_lo, x_hi) + x_base_offset
        else:
            delta = rng.randint(-x_offset_step, x_offset_step)
            cur_x = max(x_lo + x_base_offset, min(x_hi + x_base_offset, cur_x + delta))

        y_positions.append(cur_y)
        x_offsets.append(cur_x)

    return y_positions, x_offsets


def _get_clip_files(clips_dir: Path) -> list[Path]:
    return sorted(clips_dir.glob("*.mp4"))


def _select_clips(
    available: list[Path],
    count: int,
    seed: str = "",
) -> list[Path]:
    if not available:
        raise ValueError("No clips available for video build")
    rng = random.Random(seed)
    shuffled = available[:]
    rng.shuffle(shuffled)
    return [shuffled[i % len(shuffled)] for i in range(count)]


def _create_paused_audio(
    audio_path: str,
    lines: list,
    pause_duration: float,
    tmp: Path,
) -> Path:
    """Insert silence between lines in the TTS audio via FFmpeg."""
    parts = []
    inputs = []

    for i in range(len(lines)):
        start = 0.0 if i == 0 else lines[i].start
        if i < len(lines) - 1:
            trim = f"atrim={start}:{lines[i + 1].start}"
        else:
            trim = f"atrim=start={start}"

        parts.append(f"[0:a]{trim},asetpts=PTS-STARTPTS[s{i}]")
        inputs.append(f"[s{i}]")

        if i < len(lines) - 1:
            parts.append(
                f"anullsrc=r=44100:cl=stereo,atrim=0:{pause_duration},asetpts=PTS-STARTPTS[p{i}]"
            )
            inputs.append(f"[p{i}]")

    n = len(inputs)
    parts.append(f"{''.join(inputs)}concat=n={n}:v=0:a=1[out]")

    output = tmp / "voice_paused.mp3"
    cmd = [
        "ffmpeg", "-y",
        "-i", audio_path,
        "-filter_complex", ";".join(parts),
        "-map", "[out]",
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(output),
    ]

    logger.info("Inserting %.1fs pauses between %d lines", pause_duration, len(lines))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio pause failed: {result.stderr[-500:]}")

    return output


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


def build_video(
    voiceover: VoiceoverResult,
    clips_dir: Path,
    output_path: Path,
    assembly_config: dict,
    music_path: Path | None = None,
) -> Path:
    """Build a final video for one quote."""
    tmpdir = tempfile.mkdtemp(prefix="quotes_video_")
    try:
        return _build_video_inner(voiceover, clips_dir, output_path, assembly_config, tmpdir, music_path)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _build_video_inner(
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

    line_pause = config.get("line_pause", 1.5)
    if line_pause > 0 and len(lines) > 1:
        paused_audio_path = _create_paused_audio(
            voiceover.audio_path, lines, line_pause, tmp,
        )
        audio_for_mux = str(paused_audio_path)
    else:
        audio_for_mux = voiceover.audio_path

    font = config.get("font", "fonts/SpecialElite-Regular.ttf")
    font_size = config.get("font_size", 48)
    font_color = config.get("font_color", "white")
    border_w = config.get("border_width", 2)
    border_color = config.get("border_color", "black")
    max_chars = config.get("max_chars_per_line", 30)

    clip_zones = load_clip_zones(clips_dir)
    rng = random.Random(voiceover.quote_id)
    y_positions, x_offsets = _compute_text_positions(selected, clip_zones, rng, config)
    resolution = config.get("resolution", "1080x1920")
    fps = config.get("fps", 30)

    width, height = resolution.split("x")

    segment_files: list[Path] = []
    concat_list = tmp / "concat.txt"

    for i, line in enumerate(lines):
        clip_path = selected[i]
        clip_duration = _get_video_duration(clip_path)

        if i < len(lines) - 1:
            line_duration = lines[i + 1].start - line.start + line_pause
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
                f":x=max(20\\, min(w-tw-20\\, (w-tw)/2+{x_offsets[i]}))"
                f":y={y_positions[i]}"
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
        music_vol = config.get("music_volume", 0.3)
        cmd_mux = [
            "ffmpeg", "-y",
            "-i", str(concat_video),
            "-i", audio_for_mux,
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
            "-i", audio_for_mux,
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

    fade_dur = config.get("outro_fade", 0.5)
    if fade_dur > 0:
        duration = _get_video_duration(output_path)
        fade_start = max(0, duration - fade_dur)
        pre_fade = tmp / "pre_fade.mp4"
        shutil.move(str(output_path), str(pre_fade))

        cmd_fade = [
            "ffmpeg", "-y",
            "-i", str(pre_fade),
            "-vf", f"fade=t=out:st={fade_start:.3f}:d={fade_dur:.3f}",
            "-af", f"afade=t=out:st={fade_start:.3f}:d={fade_dur:.3f}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            str(output_path),
        ]
        logger.info("Applying %.1fs fade-out at %.1fs", fade_dur, fade_start)
        result = subprocess.run(cmd_fade, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg fade failed: {result.stderr[-500:]}")

    logger.info("Built video: %s (%.1f KB)", output_path, output_path.stat().st_size / 1024)
    return output_path
