"""eBay listing generator — turn identified Items into optimized eBay listings.

Generates:
- 80-char keyword-optimized title
- Item specifics (category-dependent key-value pairs)
- Markdown description body
- Suggested pricing strategy (auction vs. fixed, starting price)
- eBay category ID suggestion

Uses a local LLM via ollama for title optimization and description writing.
Falls back to template-based generation if ollama is unavailable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from whgot.schema import Condition, Item, ItemCategory


# --- eBay Category Mapping ---

# Simplified top-level category map. eBay has ~35k leaf categories;
# this covers the most common resale categories. For production,
# use the eBay Taxonomy API to get precise leaf category IDs.
CATEGORY_MAP: dict[ItemCategory, dict[str, str]] = {
    ItemCategory.BOOK: {
        "id": "261186",
        "name": "Books & Magazines > Books",
    },
    ItemCategory.DVD: {
        "id": "617",
        "name": "Movies & TV > DVDs & Blu-ray Discs",
    },
    ItemCategory.BLURAY: {
        "id": "617",
        "name": "Movies & TV > DVDs & Blu-ray Discs",
    },
    ItemCategory.CD: {
        "id": "176984",
        "name": "Music > CDs",
    },
    ItemCategory.VINYL: {
        "id": "176985",
        "name": "Music > Vinyl Records",
    },
    ItemCategory.VIDEO_GAME: {
        "id": "139973",
        "name": "Video Games & Consoles > Video Games",
    },
    ItemCategory.TOY: {
        "id": "220",
        "name": "Toys & Hobbies",
    },
    ItemCategory.COLLECTIBLE: {
        "id": "1",
        "name": "Collectibles",
    },
    ItemCategory.CLOTHING: {
        "id": "11450",
        "name": "Clothing, Shoes & Accessories",
    },
    ItemCategory.ELECTRONICS: {
        "id": "293",
        "name": "Consumer Electronics",
    },
    ItemCategory.HOUSEHOLD: {
        "id": "11700",
        "name": "Home & Garden",
    },
    ItemCategory.OTHER: {
        "id": "99",
        "name": "Everything Else",
    },
}


# --- Condition Mapping ---

# eBay condition IDs mapped from our internal condition enum
EBAY_CONDITION_MAP: dict[Condition, dict[str, str | int]] = {
    Condition.NEW_SEALED: {"id": 1000, "name": "New"},
    Condition.NEW_OPEN: {"id": 1500, "name": "New (Other)"},
    Condition.LIKE_NEW: {"id": 3000, "name": "Like New"},
    Condition.VERY_GOOD: {"id": 4000, "name": "Very Good"},
    Condition.GOOD: {"id": 5000, "name": "Good"},
    Condition.ACCEPTABLE: {"id": 6000, "name": "Acceptable"},
    Condition.FOR_PARTS: {"id": 7000, "name": "For Parts or Not Working"},
    Condition.UNKNOWN: {"id": 5000, "name": "Good"},  # conservative default
}


@dataclass
class EbayListing:
    """A complete eBay listing ready for submission or review."""

    title: str  # max 80 chars, keyword-optimized
    description: str  # markdown/HTML body
    category_id: str
    category_name: str
    condition_id: int
    condition_name: str
    item_specifics: dict[str, str] = field(default_factory=dict)
    suggested_price: Optional[float] = None
    pricing_strategy: str = "fixed"  # "fixed" or "auction"
    starting_bid: Optional[float] = None
    buy_it_now: Optional[float] = None
    source_item: Optional[Item] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON output, excluding source_item."""
        return {
            "title": self.title,
            "description": self.description,
            "category_id": self.category_id,
            "category_name": self.category_name,
            "condition_id": self.condition_id,
            "condition_name": self.condition_name,
            "item_specifics": self.item_specifics,
            "suggested_price": self.suggested_price,
            "pricing_strategy": self.pricing_strategy,
            "starting_bid": self.starting_bid,
            "buy_it_now": self.buy_it_now,
        }


