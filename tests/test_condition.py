"""Tests for the condition grading engine — text-based heuristics."""

from whgot.condition import estimate_condition_from_text
from whgot.schema import Condition


def test_sealed_keywords():
    """Sealed/NIB items should grade as NEW_SEALED."""
    assert estimate_condition_from_text("Brand new factory sealed") == Condition.NEW_SEALED
    assert estimate_condition_from_text("NIB never opened") == Condition.NEW_SEALED
    assert estimate_condition_from_text("Still in shrink wrap") == Condition.NEW_SEALED


def test_like_new_keywords():
    """Mint/excellent items should grade as LIKE_NEW."""
    assert estimate_condition_from_text("Mint condition, barely used") == Condition.LIKE_NEW
    assert estimate_condition_from_text("Like new, no marks") == Condition.LIKE_NEW
    assert estimate_condition_from_text("Excellent, unread") == Condition.LIKE_NEW


def test_good_keywords():
    """Standard used items should grade as GOOD."""
    assert estimate_condition_from_text("Used, good condition") == Condition.GOOD
    assert estimate_condition_from_text("Pre-owned, shows some wear") == Condition.GOOD


def test_for_parts_keywords():
    """Broken/as-is items should grade as FOR_PARTS."""
    assert estimate_condition_from_text("Broken screen, as-is") == Condition.FOR_PARTS
    assert estimate_condition_from_text("For parts only, not working") == Condition.FOR_PARTS


def test_unknown_fallback():
    """Descriptions without condition keywords should return UNKNOWN."""
    assert estimate_condition_from_text("Blue widget model X") == Condition.UNKNOWN
    assert estimate_condition_from_text("") == Condition.UNKNOWN
