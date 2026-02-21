"""CLI runner for the typescript pipeline.

Usage:
    python -m src voiceover <lang> [quote_ids...]
    python -m src assemble <lang> [quote_ids...]
    python -m src produce <lang> [quote_ids...]
    python -m src status [lang...]
    python -m src deploy_status <lang> [quote_ids...]
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


def _find_lang_dirs(config_path: str) -> list[Path]:
    """Find all language directories (dirs containing .txt files)."""
    from src.config import get_project_root
    root = get_project_root(config_path)
    exclude = {"src", "clips", ".git", "__pycache__", "node_modules"}
    dirs = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and d.name not in exclude and not d.name.startswith("."):
            if any(d.glob("*.txt")):
                dirs.append(d)
    return dirs


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
# voiceover
# ------------------------------------------------------------------

@cli.command("voiceover")
@click.argument("lang")
@click.argument("quote_ids", nargs=-1)
@click.pass_context
def cmd_voiceover(ctx: click.Context, lang: str, quote_ids: tuple[str, ...]) -> None:
    """Generate TTS voiceovers with timestamps."""
    from src.config import load_config
    from src.quotes import load_quotes, filter_quotes
    from src.voiceover import generate_voiceover, rebuild_transcript

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

    console.print(f"[bold]Generating voiceovers for {len(quotes)} quote(s) [{lang}]...[/bold]\n")

    for quote in quotes:
        quote_dir = output_dir / quote.id
        transcript_path = quote_dir / f"{quote.id}_transcript.json"
        raw_path = quote_dir / f"{quote.id}_elevenlabs_raw.json"
        audio_path = quote_dir / f"{quote.id}_voice.mp3"

        if transcript_path.exists():
            console.print(f"  [dim]{quote.id}: skip (transcript exists)[/dim]")
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
            result = generate_voiceover(quote, output_dir, elevenlabs_config, lang)
            console.print(f"  [green]{quote.id}: done ({result.duration:.1f}s)[/green]")
        except Exception as exc:
            console.print(f"  [red]{quote.id}: failed — {exc}[/red]")

    console.print("\n[bold]Voiceover complete.[/bold]")


# ------------------------------------------------------------------
# assemble
# ------------------------------------------------------------------

@cli.command("assemble")
@click.argument("lang")
@click.argument("quote_ids", nargs=-1)
@click.pass_context
def cmd_assemble(ctx: click.Context, lang: str, quote_ids: tuple[str, ...]) -> None:
    """Assemble final videos from clips + voiceover."""
    import json as _json
    from src.config import load_config, get_clips_dir
    from src.quotes import load_quotes, filter_quotes, load_status, save_status
    from src.assemble import assemble_quote
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

    console.print(f"[bold]Assembling videos for {len(quotes)} quote(s) [{lang}]...[/bold]\n")

    for quote in quotes:
        q_status = status.setdefault(quote.id, {})

        if q_status.get("assembly", {}).get("status") == "completed":
            console.print(f"  [dim]{quote.id}: already assembled[/dim]")
            continue

        transcript_path = output_dir / quote.id / f"{quote.id}_transcript.json"
        audio_path = output_dir / quote.id / f"{quote.id}_voice.mp3"
        if not transcript_path.exists():
            console.print(f"  [yellow]{quote.id}: no voiceover, skipping[/yellow]")
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
            assemble_quote(
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

    console.print("\n[bold]Assembly complete.[/bold]")


# ------------------------------------------------------------------
# produce (voiceover + assemble)
# ------------------------------------------------------------------

@cli.command("produce")
@click.argument("lang")
@click.argument("quote_ids", nargs=-1)
@click.pass_context
def cmd_produce(ctx: click.Context, lang: str, quote_ids: tuple[str, ...]) -> None:
    """Full pipeline: voiceover -> assemble."""
    console.rule("[bold blue]Step 1: Voiceover[/bold blue]")
    ctx.invoke(cmd_voiceover, lang=lang, quote_ids=quote_ids)

    console.rule("[bold blue]Step 2: Assemble[/bold blue]")
    ctx.invoke(cmd_assemble, lang=lang, quote_ids=quote_ids)

    console.rule("[bold green]Pipeline Complete[/bold green]")


# ------------------------------------------------------------------
# deploy_status
# ------------------------------------------------------------------

@cli.command("deploy_status")
@click.argument("lang")
@click.argument("quote_ids", nargs=-1)
@click.pass_context
def cmd_deploy_status(ctx: click.Context, lang: str, quote_ids: tuple[str, ...]) -> None:
    """Show deployment status for quotes across platforms."""
    from src.config import load_config, get_platforms
    from src.quotes import load_quotes, filter_quotes, load_status, save_status

    config_path = ctx.obj["config"]
    config = load_config(config_path)
    lang_dir = _resolve_lang_dir(config_path, lang)
    platforms = get_platforms(config)

    quotes = load_quotes(lang_dir)
    quotes = filter_quotes(quotes, list(quote_ids) or None)
    status = load_status(lang_dir)

    changed = False
    for quote in quotes:
        q_status = status.setdefault(quote.id, {})
        deploy = q_status.setdefault("deploy", {})
        for platform in platforms:
            if platform not in deploy:
                deploy[platform] = "pending"
                changed = True
    if changed:
        save_status(lang_dir, status)

    table = Table(title=f"Deploy Status [{lang}]", show_lines=True)
    table.add_column("Quote", style="cyan")
    for platform in platforms:
        table.add_column(platform, justify="center")

    for quote in quotes:
        deploy = status.get(quote.id, {}).get("deploy", {})
        row = [quote.id]
        for platform in platforms:
            st = deploy.get(platform, "pending")
            if st == "published":
                row.append("[green]published[/green]")
            elif st == "scheduled":
                row.append("[yellow]scheduled[/yellow]")
            else:
                row.append("[dim]pending[/dim]")
        table.add_row(*row)

    console.print(table)
    console.print()


# ------------------------------------------------------------------
# status
# ------------------------------------------------------------------

@cli.command("status")
@click.argument("langs", nargs=-1)
@click.pass_context
def cmd_status(ctx: click.Context, langs: tuple[str, ...]) -> None:
    """Show current pipeline status. Pass language names or omit for all."""
    from src.config import load_config, get_clips_dir
    from src.quotes import load_quotes, load_status

    config_path = ctx.obj["config"]
    config = load_config(config_path)
    clips_dir = get_clips_dir(config, config_path)

    if langs:
        lang_dirs = [_resolve_lang_dir(config_path, l) for l in langs]
    else:
        lang_dirs = _find_lang_dirs(config_path)

    clip_files = sorted(clips_dir.glob("*.mp4")) if clips_dir.exists() else []
    if clip_files:
        console.print(f"[bold]Clips:[/bold] {len(clip_files)} file(s) in {clips_dir}")
        for f in clip_files:
            console.print(f"  [dim]{f.name}[/dim]")
        console.print()

    if not lang_dirs:
        console.print("[yellow]No language directories found.[/yellow]")
        return

    for lang_dir in lang_dirs:
        quotes = load_quotes(lang_dir)
        status = load_status(lang_dir)

        if not quotes:
            console.print(f"[dim]{lang_dir.name}: no quotes[/dim]")
            continue

        table = Table(title=f"[{lang_dir.name}]", show_lines=True)
        table.add_column("Quote", style="cyan")
        table.add_column("Lines", justify="center")
        table.add_column("Voiceover", justify="center")
        table.add_column("Assembly", justify="center")

        output_dir = lang_dir / "output"
        for quote in quotes:
            q_status = status.get(quote.id, {})
            transcript_path = output_dir / quote.id / f"{quote.id}_transcript.json"
            vo_st = "completed" if transcript_path.exists() else ""
            asm_st = q_status.get("assembly", {}).get("status", "")

            def _fmt(st: str) -> str:
                if st == "completed":
                    return "[green]done[/green]"
                elif st == "failed":
                    return "[red]failed[/red]"
                return "[dim]—[/dim]"

            table.add_row(
                quote.id,
                str(len(quote.lines)),
                _fmt(vo_st),
                _fmt(asm_st),
            )

        console.print(table)
        console.print()


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