# --- Title Generation ---


def _generate_title_template(item: Item) -> str:
    """Generate an eBay title using templates (no LLM needed).

    eBay titles are max 80 characters. Strategy: pack in the most
    searchable keywords — brand, name, specifics, condition.
    """
    parts: list[str] = []

    # Brand/author/franchise first (most searched)
    if item.metadata.brand:
        parts.append(item.metadata.brand)
    if item.metadata.author:
        parts.append(item.metadata.author)
    if item.metadata.franchise:
        parts.append(item.metadata.franchise)

    # Core item name
    parts.append(item.name)

    # Key specifics
    if item.metadata.format:
        parts.append(item.metadata.format)
    if item.metadata.edition:
        parts.append(item.metadata.edition)
    if item.metadata.color and item.category in (ItemCategory.CLOTHING, ItemCategory.ELECTRONICS):
        parts.append(item.metadata.color)
    if item.metadata.size and item.category == ItemCategory.CLOTHING:
        parts.append(f"Size {item.metadata.size}")
    if item.metadata.model:
        parts.append(item.metadata.model)
    if item.metadata.year_published:
        parts.append(str(item.metadata.year_published))

    # Condition tag
    if item.condition == Condition.NEW_SEALED:
        parts.append("NEW SEALED")
    elif item.condition == Condition.NEW_OPEN:
        parts.append("NEW")
    elif item.condition == Condition.LIKE_NEW:
        parts.append("Like New")

    # ISBN/UPC for exact-match searches
    if item.identifiers.isbn13:
        parts.append(item.identifiers.isbn13)
    elif item.identifiers.isbn:
        parts.append(item.identifiers.isbn)

    # Join and truncate to 80 chars
    title = " ".join(parts)
    if len(title) > 80:
        # Truncate at last word boundary before 80
        title = title[:80].rsplit(" ", 1)[0]

    return title


def _generate_title_llm(item: Item, model: str) -> str:
    """Generate an optimized eBay title using a local LLM.

    Falls back to template if ollama isn't available.
    """
    try:
        import ollama

        prompt = f"""Generate an eBay listing title for this item. The title MUST be 80 characters or less.
Pack in the most searchable keywords: brand, product name, model, key specs, condition.
Do NOT use special characters, emojis, or ALL CAPS (except brand names that are normally capitalized).
Return ONLY the title text, nothing else.

Item: {item.name}
Category: {item.category.value}
Brand: {item.metadata.brand or 'unknown'}
Author: {item.metadata.author or 'n/a'}
Condition: {item.condition.value}
Format: {item.metadata.format or 'n/a'}
ISBN: {item.identifiers.isbn13 or item.identifiers.isbn or 'n/a'}"""

        # Use a text model (don't need vision for this)
        text_model = model.replace("llava", "llama3.1").replace("moondream", "llama3.1")

        response = ollama.chat(
            model=text_model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3, "num_predict": 128},
        )
        title = response["message"]["content"].strip().strip('"').strip("'")

        # Enforce 80-char limit
        if len(title) > 80:
            title = title[:80].rsplit(" ", 1)[0]
        if len(title) < 10:
            # Model gave garbage — fall back
            return _generate_title_template(item)
        return title

    except Exception:
        return _generate_title_template(item)


# --- Description Generation ---


