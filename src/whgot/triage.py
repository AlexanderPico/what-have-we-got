"""Heuristic triage scoring for seller review workflows."""

from __future__ import annotations

from whgot.schema import Condition, Item, ItemCategory, TriageAssessment, TriageBadge

HIGH_SIGNAL_CATEGORIES = {
    ItemCategory.BOOK,
    ItemCategory.DVD,
    ItemCategory.BLURAY,
    ItemCategory.TOY,
    ItemCategory.COLLECTIBLE,
    ItemCategory.ELECTRONICS,
}


def assess_item(item: Item) -> TriageAssessment:
    """Assign a lightweight heuristic score and badge to an item."""
    score = 0.0
    reasons: list[str] = []

    if item.category in HIGH_SIGNAL_CATEGORIES:
        score += 10
        reasons.append(f"priority category: {item.category.value}")

    if item.pricing.median:
        median = item.pricing.median
        if median >= 100:
            score += 45
            reasons.append("strong price band")
        elif median >= 40:
            score += 30
            reasons.append("solid price band")
        elif median >= 15:
            score += 18
            reasons.append("modest resale value")
        else:
            score += 6
            reasons.append("low price band")
    elif item.pricing.high:
        if item.pricing.high >= 50:
            score += 18
            reasons.append("high-end estimate present")
        else:
            score += 5
            reasons.append("partial pricing only")
    else:
        reasons.append("no pricing yet")

    if item.identifiers.isbn13 or item.identifiers.upc or item.identifiers.asin:
        score += 12
        reasons.append("strong identifier match")
    elif item.identifiers.isbn or item.identifiers.ean:
        score += 8
        reasons.append("some identifier support")

    confidence_boost = round(item.confidence * 20, 2)
    if confidence_boost:
        score += confidence_boost
        reasons.append(f"model confidence {item.confidence:.0%}")

    if item.condition in {Condition.NEW_SEALED, Condition.NEW_OPEN, Condition.LIKE_NEW}:
        score += 10
        reasons.append("strong condition")
    elif item.condition in {Condition.ACCEPTABLE, Condition.FOR_PARTS}:
        score -= 10
        reasons.append("condition drag")

    if item.pricing.warning:
        score -= 6
        reasons.append("pricing is heuristic")

    if item.category == ItemCategory.BOOK and item.metadata.author:
        score += 4
        reasons.append("author metadata present")

    score = max(0.0, min(100.0, score))

    if score >= 55:
        badge = TriageBadge.WORTH_CHECKING
    elif score >= 25:
        badge = TriageBadge.MAYBE
    else:
        badge = TriageBadge.SKIP

    return TriageAssessment(score=round(score, 2), badge=badge, reasons=reasons)


def assess_items(items: list[Item]) -> list[Item]:
    """Apply triage assessment to a batch of items in place."""
    for item in items:
        item.triage = assess_item(item)
    return items
