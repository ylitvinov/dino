"""CLI runner for the typescript pipeline.

Usage:
    python -m src tts <lang> [quote_ids...]
    python -m src video <lang> [quote_ids...]
    python -m src produce <lang> [quote_ids...]

"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()

_DEFAULT_CONFIG = "config.yaml"


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


def _resolve_lang_dir(config_path: str, lang: str) -> Path:
    from src.config import get_project_root
    root = get_project_root(config_path)
    lang_dir = root / lang
    if not lang_dir.is_dir():
        console.print(f"[red]Language directory not found: {lang_dir}[/red]")
        sys.exit(1)
    return lang_dir


@click.group()
@click.option("--config", "-c", default=_DEFAULT_CONFIG, help="Path to config.yaml")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx: click.Context, config: str, verbose: bool) -> None:
    """typescript — short-form video from text quotes."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    _setup_logging(verbose)


# ------------------------------------------------------------------
# tts
# ------------------------------------------------------------------

@cli.command("tts")
@click.argument("lang")
@click.argument("quote_ids", nargs=-1)
@click.option("--force", "-f", is_flag=True, help="Regenerate even if transcript exists")
@click.pass_context
def cmd_tts(ctx: click.Context, lang: str, quote_ids: tuple[str, ...], force: bool) -> None:
    """Generate TTS audio with timestamps."""
    from src.config import load_config
    from src.quotes import load_quotes, filter_quotes
    from src.tts import generate_tts, rebuild_transcript

    config_path = ctx.obj["config"]
    config = load_config(config_path)
    lang_dir = _resolve_lang_dir(config_path, lang)
    output_dir = lang_dir / "output"

    quotes = load_quotes(lang_dir)
    quotes = filter_quotes(quotes, list(quote_ids) or None)

    elevenlabs_config = config["elevenlabs"]
    if not elevenlabs_config.get("api_key"):
        console.print("[red]Error: elevenlabs.api_key is not set in config.yaml[/red]")
        sys.exit(1)

    console.print(f"[bold]Generating TTS for {len(quotes)} quote(s) [{lang}]...[/bold]\n")

    for quote in quotes:
        quote_dir = output_dir / quote.id
        transcript_path = quote_dir / f"{quote.id}_transcript.json"
        raw_path = quote_dir / f"{quote.id}_elevenlabs_raw.json"
        audio_path = quote_dir / f"{quote.id}_voice.mp3"

        if not force:
            if transcript_path.exists():
                console.print(f"  [dim]{quote.id}: skip (transcript exists) -> {audio_path}[/dim]")
                continue

            if raw_path.exists() and audio_path.exists():
                try:
                    console.print(f"  [yellow]{quote.id}: rebuilding transcript from raw...[/yellow]")
                    result = rebuild_transcript(quote, output_dir)
                    console.print(f"  [green]{quote.id}: transcript rebuilt ({result.duration:.1f}s)[/green]")
                except Exception as exc:
                    console.print(f"  [red]{quote.id}: transcript rebuild failed — {exc}[/red]")
                continue

        try:
            console.print(f"  {quote.id}: calling ElevenLabs API...")
            result = generate_tts(quote, output_dir, elevenlabs_config, lang)
            console.print(f"  [green]{quote.id}: done ({result.duration:.1f}s)[/green]")
        except Exception as exc:
            console.print(f"  [red]{quote.id}: failed — {exc}[/red]")

    console.print("\n[bold]TTS complete.[/bold]")


# ------------------------------------------------------------------
# video
# ------------------------------------------------------------------

