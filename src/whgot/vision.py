"""Vision pipeline: image or text -> structured Item identification via Ollama."""

from __future__ import annotations

from pathlib import Path

import ollama
from PIL import Image

from whgot.parsing import parse_items_response
from whgot.schema import Item

DEFAULT_MODEL = "llava:13b"

IDENTIFY_SYSTEM = """You are an expert item appraiser and identifier for resale markets.
Given an image, identify the item or items and return structured JSON.

For each distinct item visible, return:
- name
- category: one of book, dvd, bluray, cd, vinyl, video_game, toy,
  collectible, clothing, electronics, household, other
- confidence: float 0-1
- description
- metadata object with relevant fields
- identifiers object with isbn, upc, asin when determinable

Return a JSON array and ONLY valid JSON."""

BATCH_SYSTEM = """You are an expert item appraiser scanning a shelf, rack, or collection.
Identify as many individual items as you can see accurately.

For each item, return:
- name
- category: one of book, dvd, bluray, cd, vinyl, video_game, toy,
  collectible, clothing, electronics, household, other
- confidence: float 0-1
- description
- metadata object with relevant fields
- identifiers object with isbn, upc, asin when determinable

Focus on accuracy over completeness. Return ONLY valid JSON array output."""


def identify_image(
    image_path: str | Path,
    model: str = DEFAULT_MODEL,
    batch_mode: bool = False,
) -> list[Item]:
    """Identify item(s) in an image using a local vision model via Ollama."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    try:
        image = Image.open(path)
        image.verify()
    except Exception as exc:
        raise ValueError(f"Invalid image file {path}: {exc}") from exc

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
            options={"temperature": 0.1, "num_predict": 4096},
        )
    except Exception as exc:
        if "connection" in str(exc).lower() or "refused" in str(exc).lower():
            raise ConnectionError(
                "Cannot connect to ollama. Is it running? Start with: ollama serve"
            ) from exc
        raise

    return parse_items_response(response["message"]["content"], source_image=str(path))


def identify_text(description: str, model: str = DEFAULT_MODEL) -> Item:
    """Identify an item from a text description using a local LLM via Ollama."""
    text_system = """You are an expert item appraiser for resale markets.
Given a text description, return a single JSON object with:
- name
- category: one of book, dvd, bluray, cd, vinyl, video_game, toy,
  collectible, clothing, electronics, household, other
- confidence: float 0-1
- description
- metadata object with relevant fields
- identifiers object with isbn, upc, asin when determinable

Return ONLY valid JSON."""

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
    except Exception as exc:
        if "connection" in str(exc).lower() or "refused" in str(exc).lower():
            raise ConnectionError(
                "Cannot connect to ollama. Is it running? Start with: ollama serve"
            ) from exc
        if "not found" not in str(exc).lower():
            raise
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": text_system},
                {"role": "user", "content": f"Identify this item: {description}"},
            ],
            options={"temperature": 0.1, "num_predict": 1024},
        )

    items = parse_items_response(response["message"]["content"], source_image=None)
    if items:
        items[0].source_text = description
        return items[0]

    return Item(name=description, source_text=description)
