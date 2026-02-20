"""Load quotes from language directories.

Structure:
    en/
        atticus_1.txt       # one line per quote line
        marcus_1.txt
        status.json         # pipeline & deploy status
        output/             # generated voiceovers & videos
"""

from __future__ import annotations

import json
from pathlib import Path

from src.models import Quote


def _read_lines(txt_path: Path) -> list[str]:
    with open(txt_path, "r", encoding="utf-8") as f:
        return [line for line in f.read().splitlines() if line.strip()]


def load_quotes(lang_dir: Path) -> list[Quote]:
    """Load all quotes from a language directory.

    Each .txt file is a quote. Filename (without extension) is the quote ID.
    """
    if not lang_dir.exists():
        raise FileNotFoundError(f"Language directory not found: {lang_dir}")

    quotes = []
    for txt_file in sorted(lang_dir.glob("*.txt")):
        lines = _read_lines(txt_file)
        if lines:
            quotes.append(Quote(
                id=txt_file.stem,
                language=lang_dir.name,
                lines=lines,
                path=txt_file,
            ))
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


def load_status(lang_dir: Path) -> dict:
    status_path = lang_dir / "status.json"
    if status_path.exists():
        with open(status_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_status(lang_dir: Path, status: dict) -> None:
    status_path = lang_dir / "status.json"
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)
