"""Condition grading engine — assess item condition from images.

Uses a local vision model via ollama to detect:
- Physical damage (tears, stains, scratches, dents, foxing)
- Wear indicators (creased spines, faded covers, yellowed pages)
- Packaging state (sealed, opened, missing packaging)
- Completeness (missing parts, accessories, inserts)

Outputs a Condition enum value plus a free-text condition note
describing detected flaws.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from whgot.schema import Condition, Item, ItemCategory

# --- Prompts ---

CONDITION_SYSTEM = """You are an expert condition grader for resale items (eBay, used bookstores, etc.).
Examine this image and assess the item's condition. Look for:

1. DAMAGE: tears, rips, stains, water damage, foxing (brown spots on paper), scratches, dents, cracks
2. WEAR: creased spine, faded colors, yellowed pages, rubbing, shelf wear, sun damage
3. PACKAGING: is it sealed/unopened? In original packaging? Missing packaging?
4. COMPLETENESS: any visible missing parts, loose pages, missing inserts/manuals?

Return a JSON object with exactly these fields:
- grade: one of "new_sealed", "new_open", "like_new", "very_good", "good", "acceptable", "for_parts"
- confidence: float 0-1
- flaws: array of strings, each describing a specific flaw (empty array if none)
- notes: string — brief overall condition summary

Be conservative: if you can't inspect closely, default to "good" rather than over-grading.
For items in packaging, note whether the packaging is sealed or opened.

Return ONLY valid JSON, no markdown fences, no commentary."""


def grade_condition(
    item: Item,
    model: str = "llava:13b",
) -> Item:
    """Assess item condition from its source image.

    Updates the item's condition field and adds condition notes
    to the description. Requires the item to have a source_image path.

    Args:
        item: Item with source_image set.
        model: Ollama vision model to use.

    Returns:
        The same Item, mutated with condition data.
    """
    if not item.source_image:
        return item

    path = Path(item.source_image)
    if not path.exists():
        return item

    try:
        import json
        import ollama

        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": CONDITION_SYSTEM},
                {
                    "role": "user",
                    "content": "Grade the condition of this item.",
                    "images": [str(path)],
                },
            ],
            options={"temperature": 0.1, "num_predict": 1024},
        )

        raw = response["message"]["content"]

        # Parse response (reuse the same cleanup logic as parsing.py)
        import re

        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)

        data = json.loads(cleaned)

        # Map grade to Condition enum
        grade_str = data.get("grade", "unknown")
        try:
            item.condition = Condition(grade_str)
        except ValueError:
            # Try common variations
            grade_map = {
                "new": Condition.NEW_SEALED,
                "mint": Condition.LIKE_NEW,
                "excellent": Condition.LIKE_NEW,
                "fair": Condition.ACCEPTABLE,
                "poor": Condition.FOR_PARTS,
            }
            item.condition = grade_map.get(grade_str.lower(), Condition.UNKNOWN)

        # Add flaw notes to description
        flaws = data.get("flaws", [])
        notes = data.get("notes", "")

        condition_text = notes
        if flaws:
            condition_text += " Flaws: " + "; ".join(flaws)

        if condition_text.strip():
            existing = item.description or ""
            if existing:
                item.description = f"{existing}\n\nCondition: {condition_text.strip()}"
            else:
                item.description = f"Condition: {condition_text.strip()}"

    except Exception:
        # Condition grading is best-effort — don't fail the pipeline
        pass

    return item


def grade_conditions(
    items: list[Item],
    model: str = "llava:13b",
) -> list[Item]:
    """Grade conditions for a batch of items. Convenience wrapper."""
    return [grade_condition(item, model=model) for item in items]


def estimate_condition_from_text(description: str) -> Condition:
    """Heuristic condition estimation from text description (no LLM needed).

    Scans for condition-related keywords. Used as a fallback when
    no image is available or ollama is down.
    """
    desc_lower = description.lower()

    # Keyword-based heuristics
    new_keywords = ["sealed", "new in box", "nib", "nwt", "brand new", "factory sealed", "shrink"]
    like_new_keywords = ["like new", "mint", "excellent", "pristine", "unread", "unworn"]
    very_good_keywords = ["very good", "great condition", "minimal wear", "light wear"]
    good_keywords = ["good condition", "some wear", "used", "pre-owned", "preowned"]
    acceptable_keywords = ["acceptable", "fair", "worn", "stained", "damaged", "rough"]
    parts_keywords = ["for parts", "as-is", "as is", "broken", "not working", "repair"]

    for kw in new_keywords:
        if kw in desc_lower:
            return Condition.NEW_SEALED
    for kw in like_new_keywords:
        if kw in desc_lower:
            return Condition.LIKE_NEW
    for kw in very_good_keywords:
        if kw in desc_lower:
            return Condition.VERY_GOOD
    for kw in good_keywords:
        if kw in desc_lower:
            return Condition.GOOD
    for kw in acceptable_keywords:
        if kw in desc_lower:
            return Condition.ACCEPTABLE
    for kw in parts_keywords:
        if kw in desc_lower:
            return Condition.FOR_PARTS

    return Condition.UNKNOWN