def _generate_description(item: Item) -> str:
    """Generate a markdown description for the eBay listing body."""
    lines: list[str] = []

    lines.append(f"# {item.name}")
    lines.append("")

    if item.description:
        lines.append(item.description)
        lines.append("")

    # Item details section
    lines.append("## Item Details")
    lines.append("")

    details: list[tuple[str, str]] = []
    if item.metadata.author:
        details.append(("Author", item.metadata.author))
    if item.metadata.brand:
        details.append(("Brand", item.metadata.brand))
    if item.metadata.manufacturer:
        details.append(("Manufacturer", item.metadata.manufacturer))
    if item.metadata.publisher:
        details.append(("Publisher", item.metadata.publisher))
    if item.metadata.format:
        details.append(("Format", item.metadata.format))
    if item.metadata.edition:
        details.append(("Edition", item.metadata.edition))
    if item.metadata.year_published:
        details.append(("Year", str(item.metadata.year_published)))
    if item.metadata.director:
        details.append(("Director", item.metadata.director))
    if item.metadata.artist:
        details.append(("Artist", item.metadata.artist))
    if item.metadata.genre:
        details.append(("Genre", item.metadata.genre))
    if item.metadata.color:
        details.append(("Color", item.metadata.color))
    if item.metadata.size:
        details.append(("Size", item.metadata.size))
    if item.metadata.material:
        details.append(("Material", item.metadata.material))
    if item.metadata.franchise:
        details.append(("Franchise", item.metadata.franchise))
    if item.metadata.character:
        details.append(("Character", item.metadata.character))
    if item.metadata.scale:
        details.append(("Scale", item.metadata.scale))

    for label, value in details:
        lines.append(f"- **{label}:** {value}")

    if item.identifiers.isbn13 or item.identifiers.isbn:
        isbn = item.identifiers.isbn13 or item.identifiers.isbn
        lines.append(f"- **ISBN:** {isbn}")
    if item.identifiers.upc:
        lines.append(f"- **UPC:** {item.identifiers.upc}")

    lines.append("")

    # Condition section
    cond = EBAY_CONDITION_MAP.get(item.condition, EBAY_CONDITION_MAP[Condition.UNKNOWN])
    lines.append(f"## Condition: {cond['name']}")
    lines.append("")

    if item.condition == Condition.NEW_SEALED:
        lines.append("Brand new, factory sealed. Never opened.")
    elif item.condition == Condition.LIKE_NEW:
        lines.append("Excellent condition, minimal to no signs of use.")
    elif item.condition in (Condition.VERY_GOOD, Condition.GOOD):
        lines.append("Pre-owned in good condition. See photos for details.")
    elif item.condition == Condition.FOR_PARTS:
        lines.append("Sold as-is for parts or repair. See description for known issues.")

    lines.append("")
    lines.append("---")
    lines.append("*Listed with whgot*")

    return "\n".join(lines)


# --- Item Specifics ---


def _generate_item_specifics(item: Item) -> dict[str, str]:
    """Generate eBay item specifics (key-value pairs shown in listing details)."""
    specifics: dict[str, str] = {}

    # Universal specifics
    cond = EBAY_CONDITION_MAP.get(item.condition, EBAY_CONDITION_MAP[Condition.UNKNOWN])
    specifics["Condition"] = str(cond["name"])

    if item.metadata.brand:
        specifics["Brand"] = item.metadata.brand

    # Category-specific
    if item.category == ItemCategory.BOOK:
        if item.metadata.author:
            specifics["Author"] = item.metadata.author
        if item.metadata.publisher:
            specifics["Publisher"] = item.metadata.publisher
        if item.metadata.format:
            specifics["Format"] = item.metadata.format
        if item.metadata.year_published:
            specifics["Publication Year"] = str(item.metadata.year_published)
        if item.identifiers.isbn13:
            specifics["ISBN"] = item.identifiers.isbn13
        elif item.identifiers.isbn:
            specifics["ISBN"] = item.identifiers.isbn
        specifics["Language"] = "English"  # default, would need NLP to detect

    elif item.category in (ItemCategory.DVD, ItemCategory.BLURAY):
        if item.metadata.director:
            specifics["Director"] = item.metadata.director
        if item.metadata.genre:
            specifics["Genre"] = item.metadata.genre
        if item.metadata.format:
            specifics["Format"] = item.metadata.format
        else:
            specifics["Format"] = "DVD" if item.category == ItemCategory.DVD else "Blu-ray"
        if item.identifiers.upc:
            specifics["UPC"] = item.identifiers.upc
        specifics["Region Code"] = "1"  # US default

    elif item.category in (ItemCategory.TOY, ItemCategory.COLLECTIBLE):
        if item.metadata.franchise:
            specifics["Franchise"] = item.metadata.franchise
        if item.metadata.character:
            specifics["Character"] = item.metadata.character
        if item.metadata.manufacturer:
            specifics["Manufacturer"] = item.metadata.manufacturer
        if item.metadata.scale:
            specifics["Scale"] = item.metadata.scale
        if item.metadata.era:
            specifics["Era"] = item.metadata.era
        if item.metadata.in_packaging is not None:
            specifics["Packaging"] = "Original (Opened)" if not item.metadata.in_packaging else "Original (Unopened)"

    elif item.category == ItemCategory.CLOTHING:
        if item.metadata.size:
            specifics["Size"] = item.metadata.size
        if item.metadata.color:
            specifics["Color"] = item.metadata.color
        if item.metadata.material:
            specifics["Material"] = item.metadata.material

    elif item.category == ItemCategory.ELECTRONICS:
        if item.metadata.model:
            specifics["Model"] = item.metadata.model
        if item.metadata.color:
            specifics["Color"] = item.metadata.color
        if item.metadata.manufacturer:
            specifics["Manufacturer"] = item.metadata.manufacturer

    return specifics


