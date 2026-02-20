"""CLI runner for the typescript pipeline.

Usage:
    python -m pipeline generate-clips
    python -m pipeline translate [quote_ids...]
    python -m pipeline voiceover [quote_ids...]
    python -m pipeline assemble [quote_ids...]
    python -m pipeline produce [quote_ids...]
    python -m pipeline status
    python -m pipeline deploy-status [quote_ids...]
"""

from __future__ import annotations

import asyncio
import json
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


def _load_json(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


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
# generate-clips
# ------------------------------------------------------------------

@cli.command("generate-clips")
@click.pass_context
def cmd_generate_clips(ctx: click.Context) -> None:
    """Generate video clips from images in the clip library."""
    from pipeline.clip_generator import generate_clips

    config_path = ctx.obj["config"]
    console.print("[bold]Starting clip generation...[/bold]")

    try:
        asyncio.run(generate_clips(config_path=config_path))
    except FileNotFoundError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        sys.exit(1)
    except ValueError as exc:
        console.print(f"[red]Configuration error: {exc}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Progress saved.[/yellow]")
        sys.exit(130)


# ------------------------------------------------------------------
# translate
# ------------------------------------------------------------------

@cli.command("translate")
@click.argument("quote_ids", nargs=-1)
@click.pass_context
def cmd_translate(ctx: click.Context, quote_ids: tuple[str, ...]) -> None:
    """Translate quotes into configured languages. Saves .txt files into quote folders."""
    from pipeline.config import load_config, get_languages, get_quotes_dir
    from pipeline.quotes_parser import load_quotes, filter_quotes, get_translation
    from pipeline.translator import translate_quote

    config_path = ctx.obj["config"]
    config = load_config(config_path)
    languages = get_languages(config)
    quotes_dir = get_quotes_dir(config, config_path)

    quotes = load_quotes(quotes_dir)
    quotes = filter_quotes(quotes, list(quote_ids) or None)

    openai_config = config["openai"]
    if not openai_config.get("api_key"):
        console.print("[red]Error: openai.api_key is not set in config.yaml[/red]")
        sys.exit(1)

    console.print(f"[bold]Translating {len(quotes)} quote(s) into {len(languages)} language(s)...[/bold]\n")

    for quote in quotes:
        for lang in languages:
            # Check if .txt file already exists
            existing = get_translation(quote, lang.code)
            if existing:
                console.print(f"  [dim]{quote.id}/{lang.code}: already exists[/dim]")
                continue

            try:
                translate_quote(quote, lang, openai_config)
                console.print(f"  [green]{quote.id}/{lang.code}: done[/green]")
            except Exception as exc:
                console.print(f"  [red]{quote.id}/{lang.code}: failed — {exc}[/red]")

    console.print("\n[bold]Translation complete.[/bold]")


# ------------------------------------------------------------------
# voiceover
# ------------------------------------------------------------------

@cli.command("voiceover")
@click.argument("quote_ids", nargs=-1)
@click.pass_context
def cmd_voiceover(ctx: click.Context, quote_ids: tuple[str, ...]) -> None:
    """Generate TTS voiceovers with timestamps."""
    from pipeline.config import load_config, get_languages, get_quotes_output_dir, get_quotes_status_path, get_quotes_dir
    from pipeline.quotes_parser import load_quotes, filter_quotes, get_translation
    from pipeline.voiceover import generate_voiceover
    from pipeline.models import TranslatedQuote

    config_path = ctx.obj["config"]
    config = load_config(config_path)
    languages = get_languages(config)
    output_dir = get_quotes_output_dir(config, config_path)
    status_path = get_quotes_status_path(config, config_path)
    quotes_dir = get_quotes_dir(config, config_path)

    quotes = load_quotes(quotes_dir)
    quotes = filter_quotes(quotes, list(quote_ids) or None)
    status = _load_json(status_path)

    elevenlabs_config = config["elevenlabs"]
    if not elevenlabs_config.get("api_key"):
        console.print("[red]Error: elevenlabs.api_key is not set in config.yaml[/red]")
        sys.exit(1)

    console.print(f"[bold]Generating voiceovers for {len(quotes)} quote(s)...[/bold]\n")

    for quote in quotes:
        q_status = status.setdefault(quote.id, {})
        voiceovers = q_status.setdefault("voiceovers", {})

        for lang in languages:
            key = lang.code

            if key in voiceovers and voiceovers[key].get("status") == "completed":
                console.print(f"  [dim]{quote.id}/{key}: already voiced[/dim]")
                continue

            # Need translation .txt file
            trans_lines = get_translation(quote, key)
            if not trans_lines:
                console.print(f"  [yellow]{quote.id}/{key}: no translation, skipping[/yellow]")
                continue

            translated = TranslatedQuote(
                quote_id=quote.id,
                language=key,
                lines=trans_lines,
                author=quote.author,
            )

            try:
                quote_output_dir = output_dir / quote.id
                result = generate_voiceover(translated, quote_output_dir, elevenlabs_config)
                voiceovers[key] = {
                    "status": "completed",
                    "audio_path": result.audio_path,
                    "duration": result.duration,
                    "lines": [
                        {"text": lt.text, "start": lt.start, "end": lt.end}
                        for lt in result.lines
                    ],
                }
                console.print(f"  [green]{quote.id}/{key}: done ({result.duration:.1f}s)[/green]")
            except Exception as exc:
                voiceovers[key] = {
                    "status": "failed",
                    "error": str(exc),
                }
                console.print(f"  [red]{quote.id}/{key}: failed — {exc}[/red]")

            _save_json(status_path, status)

    console.print("\n[bold]Voiceover complete.[/bold]")


# ------------------------------------------------------------------
# assemble
# ------------------------------------------------------------------

@cli.command("assemble")
@click.argument("quote_ids", nargs=-1)
@click.pass_context
def cmd_assemble(ctx: click.Context, quote_ids: tuple[str, ...]) -> None:
    """Assemble final videos from clips + voiceover."""
    from pipeline.config import (
        load_config, get_languages, get_quotes_output_dir,
        get_quotes_status_path, get_clips_dir, get_clips_status_path, get_quotes_dir,
    )
    from pipeline.quotes_parser import load_quotes, filter_quotes
    from pipeline.assembler import assemble_quote
    from pipeline.models import VoiceoverResult, LineTimestamp

    config_path = ctx.obj["config"]
    config = load_config(config_path)
    languages = get_languages(config)
    output_dir = get_quotes_output_dir(config, config_path)
    status_path = get_quotes_status_path(config, config_path)
    clips_dir = get_clips_dir(config, config_path)
    clips_status_path = get_clips_status_path(config, config_path)
    quotes_dir = get_quotes_dir(config, config_path)

    quotes = load_quotes(quotes_dir)
    quotes = filter_quotes(quotes, list(quote_ids) or None)
    status = _load_json(status_path)

    assembly_config = config["assembly"]

    console.print(f"[bold]Assembling videos for {len(quotes)} quote(s)...[/bold]\n")

    for quote in quotes:
        q_status = status.setdefault(quote.id, {})
        voiceovers = q_status.get("voiceovers", {})
        assemblies = q_status.setdefault("assemblies", {})

        for lang in languages:
            key = lang.code

            if key in assemblies and assemblies[key].get("status") == "completed":
                console.print(f"  [dim]{quote.id}/{key}: already assembled[/dim]")
                continue

            vo = voiceovers.get(key)
            if not vo or vo.get("status") != "completed":
                console.print(f"  [yellow]{quote.id}/{key}: no voiceover, skipping[/yellow]")
                continue

            vo_lines = [
                LineTimestamp(
                    text=lt["text"],
                    index=i,
                    start=lt["start"],
                    end=lt["end"],
                )
                for i, lt in enumerate(vo["lines"])
            ]
            voiceover_result = VoiceoverResult(
                quote_id=quote.id,
                language=key,
                audio_path=vo["audio_path"],
                duration=vo["duration"],
                lines=vo_lines,
            )

            video_path = output_dir / quote.id / f"{quote.id}_{key}.mp4"

            try:
                assemble_quote(
                    voiceover=voiceover_result,
                    clips_dir=clips_dir,
                    clips_status_path=clips_status_path,
                    output_path=video_path,
                    assembly_config=assembly_config,
                )
                assemblies[key] = {
                    "status": "completed",
                    "video_path": str(video_path),
                }
                console.print(f"  [green]{quote.id}/{key}: done -> {video_path}[/green]")
            except Exception as exc:
                assemblies[key] = {
                    "status": "failed",
                    "error": str(exc),
                }
                console.print(f"  [red]{quote.id}/{key}: failed — {exc}[/red]")

            _save_json(status_path, status)

    console.print("\n[bold]Assembly complete.[/bold]")


# ------------------------------------------------------------------
# produce (translate + voiceover + assemble)
# ------------------------------------------------------------------

@cli.command("produce")
@click.argument("quote_ids", nargs=-1)
@click.pass_context
def cmd_produce(ctx: click.Context, quote_ids: tuple[str, ...]) -> None:
    """Full pipeline: translate -> voiceover -> assemble."""
    console.rule("[bold blue]Step 1: Translate[/bold blue]")
    ctx.invoke(cmd_translate, quote_ids=quote_ids)

    console.rule("[bold blue]Step 2: Voiceover[/bold blue]")
    ctx.invoke(cmd_voiceover, quote_ids=quote_ids)

    console.rule("[bold blue]Step 3: Assemble[/bold blue]")
    ctx.invoke(cmd_assemble, quote_ids=quote_ids)

    console.rule("[bold green]Pipeline Complete[/bold green]")


# ------------------------------------------------------------------
# deploy-status
# ------------------------------------------------------------------

@cli.command("deploy-status")
@click.argument("quote_ids", nargs=-1)
@click.pass_context
def cmd_deploy_status(ctx: click.Context, quote_ids: tuple[str, ...]) -> None:
    """Show deployment status for quotes across platforms."""
    from pipeline.config import load_config, get_languages, get_platforms, get_quotes_dir
    from pipeline.quotes_parser import load_quotes, filter_quotes, load_deploy_status, init_deploy_status

    config_path = ctx.obj["config"]
    config = load_config(config_path)
    languages = get_languages(config)
    platforms = get_platforms(config)
    quotes_dir = get_quotes_dir(config, config_path)

    quotes = load_quotes(quotes_dir)
    quotes = filter_quotes(quotes, list(quote_ids) or None)

    lang_codes = [l.code for l in languages]

    for quote in quotes:
        # Ensure deploy_status.yaml has all lang+platform combos
        deploy = init_deploy_status(quote, lang_codes, platforms)

        table = Table(title=f"{quote.id} ({quote.author})", show_lines=True)
        table.add_column("Language", style="cyan")
        for platform in platforms:
            table.add_column(platform, justify="center")

        for lang in lang_codes:
            lang_deploy = deploy.get(lang, {})
            row = [lang]
            for platform in platforms:
                info = lang_deploy.get(platform, {})
                st = info.get("status", "pending")
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
@click.pass_context
def cmd_status(ctx: click.Context) -> None:
    """Show current pipeline status."""
    from pipeline.config import load_config, get_clips_status_path, get_quotes_status_path, get_quotes_dir
    from pipeline.quotes_parser import load_quotes, get_translation

    config_path = ctx.obj["config"]
    config = load_config(config_path)

    clips_status_path = get_clips_status_path(config, config_path)
    quotes_status_path = get_quotes_status_path(config, config_path)
    quotes_dir = get_quotes_dir(config, config_path)

    clips_status = _load_json(clips_status_path)
    pipeline_status = _load_json(quotes_status_path)

    # Load quotes from folders
    try:
        quotes = load_quotes(quotes_dir)
    except FileNotFoundError:
        quotes = []

    languages = [l["code"] for l in config.get("languages", [])]

    has_data = bool(clips_status) or bool(pipeline_status) or bool(quotes)
    if not has_data:
        console.print("[yellow]No data found. Pipeline has not been run yet.[/yellow]")
        return

    # Clips table
    clips = clips_status.get("clips", {})
    if clips:
        table = Table(title="Clip Library", show_lines=True)
        table.add_column("Image", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("File", max_width=50)

        for name, info in sorted(clips.items()):
            st = info.get("status", "unknown")
            if st == "completed":
                status_str = "[green]DONE[/green]"
            elif st == "failed":
                status_str = "[red]FAILED[/red]"
            elif st in ("submitted", "processing"):
                status_str = "[yellow]IN PROGRESS[/yellow]"
            else:
                status_str = f"[dim]{st.upper()}[/dim]"

            file_str = info.get("clip_path", info.get("error", ""))
            table.add_row(name, status_str, str(file_str))

        console.print(table)
        console.print()

    # Quotes table
    if quotes:
        table = Table(title="Quotes", show_lines=True)
        table.add_column("Quote", style="cyan")
        table.add_column("Author")
        table.add_column("Lines", justify="center")
        table.add_column("Translations", justify="center")
        table.add_column("Voiceovers", justify="center")
        table.add_column("Assemblies", justify="center")

        for quote in quotes:
            # Count translations by checking .txt files
            trans_count = sum(
                1 for lang in languages
                if get_translation(quote, lang) is not None
            )

            # Count voiceovers/assemblies from pipeline status
            q_pipeline = pipeline_status.get(quote.id, {})
            vos = q_pipeline.get("voiceovers", {})
            asms = q_pipeline.get("assemblies", {})

            vo_done = sum(1 for v in vos.values() if v.get("status") == "completed")
            asm_done = sum(1 for a in asms.values() if a.get("status") == "completed")

            def _fmt(done: int, total: int) -> str:
                if total == 0:
                    return "[dim]—[/dim]"
                if done == total:
                    return f"[green]{done}/{total}[/green]"
                return f"[yellow]{done}/{total}[/yellow]"

            table.add_row(
                quote.id,
                quote.author,
                str(len(quote.lines)),
                _fmt(trans_count, len(languages)),
                _fmt(vo_done, len(languages)),
                _fmt(asm_done, len(languages)),
            )

        console.print(table)
        console.print()

    # Summary
    total_clips = len(clips)
    done_clips = sum(1 for c in clips.values() if c.get("status") == "completed")
    console.print("[bold]Summary:[/bold]")
    console.print(f"  Clips: {done_clips}/{total_clips}")
    console.print(f"  Quotes: {len(quotes)}")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
