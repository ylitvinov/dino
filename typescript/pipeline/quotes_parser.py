"""Parse quotes from folder structure.

Each quote is a folder under quotes_dir/:
    quotes/atticus_1/
        meta.yaml             # author, original_language
        en.txt                # original text (one line per quote line)
        ru.txt                # translation
        deploy_status.yaml    # per-language per-platform deployment status
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pipeline.models import Quote, QuoteLine


def _read_lines(txt_path: Path) -> list[str]:
    """Read non-empty lines from a .txt file."""
    with open(txt_path, "r", encoding="utf-8") as f:
        return [line for line in f.read().splitlines() if line.strip()]


def load_quote(folder: Path) -> Quote:
    """Load a single quote from its folder.

    Args:
        folder: Path to the quote folder (e.g. quotes/atticus_1/).

    Returns:
        Quote object.

    Raises:
        FileNotFoundError: If meta.yaml or original text file missing.
        ValueError: If format is invalid.
    """
    meta_path = folder / "meta.yaml"
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing meta.yaml in {folder}")

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = yaml.safe_load(f)

    author = meta.get("author", "Unknown")
    original_language = meta.get("original_language", "en")

    txt_path = folder / f"{original_language}.txt"
    if not txt_path.exists():
        raise FileNotFoundError(f"Missing {original_language}.txt in {folder}")

    raw_lines = _read_lines(txt_path)
    if not raw_lines:
        raise ValueError(f"Empty quote in {txt_path}")

    lines = [QuoteLine(text=line, index=i) for i, line in enumerate(raw_lines)]

    return Quote(
        id=folder.name,
        author=author,
        original_language=original_language,
        lines=lines,
        folder=folder,
    )


def load_quotes(quotes_dir: str | Path) -> list[Quote]:
    """Load all quotes from the quotes directory.

    Scans for subdirectories containing meta.yaml.

    Args:
        quotes_dir: Path to the quotes directory.

    Returns:
        List of Quote objects, sorted by ID.
    """
    qdir = Path(quotes_dir)
    if not qdir.exists():
        raise FileNotFoundError(f"Quotes directory not found: {qdir}")

    quotes = []
    for folder in sorted(qdir.iterdir()):
        if folder.is_dir() and (folder / "meta.yaml").exists():
            quotes.append(load_quote(folder))

    return quotes


def filter_quotes(quotes: list[Quote], quote_ids: list[str] | None) -> list[Quote]:
    """Filter quotes by IDs. Returns all if quote_ids is None or empty."""
    if not quote_ids:
        return quotes
    id_set = set(quote_ids)
    filtered = [q for q in quotes if q.id in id_set]
    missing = id_set - {q.id for q in filtered}
    if missing:
        available = ", ".join(q.id for q in quotes)
        raise ValueError(f"Quote(s) not found: {', '.join(missing)}. Available: {available}")
    return filtered


def get_translation(quote: Quote, lang_code: str) -> list[str] | None:
    """Read an existing translation file if it exists.

    Args:
        quote: The quote (must have folder set).
        lang_code: Language code (e.g. "ru").

    Returns:
        List of translated lines, or None if file doesn't exist.
    """
    if not quote.folder:
        return None
    txt_path = quote.folder / f"{lang_code}.txt"
    if not txt_path.exists():
        return None
    return _read_lines(txt_path)


def save_translation(quote: Quote, lang_code: str, lines: list[str]) -> Path:
    """Save a translation as a .txt file in the quote folder.

    Args:
        quote: The quote (must have folder set).
        lang_code: Language code (e.g. "ru").
        lines: Translated lines.

    Returns:
        Path to the saved file.
    """
    if not quote.folder:
        raise ValueError(f"Quote {quote.id} has no folder path")
    txt_path = quote.folder / f"{lang_code}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return txt_path


def load_deploy_status(quote: Quote) -> dict:
    """Load deploy_status.yaml for a quote.

    Returns:
        Dict like {lang: {platform: {status, url, published_at}}}.
    """
    if not quote.folder:
        return {}
    path = quote.folder / "deploy_status.yaml"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_deploy_status(quote: Quote, status: dict) -> None:
    """Save deploy_status.yaml for a quote."""
    if not quote.folder:
        raise ValueError(f"Quote {quote.id} has no folder path")
    path = quote.folder / "deploy_status.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(status, f, default_flow_style=False, allow_unicode=True)


def init_deploy_status(quote: Quote, languages: list[str], platforms: list[str]) -> dict:
    """Initialize deploy_status.yaml with pending entries for all lang+platform combos.

    Only adds missing entries, preserves existing ones.
    """
    existing = load_deploy_status(quote)
    for lang in languages:
        if lang not in existing:
            existing[lang] = {}
        for platform in platforms:
            if platform not in existing[lang]:
                existing[lang][platform] = {"status": "pending"}
    save_deploy_status(quote, existing)
    return existing
