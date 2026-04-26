"""Condition grading engine — assess item condition from images."""

from __future__ import annotations

from pathlib import Path

from whgot.schema import Condition, Item

CONDITION_SYSTEM = """You are an expert condition grader for resale items.
Examine this image and assess the item's condition.
Look for damage, wear, packaging state, and completeness.

Return a JSON object with exactly these fields:
- grade: one of "new_sealed", "new_open", "like_new", "very_good", "good", "acceptable", "for_parts"
- confidence: float 0-1
- flaws: array of strings
- notes: string

Be conservative. Return ONLY valid JSON."""


def grade_condition(item: Item, model: str = "llava:13b") -> Item:
    """Assess item condition from its source image."""
    if not item.source_image:
        return item

    path = Path(item.source_image)
    if not path.exists():
        return item

    try:
        import json
        import re

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
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        data = json.loads(cleaned)

        grade_str = data.get("grade", "unknown")
        try:
            item.condition = Condition(grade_str)
        except ValueError:
            grade_map = {
                "new": Condition.NEW_SEALED,
                "mint": Condition.LIKE_NEW,
                "excellent": Condition.LIKE_NEW,
                "fair": Condition.ACCEPTABLE,
                "poor": Condition.FOR_PARTS,
            }
            item.condition = grade_map.get(grade_str.lower(), Condition.UNKNOWN)

        flaws = data.get("flaws", [])
        notes = data.get("notes", "")
        condition_text = notes
        if flaws:
            condition_text += " Flaws: " + "; ".join(flaws)

        if condition_text.strip():
            existing = item.description or ""
            item.description = (
                f"{existing}\n\nCondition: {condition_text.strip()}"
                if existing
                else f"Condition: {condition_text.strip()}"
            )
    except Exception:
        pass

    return item


def grade_conditions(items: list[Item], model: str = "llava:13b") -> list[Item]:
    """Grade conditions for a batch of items."""
    return [grade_condition(item, model=model) for item in items]


def estimate_condition_from_text(description: str) -> Condition:
    """Heuristic condition estimation from text description."""
    desc_lower = description.lower()

    new_keywords = [
        "sealed",
        "new in box",
        "nib",
        "nwt",
        "brand new",
        "factory sealed",
        "shrink",
    ]
    like_new_keywords = ["like new", "mint", "excellent", "pristine", "unread", "unworn"]
    very_good_keywords = ["very good", "great condition", "minimal wear", "light wear"]
    good_keywords = ["good condition", "some wear", "used", "pre-owned", "preowned"]
    acceptable_keywords = ["acceptable", "fair", "worn", "stained", "damaged", "rough"]
    parts_keywords = ["for parts", "as-is", "as is", "broken", "not working", "repair"]

    for keyword in new_keywords:
        if keyword in desc_lower:
            return Condition.NEW_SEALED
    for keyword in like_new_keywords:
        if keyword in desc_lower:
            return Condition.LIKE_NEW
    for keyword in very_good_keywords:
        if keyword in desc_lower:
            return Condition.VERY_GOOD
    for keyword in good_keywords:
        if keyword in desc_lower:
            return Condition.GOOD
    for keyword in acceptable_keywords:
        if keyword in desc_lower:
            return Condition.ACCEPTABLE
    for keyword in parts_keywords:
        if keyword in desc_lower:
            return Condition.FOR_PARTS

    return Condition.UNKNOWN
