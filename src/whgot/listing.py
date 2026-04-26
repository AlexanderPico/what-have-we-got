"""eBay listing generator — turn identified Items into optimized eBay listings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from whgot.schema import Condition, Item, ItemCategory

CATEGORY_MAP: dict[ItemCategory, dict[str, str]] = {
    ItemCategory.BOOK: {"id": "261186", "name": "Books & Magazines > Books"},
    ItemCategory.DVD: {"id": "617", "name": "Movies & TV > DVDs & Blu-ray Discs"},
    ItemCategory.BLURAY: {"id": "617", "name": "Movies & TV > DVDs & Blu-ray Discs"},
    ItemCategory.CD: {"id": "176984", "name": "Music > CDs"},
    ItemCategory.VINYL: {"id": "176985", "name": "Music > Vinyl Records"},
    ItemCategory.VIDEO_GAME: {
        "id": "139973",
        "name": "Video Games & Consoles > Video Games",
    },
    ItemCategory.TOY: {"id": "220", "name": "Toys & Hobbies"},
    ItemCategory.COLLECTIBLE: {"id": "1", "name": "Collectibles"},
    ItemCategory.CLOTHING: {"id": "11450", "name": "Clothing, Shoes & Accessories"},
    ItemCategory.ELECTRONICS: {"id": "293", "name": "Consumer Electronics"},
    ItemCategory.HOUSEHOLD: {"id": "11700", "name": "Home & Garden"},
    ItemCategory.OTHER: {"id": "99", "name": "Everything Else"},
}

EBAY_CONDITION_MAP: dict[Condition, dict[str, str | int]] = {
    Condition.NEW_SEALED: {"id": 1000, "name": "New"},
    Condition.NEW_OPEN: {"id": 1500, "name": "New (Other)"},
    Condition.LIKE_NEW: {"id": 3000, "name": "Like New"},
    Condition.VERY_GOOD: {"id": 4000, "name": "Very Good"},
    Condition.GOOD: {"id": 5000, "name": "Good"},
    Condition.ACCEPTABLE: {"id": 6000, "name": "Acceptable"},
    Condition.FOR_PARTS: {"id": 7000, "name": "For Parts or Not Working"},
    Condition.UNKNOWN: {"id": 5000, "name": "Good"},
}


@dataclass
class EbayListing:
    """A complete eBay listing ready for submission or review."""

    title: str
    description: str
    category_id: str
    category_name: str
    condition_id: int
    condition_name: str
    item_specifics: dict[str, str] = field(default_factory=dict)
    suggested_price: Optional[float] = None
    pricing_strategy: str = "fixed"
    starting_bid: Optional[float] = None
    buy_it_now: Optional[float] = None
    source_item: Optional[Item] = field(default=None, repr=False)

    def to_dict(self) -> dict:
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
            "source_item_name": self.source_item.name if self.source_item else None,
        }


def _generate_title_template(item: Item) -> str:
    """Generate an eBay title using templates without an LLM."""
    parts: list[str] = []

    if item.metadata.brand:
        parts.append(item.metadata.brand)
    if item.metadata.author:
        parts.append(item.metadata.author)
    if item.metadata.franchise:
        parts.append(item.metadata.franchise)

    parts.append(item.name)

    if item.metadata.format:
        parts.append(item.metadata.format)
    if item.metadata.edition:
        parts.append(item.metadata.edition)
    if item.metadata.color and item.category in {
        ItemCategory.CLOTHING,
        ItemCategory.ELECTRONICS,
    }:
        parts.append(item.metadata.color)
    if item.metadata.size and item.category == ItemCategory.CLOTHING:
        parts.append(f"Size {item.metadata.size}")
    if item.metadata.model:
        parts.append(item.metadata.model)
    if item.metadata.year_published:
        parts.append(str(item.metadata.year_published))

    if item.condition == Condition.NEW_SEALED:
        parts.append("NEW SEALED")
    elif item.condition == Condition.NEW_OPEN:
        parts.append("NEW")
    elif item.condition == Condition.LIKE_NEW:
        parts.append("Like New")

    if item.identifiers.isbn13:
        parts.append(item.identifiers.isbn13)
    elif item.identifiers.isbn:
        parts.append(item.identifiers.isbn)

    title = " ".join(parts)
    if len(title) > 80:
        title = title[:80].rsplit(" ", 1)[0]
    return title


def _generate_title_llm(item: Item, model: str) -> str:
    """Generate an optimized eBay title using a local LLM."""
    try:
        import ollama

        prompt = (
            "Generate an eBay listing title for this item. "
            "The title MUST be 80 characters or less. "
            "Pack in the most searchable keywords: brand, product name, model, "
            "key specs, condition. Return ONLY the title text.\n\n"
            f"Item: {item.name}\n"
            f"Category: {item.category.value}\n"
            f"Brand: {item.metadata.brand or 'unknown'}\n"
            f"Author: {item.metadata.author or 'n/a'}\n"
            f"Condition: {item.condition.value}\n"
            f"Format: {item.metadata.format or 'n/a'}\n"
            f"ISBN: {item.identifiers.isbn13 or item.identifiers.isbn or 'n/a'}"
        )
        text_model = model.replace("llava", "llama3.1").replace("moondream", "llama3.1")
        response = ollama.chat(
            model=text_model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3, "num_predict": 128},
        )
        title = response["message"]["content"].strip().strip('"').strip("'")
        if len(title) > 80:
            title = title[:80].rsplit(" ", 1)[0]
        if len(title) < 10:
            return _generate_title_template(item)
        return title
    except Exception:
        return _generate_title_template(item)


def _generate_description(item: Item) -> str:
    """Generate a markdown description for the eBay listing body."""
    lines = [f"# {item.name}", ""]

    if item.description:
        lines.extend([item.description, ""])

    lines.extend(["## Item Details", ""])

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
        lines.append(f"- **ISBN:** {item.identifiers.isbn13 or item.identifiers.isbn}")
    if item.identifiers.upc:
        lines.append(f"- **UPC:** {item.identifiers.upc}")

    lines.extend(["", f"## Condition: {EBAY_CONDITION_MAP[item.condition]['name']}", ""])

    if item.condition == Condition.NEW_SEALED:
        lines.append("Brand new, factory sealed. Never opened.")
    elif item.condition == Condition.LIKE_NEW:
        lines.append("Excellent condition, minimal to no signs of use.")
    elif item.condition in {Condition.VERY_GOOD, Condition.GOOD}:
        lines.append("Pre-owned in good condition. See photos for details.")
    elif item.condition == Condition.FOR_PARTS:
        lines.append("Sold as-is for parts or repair. See description for known issues.")

    if item.pricing.warning:
        lines.extend(["", f"Pricing note: {item.pricing.warning}"])

    lines.extend(["", "---", "*Listed with whgot*"])
    return "\n".join(lines)


def _generate_item_specifics(item: Item) -> dict[str, str]:
    """Generate eBay item specifics."""
    specifics: dict[str, str] = {}
    cond = EBAY_CONDITION_MAP.get(item.condition, EBAY_CONDITION_MAP[Condition.UNKNOWN])
    specifics["Condition"] = str(cond["name"])

    if item.metadata.brand:
        specifics["Brand"] = item.metadata.brand

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
        specifics["Language"] = "English"
    elif item.category in {ItemCategory.DVD, ItemCategory.BLURAY}:
        if item.metadata.director:
            specifics["Director"] = item.metadata.director
        if item.metadata.genre:
            specifics["Genre"] = item.metadata.genre
        if item.metadata.format:
            specifics["Format"] = item.metadata.format
        else:
            specifics["Format"] = (
                "DVD" if item.category == ItemCategory.DVD else "Blu-ray"
            )
        if item.identifiers.upc:
            specifics["UPC"] = item.identifiers.upc
        specifics["Region Code"] = "1"
    elif item.category in {ItemCategory.TOY, ItemCategory.COLLECTIBLE}:
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
            specifics["Packaging"] = (
                "Original (Unopened)"
                if item.metadata.in_packaging
                else "Original (Opened)"
            )
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


def _suggest_pricing(item: Item) -> tuple[str, Optional[float], Optional[float]]:
    """Suggest fixed price or auction strategy based on available pricing."""
    median = item.pricing.median
    low = item.pricing.low
    high = item.pricing.high

    if not median and not low:
        return "fixed", 9.99, None

    if median:
        spread = (high - low) / median if high and low and median > 0 else 0
        if spread > 1.0:
            start = round(max(0.99, (low or median) * 0.6), 2)
            buy_it_now = round((high or median) * 0.85, 2) if high else None
            return "auction", start, buy_it_now
        return "fixed", round(median * 0.95, 2), None

    midpoint = (low + high) / 2 if low and high else low or high or 9.99
    return "fixed", round(midpoint, 2), None


def generate_listing(
    item: Item,
    use_llm: bool = True,
    model: str = "llava:13b",
) -> EbayListing:
    """Generate a complete eBay listing from an identified Item."""
    title = _generate_title_llm(item, model) if use_llm else _generate_title_template(item)
    category = CATEGORY_MAP.get(item.category, CATEGORY_MAP[ItemCategory.OTHER])
    cond = EBAY_CONDITION_MAP.get(item.condition, EBAY_CONDITION_MAP[Condition.UNKNOWN])
    description = _generate_description(item)
    item_specifics = _generate_item_specifics(item)
    strategy, price, buy_it_now = _suggest_pricing(item)

    return EbayListing(
        title=title,
        description=description,
        category_id=category["id"],
        category_name=category["name"],
        condition_id=int(cond["id"]),
        condition_name=str(cond["name"]),
        item_specifics=item_specifics,
        suggested_price=price,
        pricing_strategy=strategy,
        starting_bid=price if strategy == "auction" else None,
        buy_it_now=buy_it_now,
        source_item=item,
    )


def generate_listings(
    items: list[Item],
    use_llm: bool = True,
    model: str = "llava:13b",
) -> list[EbayListing]:
    """Generate eBay listings for a batch of items."""
    return [generate_listing(item, use_llm=use_llm, model=model) for item in items]
