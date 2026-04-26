"""Canonical item schema for identified items.

This is the core data model that all pipeline stages produce and consume.
Designed to cover books, media, clothing, electronics, toys, and collectibles.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ItemCategory(str, Enum):
    """Top-level item categories relevant to resale."""

    BOOK = "book"
    DVD = "dvd"
    BLURAY = "bluray"
    CD = "cd"
    VINYL = "vinyl"
    VIDEO_GAME = "video_game"
    TOY = "toy"
    COLLECTIBLE = "collectible"
    CLOTHING = "clothing"
    ELECTRONICS = "electronics"
    HOUSEHOLD = "household"
    OTHER = "other"


class Condition(str, Enum):
    """Standardized condition grades, roughly aligned with eBay's scale."""

    NEW_SEALED = "new_sealed"
    NEW_OPEN = "new_open"
    LIKE_NEW = "like_new"
    VERY_GOOD = "very_good"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    FOR_PARTS = "for_parts"
    UNKNOWN = "unknown"


class TriageBadge(str, Enum):
    """Fast seller-facing prioritization badge."""

    WORTH_CHECKING = "worth_checking"
    MAYBE = "maybe"
    SKIP = "skip"


class Identifiers(BaseModel):
    """Known identifiers for the item. All optional — we populate what we can."""

    isbn: Optional[str] = None
    isbn13: Optional[str] = None
    upc: Optional[str] = None
    ean: Optional[str] = None
    asin: Optional[str] = None
    ebay_category_id: Optional[str] = None


class PriceEstimate(BaseModel):
    """Price estimate with source attribution and light provenance."""

    low: Optional[float] = None
    high: Optional[float] = None
    median: Optional[float] = None
    source: Optional[str] = None
    last_updated: Optional[datetime] = None
    comp_count: Optional[int] = None
    query: Optional[str] = None
    source_details: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    warning: Optional[str] = None


class TriageAssessment(BaseModel):
    """Heuristic prioritization for seller review workflows."""

    score: float = Field(default=0.0, ge=0.0, le=100.0)
    badge: TriageBadge = Field(default=TriageBadge.MAYBE)
    reasons: list[str] = Field(default_factory=list)


class ItemMetadata(BaseModel):
    """Category-dependent metadata. Not all fields apply to all categories."""

    brand: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    material: Optional[str] = None
    era: Optional[str] = None
    genre: Optional[str] = None
    format: Optional[str] = None

    # Book-specific
    author: Optional[str] = None
    publisher: Optional[str] = None
    edition: Optional[str] = None
    year_published: Optional[int] = None

    # Media-specific
    director: Optional[str] = None
    artist: Optional[str] = None
    runtime_minutes: Optional[int] = None

    # Toy/collectible-specific
    franchise: Optional[str] = None
    character: Optional[str] = None
    scale: Optional[str] = None
    in_packaging: Optional[bool] = None


class Item(BaseModel):
    """A single identified item — the canonical unit of the whgot pipeline."""

    name: str = Field(..., description="Human-readable item name/title")
    category: ItemCategory = Field(default=ItemCategory.OTHER)
    condition: Condition = Field(default=Condition.UNKNOWN)
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Model confidence in identification (0-1)",
    )
    description: Optional[str] = Field(
        default=None,
        description="Free-text description of the item",
    )
    identifiers: Identifiers = Field(default_factory=Identifiers)
    pricing: PriceEstimate = Field(default_factory=PriceEstimate)
    triage: TriageAssessment = Field(default_factory=TriageAssessment)
    metadata: ItemMetadata = Field(default_factory=ItemMetadata)
    source_image: Optional[str] = Field(
        default=None,
        description="Path to the source image, if identified from a photo",
    )
    source_text: Optional[str] = Field(
        default=None,
        description="Original text input, if identified from a text list",
    )

    def summary(self) -> str:
        """One-line summary suitable for terminal output."""
        parts = [self.name]
        if self.metadata.author:
            parts.append(f"by {self.metadata.author}")
        if self.metadata.brand:
            parts.append(f"({self.metadata.brand})")
        if self.condition != Condition.UNKNOWN:
            parts.append(f"[{self.condition.value}]")
        if self.pricing.median:
            parts.append(f"~${self.pricing.median:.2f}")
        if self.triage.badge != TriageBadge.MAYBE or self.triage.score:
            parts.append(f"triage:{self.triage.badge.value}")
        return " — ".join(parts)
