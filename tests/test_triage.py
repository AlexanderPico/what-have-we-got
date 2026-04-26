"""Tests for heuristic triage scoring."""

from whgot.schema import Condition, Identifiers, Item, ItemCategory, PriceEstimate
from whgot.triage import assess_item


def test_high_value_item_gets_worth_checking():
    item = Item(
        name="Sony Walkman",
        category=ItemCategory.ELECTRONICS,
        confidence=0.9,
        condition=Condition.LIKE_NEW,
        identifiers=Identifiers(upc="123456789012"),
        pricing=PriceEstimate(median=120.0, high=160.0, low=80.0),
    )
    triage = assess_item(item)
    assert triage.badge.value == "worth_checking"
    assert triage.score >= 55


def test_low_signal_item_can_be_skip():
    item = Item(name="Unknown cable", confidence=0.2)
    triage = assess_item(item)
    assert triage.badge.value == "skip"
