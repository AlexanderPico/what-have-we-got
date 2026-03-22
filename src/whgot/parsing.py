"""Response parsing utilities — separated from vision.py to avoid ollama import at test time."""

from __future__ import annotations

import json
import re
from typing import Optional

from whgot.schema import Identifiers, Item, ItemCategory, ItemMetadata


def parse_items_response(raw: str, source_image: Optional[str] = None) -> list[Item]:
    """Parse a vision model's JSON response into a list of Item objects.

    Handles common model quirks: markdown fences, trailing commas,
    single objects instead of arrays.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)

    # Try to parse as JSON
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to extract JSON array from surrounding text
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            # Last resort: try as single object
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                data = [json.loads(match.group())]
            else:
                raise ValueError(f"Could not parse model response as JSON:\n{raw[:500]}")

    # Normalize to list
    if isinstance(data, dict):
        data = [data]

    items = []
    for entry in data:
        # Map the flat model output to our nested schema
        metadata_fields = {}
        identifiers_fields = {}

        meta_raw = entry.get("metadata", {}) or {}
        ident_raw = entry.get("identifiers", {}) or {}

        # Pull metadata fields
        for key in ItemMetadata.model_fields:
            if key in meta_raw and meta_raw[key] is not None:
                metadata_fields[key] = meta_raw[key]

        # Pull identifier fields
        for key in Identifiers.model_fields:
            if key in ident_raw and ident_raw[key] is not None:
                identifiers_fields[key] = ident_raw[key]

        # Map category string to enum, fallback to OTHER
        cat_str = entry.get("category", "other")
        try:
            category = ItemCategory(cat_str)
        except ValueError:
            category = ItemCategory.OTHER

        item = Item(
            name=entry.get("name", "Unknown Item"),
            category=category,
            confidence=float(entry.get("confidence", 0.5)),
            description=entry.get("description"),
            metadata=ItemMetadata(**metadata_fields),
            identifiers=Identifiers(**identifiers_fields),
            source_image=source_image,
        )
        items.append(item)

    return items
