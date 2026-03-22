"""Vision pipeline: image → structured Item identification via local ollama models.

Uses ollama's Python client to send images to a local vision-language model
(e.g., llava, moondream, minicpm-v) and extract structured item data.

Requires ollama running locally with a vision model pulled:
    ollama pull llava:13b
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

import ollama
from PIL import Image

from whgot.parsing import parse_items_response
from whgot.schema import Item

# Default model — llava:13b is the best balance of accuracy and speed.
# Alternatives: moondream (faster, less accurate), minicpm-v (good multilingual),
# llava:34b (more accurate, needs ~20GB VRAM)
DEFAULT_MODEL = "llava:13b"

# System prompt for single-item identification
IDENTIFY_SYSTEM = """You are an expert item appraiser and identifier for resale markets (eBay, etc.).
Given an image, identify the item(s) and return structured JSON.

For EACH distinct item visible, return a JSON object with these fields:
- name: string — the item's full name/title
- category: string — one of: book, dvd, bluray, cd, vinyl, video_game, toy, collectible, clothing, electronics, household, other
- confidence: float 0-1 — how confident you are in the identification
- description: string — brief physical description including notable features, flaws, wear
- metadata: object with relevant fields:
  - brand, manufacturer, model, color, size, material, era, genre, format
  - For books: author, publisher, edition, year_published
  - For media: director, artist, runtime_minutes
  - For toys/collectibles: franchise, character, scale, in_packaging (boolean)
- identifiers: object — isbn, upc, asin if you can determine them (leave null if unsure)

Return a JSON array of items. If only one item, still wrap in an array.
Return ONLY valid JSON, no markdown fences, no commentary."""

# System prompt for shelf/batch scanning — identifies multiple items from one image
BATCH_SYSTEM = """You are an expert item appraiser scanning a shelf, rack, or collection.
Identify as many individual items as you can see in this image.
For each item, return a JSON object with:
- name: string — the item's full name/title (for books: full title; for DVDs: full movie/show title)
- category: string — one of: book, dvd, bluray, cd, vinyl, video_game, toy, collectible, clothing, electronics, household, other
- confidence: float 0-1 — how confident you are (lower for partially obscured items)
- description: string — brief description of what you can see
- metadata: object with relevant fields (author, brand, franchise, etc.)
- identifiers: object — isbn, upc, asin if determinable (null if unsure)

Focus on accuracy over completeness — it's better to correctly identify 15 items
than to guess at 25. If a spine/label is partially obscured, say so in description
and lower confidence.

Return a JSON array. Return ONLY valid JSON, no markdown fences, no commentary."""


def _encode_image(image_path: Path) -> str:
    """Read and base64-encode an image file for the ollama API."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")



def identify_image(
    image_path: str | Path,
    model: str = DEFAULT_MODEL,
    batch_mode: bool = False,
) -> list[Item]:
    """Identify item(s) in an image using a local vision model via ollama.

    Args:
        image_path: Path to the image file (jpg, png, webp, etc.)
        model: Ollama model name. Must be a vision model.
        batch_mode: If True, use the batch/shelf scanning prompt to
                     identify multiple items. If False, use the single-item prompt.

    Returns:
        List of identified Items with metadata populated.

    Raises:
        FileNotFoundError: If image_path doesn't exist.
        ConnectionError: If ollama is not running.
        ValueError: If model response can't be parsed.
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    # Validate it's actually an image
    try:
        img = Image.open(path)
        img.verify()
    except Exception as e:
        raise ValueError(f"Invalid image file {path}: {e}")

    system_prompt = BATCH_SYSTEM if batch_mode else IDENTIFY_SYSTEM

    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": "Identify the item(s) in this image.",
                    "images": [str(path)],
                },
            ],
            options={
                "temperature": 0.1,  # Low temp for structured output
                "num_predict": 4096,  # Allow long responses for batch mode
            },
        )
    except Exception as e:
        if "connection" in str(e).lower() or "refused" in str(e).lower():
            raise ConnectionError(
                "Cannot connect to ollama. Is it running? Start with: ollama serve"
            ) from e
        raise

    raw_text = response["message"]["content"]
    return parse_items_response(raw_text, source_image=str(path))


def identify_text(
    description: str,
    model: str = DEFAULT_MODEL,
) -> Item:
    """Identify an item from a text description using a local LLM via ollama.

    This is the non-vision path for the `ingest` command — takes a text
    description (e.g., "Blue Nike Air Max 90, size 11, worn") and returns
    a structured Item.

    Args:
        description: Free-text item description.
        model: Ollama model name. Does not need to be a vision model.

    Returns:
        Single identified Item.
    """
    text_system = """You are an expert item appraiser for resale markets.
Given a text description of an item, return a single JSON object with:
- name: string — the item's full name/title (be specific)
- category: string — one of: book, dvd, bluray, cd, vinyl, video_game, toy, collectible, clothing, electronics, household, other
- confidence: float 0-1 — how confident you are based on the description quality
- description: string — normalized description
- metadata: object with relevant fields (brand, author, size, color, etc.)
- identifiers: object — isbn, upc, asin if determinable from the description

Return ONLY valid JSON, no markdown fences, no commentary."""

    # For text-only identification, we can use any model (doesn't need vision)
    # Prefer a smaller/faster text model if available
    text_model = model.replace("llava", "llama3.1").replace("moondream", "llama3.1")

    try:
        response = ollama.chat(
            model=text_model,
            messages=[
                {"role": "system", "content": text_system},
                {"role": "user", "content": f"Identify this item: {description}"},
            ],
            options={"temperature": 0.1, "num_predict": 1024},
        )
    except Exception as e:
        if "connection" in str(e).lower() or "refused" in str(e).lower():
            raise ConnectionError(
                "Cannot connect to ollama. Is it running? Start with: ollama serve"
            ) from e
        # If the text model isn't available, fall back to the original model
        if "not found" in str(e).lower():
            response = ollama.chat(
                model=model,
                messages=[
                    {"role": "system", "content": text_system},
                    {"role": "user", "content": f"Identify this item: {description}"},
                ],
                options={"temperature": 0.1, "num_predict": 1024},
            )
        else:
            raise

    raw_text = response["message"]["content"]
    items = parse_items_response(raw_text, source_image=None)
    if items:
        items[0].source_text = description
        return items[0]

    # Fallback: return a minimal item if parsing fails entirely
    return Item(name=description, source_text=description)
