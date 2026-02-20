"""Quote translation via OpenAI GPT with structured output.

Translations are saved as .txt files in the quote folder.
"""

from __future__ import annotations

import json
import logging

from openai import OpenAI

from pipeline.models import Quote, TranslatedQuote, LanguageConfig
from pipeline.quotes_parser import get_translation, save_translation

logger = logging.getLogger(__name__)


def translate_quote(
    quote: Quote,
    target_lang: LanguageConfig,
    openai_config: dict,
) -> TranslatedQuote:
    """Translate a quote into the target language using OpenAI.

    Checks if translation .txt file already exists in the quote folder.
    If so, returns it without calling the API.

    Uses json_schema structured output to guarantee exactly N lines back.
    Saves the result as {lang}.txt in the quote folder.

    Args:
        quote: The source quote.
        target_lang: Target language config.
        openai_config: Dict with 'api_key' and 'model'.

    Returns:
        TranslatedQuote with translated lines.
    """
    # Skip if already in target language
    if quote.original_language == target_lang.code:
        return TranslatedQuote(
            quote_id=quote.id,
            language=target_lang.code,
            lines=[line.text for line in quote.lines],
            author=quote.author,
        )

    # Check if translation file already exists
    existing = get_translation(quote, target_lang.code)
    if existing:
        logger.info("Using existing translation %s/%s", quote.id, target_lang.code)
        return TranslatedQuote(
            quote_id=quote.id,
            language=target_lang.code,
            lines=existing,
            author=quote.author,
        )

    client = OpenAI(api_key=openai_config["api_key"])
    num_lines = len(quote.lines)
    source_text = "\n".join(f"{i+1}. {line.text}" for i, line in enumerate(quote.lines))

    schema = {
        "type": "object",
        "properties": {
            "lines": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": num_lines,
                "maxItems": num_lines,
            },
            "author": {"type": "string"},
        },
        "required": ["lines", "author"],
        "additionalProperties": False,
    }

    system_prompt = (
        f"You are a literary translator. Translate the following quote into {target_lang.name}. "
        f"The quote has exactly {num_lines} line(s). You MUST return exactly {num_lines} translated line(s), "
        f"preserving the original line breaks and structure. "
        f"Also translate the author's name if there is a well-known translation in {target_lang.name}. "
        f"Return JSON matching the provided schema."
    )

    user_prompt = f"Author: {quote.author}\n\nQuote:\n{source_text}"

    logger.info("Translating %s -> %s (%d lines)", quote.id, target_lang.code, num_lines)

    response = client.chat.completions.create(
        model=openai_config.get("model", "gpt-4o"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "translation",
                "strict": True,
                "schema": schema,
            },
        },
    )

    content = response.choices[0].message.content
    result = json.loads(content)

    translated_lines = result["lines"]
    if len(translated_lines) != num_lines:
        raise ValueError(
            f"Expected {num_lines} lines, got {len(translated_lines)} "
            f"for quote {quote.id} -> {target_lang.code}"
        )

    # Save translation as .txt file
    save_translation(quote, target_lang.code, translated_lines)

    translated = TranslatedQuote(
        quote_id=quote.id,
        language=target_lang.code,
        lines=translated_lines,
        author=result.get("author", quote.author),
    )

    logger.info("Translated %s -> %s: %s", quote.id, target_lang.code, translated_lines)
    return translated