# --- Pricing Strategy ---


def _suggest_pricing(item: Item) -> tuple[str, Optional[float], Optional[float]]:
    """Suggest pricing strategy based on item data.

    Returns:
        (strategy, starting_bid_or_price, buy_it_now_or_none)
        strategy: "fixed" or "auction"
    """
    median = item.pricing.median
    low = item.pricing.low
    high = item.pricing.high

    if not median and not low:
        # No pricing data — default to low fixed price
        return "fixed", 9.99, None

    if median:
        spread = (high - low) / median if high and low and median > 0 else 0

        if spread > 1.0:
            # Wide price spread — auction might discover true value
            # Start at ~60% of low to attract bidders
            start = round(max(0.99, low * 0.6), 2)
            return "auction", start, round(high * 0.85, 2)
        else:
            # Narrow spread — fixed price near median
            return "fixed", round(median * 0.95, 2), None
    else:
        # Have range but no median
        mid = (low + high) / 2 if low and high else low or high or 9.99
        return "fixed", round(mid, 2), None


# --- Public API ---


def generate_listing(
    item: Item,
    use_llm: bool = True,
    model: str = "llava:13b",
) -> EbayListing:
    """Generate a complete eBay listing from an identified Item.

    Args:
        item: Identified and optionally price-enriched Item.
        use_llm: If True, use ollama LLM for title optimization.
                 If False (or if ollama unavailable), use templates.
        model: Ollama model name for LLM-based title generation.

    Returns:
        EbayListing with all fields populated.
    """
    # Title
    if use_llm:
        title = _generate_title_llm(item, model)
    else:
        title = _generate_title_template(item)

    # Category
    cat = CATEGORY_MAP.get(item.category, CATEGORY_MAP[ItemCategory.OTHER])

    # Condition
    cond = EBAY_CONDITION_MAP.get(item.condition, EBAY_CONDITION_MAP[Condition.UNKNOWN])

    # Description
    description = _generate_description(item)

    # Item specifics
    item_specifics = _generate_item_specifics(item)

    # Pricing strategy
    strategy, price, bin_price = _suggest_pricing(item)

    return EbayListing(
        title=title,
        description=description,
        category_id=cat["id"],
        category_name=cat["name"],
        condition_id=int(cond["id"]),
        condition_name=str(cond["name"]),
        item_specifics=item_specifics,
        suggested_price=price,
        pricing_strategy=strategy,
        starting_bid=price if strategy == "auction" else None,
        buy_it_now=bin_price,
        source_item=item,
    )


def generate_listings(
    items: list[Item],
    use_llm: bool = True,
    model: str = "llava:13b",
) -> list[EbayListing]:
    """Generate eBay listings for a batch of items."""
    return [generate_listing(item, use_llm=use_llm, model=model) for item in items]