@cli.command("video")
@click.argument("lang")
@click.argument("quote_ids", nargs=-1)
@click.option("--force", "-f", is_flag=True, help="Rebuild even if already done")
@click.pass_context
def cmd_video(ctx: click.Context, lang: str, quote_ids: tuple[str, ...], force: bool) -> None:
    """Build final videos from clips + TTS audio."""
    import json as _json
    from src.config import load_config, get_clips_dir
    from src.quotes import load_quotes, filter_quotes, load_status, save_status
    from src.video import build_video
    from src.models import VoiceoverResult, LineTimestamp

    config_path = ctx.obj["config"]
    config = load_config(config_path)
    lang_dir = _resolve_lang_dir(config_path, lang)
    output_dir = lang_dir / "output"
    clips_dir = get_clips_dir(config, config_path)

    quotes = load_quotes(lang_dir)
    quotes = filter_quotes(quotes, list(quote_ids) or None)
    status = load_status(lang_dir)

    assembly_config = config["assembly"]
    music_path = lang_dir / "background_music.mp3"
    if not music_path.exists():
        music_path = None

    console.print(f"[bold]Building videos for {len(quotes)} quote(s) [{lang}]...[/bold]\n")

    for quote in quotes:
        q_status = status.setdefault(quote.id, {})

        if not force and q_status.get("assembly", {}).get("status") == "completed":
            existing = q_status["assembly"].get("video_path", "?")
            console.print(f"  [dim]{quote.id}: already built -> {existing}[/dim]")
            continue

        transcript_path = output_dir / quote.id / f"{quote.id}_transcript.json"
        audio_path = output_dir / quote.id / f"{quote.id}_voice.mp3"
        if not transcript_path.exists():
            console.print(f"  [yellow]{quote.id}: no TTS audio, skipping[/yellow]")
            continue

        with open(transcript_path, "r", encoding="utf-8") as tf:
            transcript = _json.load(tf)

        vo_lines = [
            LineTimestamp(
                text=lt["text"],
                index=lt.get("index", i),
                start=lt["start"],
                end=lt["end"],
            )
            for i, lt in enumerate(transcript["lines"])
        ]
        voiceover_result = VoiceoverResult(
            quote_id=quote.id,
            audio_path=str(audio_path),
            duration=transcript["duration"],
            lines=vo_lines,
        )

        video_path = output_dir / quote.id / f"{quote.id}_clip.mp4"

        try:
            build_video(
                voiceover=voiceover_result,
                clips_dir=clips_dir,
                output_path=video_path,
                assembly_config=assembly_config,
                music_path=music_path,
            )
            q_status["assembly"] = {
                "status": "completed",
                "video_path": str(video_path),
            }
            console.print(f"  [green]{quote.id}: done -> {video_path}[/green]")
        except Exception as exc:
            q_status["assembly"] = {"status": "failed", "error": str(exc)}
            console.print(f"  [red]{quote.id}: failed — {exc}[/red]")

        save_status(lang_dir, status)

    console.print("\n[bold]Video build complete.[/bold]")


# ------------------------------------------------------------------
# produce (tts + video)
# ------------------------------------------------------------------

@cli.command("produce")
@click.argument("lang")
@click.argument("quote_ids", nargs=-1)
@click.option("--force", "-f", is_flag=True, help="Regenerate even if output exists")
@click.pass_context
def cmd_produce(ctx: click.Context, lang: str, quote_ids: tuple[str, ...], force: bool) -> None:
    """Full pipeline: tts -> video."""
    console.rule("[bold blue]Step 1: TTS[/bold blue]")
    ctx.invoke(cmd_tts, lang=lang, quote_ids=quote_ids, force=force)

    console.rule("[bold blue]Step 2: Video[/bold blue]")
    ctx.invoke(cmd_video, lang=lang, quote_ids=quote_ids, force=force)

    console.rule("[bold green]Pipeline Complete[/bold green]")


# ------------------------------------------------------------------
# clips_annotate
# ------------------------------------------------------------------

@cli.command("clips_annotate")
@click.option("--force", "-f", is_flag=True, help="Re-annotate all clips")
@click.pass_context
def cmd_clips_annotate(ctx: click.Context, force: bool) -> None:
    """Auto-annotate clip text zones via Claude Vision."""
    import os
    from src.config import load_config, get_clips_dir
    from src.annotate import annotate_clips

    config_path = ctx.obj["config"]
    config = load_config(config_path)
    clips_dir = get_clips_dir(config, config_path)

    api_key = (
        config.get("anthropic", {}).get("api_key")
        or os.environ.get("ANTHROPIC_API_KEY")
        or ""
    )
    if not api_key:
        console.print("[red]Error: set anthropic.api_key in config.yaml or ANTHROPIC_API_KEY env[/red]")
        sys.exit(1)

    console.print(f"[bold]Annotating clips in {clips_dir}...[/bold]\n")
    zones = annotate_clips(clips_dir, api_key, force=force)
    console.print(f"\n[bold green]Done — {len(zones)} clip(s) annotated.[/bold green]")


# ------------------------------------------------------------------
# clips_preview
# ------------------------------------------------------------------

@cli.command("clips_preview")
@click.option("--open", "open_folder", is_flag=True, help="Open previews folder in Finder")
@click.pass_context
def cmd_clips_preview(ctx: click.Context, open_folder: bool) -> None:
    """Generate preview images with text-zone overlays."""
    from src.config import load_config, get_clips_dir
    from src.preview import generate_previews

    config_path = ctx.obj["config"]
    config = load_config(config_path)
    clips_dir = get_clips_dir(config, config_path)

    console.print(f"[bold]Generating previews for {clips_dir}...[/bold]\n")
    previews_dir = generate_previews(clips_dir, open_folder=open_folder)
    console.print(f"\n[bold green]Previews saved to {previews_dir}[/bold green]")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
