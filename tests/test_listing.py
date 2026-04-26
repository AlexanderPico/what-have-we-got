"""Tests for the eBay listing generator."""

from whgot.listing import (
    EbayListing,
    _generate_description,
    _generate_item_specifics,
    _generate_title_template,
    _suggest_pricing,
    generate_listing,
)
from whgot.schema import (
    Condition,
    Identifiers,
    Item,
    ItemCategory,
    ItemMetadata,
    PriceEstimate,
)


def test_title_template_book():
    """Book title should include author, name, and ISBN."""
    item = Item(
        name="The Manga Guide to Relativity",
        category=ItemCategory.BOOK,
        metadata=ItemMetadata(author="Hideo Nitta", format="softcover"),
        identifiers=Identifiers(isbn13="9781593272722"),
    )
    title = _generate_title_template(item)
    assert "Hideo Nitta" in title
    assert "Manga Guide" in title
    assert "9781593272722" in title
    assert len(title) <= 80


def test_title_template_truncation():
    """Very long titles should be truncated at 80 chars on a word boundary."""
    item = Item(
        name="An Extremely Long Item Name That Goes On And On And On About Various Things",
        category=ItemCategory.OTHER,
        metadata=ItemMetadata(
            brand="SuperLongBrandName",
            manufacturer="AnotherLongManufacturerName",
        ),
    )
    title = _generate_title_template(item)
    assert len(title) <= 80


def test_title_template_new_sealed():
    """New sealed items should include NEW SEALED in title."""
    item = Item(
        name="Cool Widget",
        category=ItemCategory.ELECTRONICS,
        condition=Condition.NEW_SEALED,
    )
    title = _generate_title_template(item)
    assert "NEW SEALED" in title


def test_item_specifics_book():
    """Book item specifics should include author, publisher, ISBN."""
    item = Item(
        name="Test Book",
        category=ItemCategory.BOOK,
        metadata=ItemMetadata(
            author="Test Author",
            publisher="Test Publisher",
            year_published=2020,
            format="hardcover",
        ),
        identifiers=Identifiers(isbn13="9780000000000"),
    )
    specifics = _generate_item_specifics(item)
    assert specifics["Author"] == "Test Author"
    assert specifics["Publisher"] == "Test Publisher"
    assert specifics["Publication Year"] == "2020"
    assert specifics["ISBN"] == "9780000000000"


def test_item_specifics_dvd():
    """DVD item specifics should include director, format, region."""
    item = Item(
        name="Test Movie",
        category=ItemCategory.DVD,
        metadata=ItemMetadata(director="Test Director", genre="Sci-Fi"),
        identifiers=Identifiers(upc="012345678901"),
    )
    specifics = _generate_item_specifics(item)
    assert specifics["Director"] == "Test Director"
    assert specifics["Genre"] == "Sci-Fi"
    assert specifics["UPC"] == "012345678901"
    assert specifics["Region Code"] == "1"


def test_item_specifics_toy_packaging():
    """Toy specifics should include packaging state."""
    item = Item(
        name="Action Figure",
        category=ItemCategory.TOY,
        metadata=ItemMetadata(franchise="Star Wars", character="Darth Vader", in_packaging=True),
    )
    specifics = _generate_item_specifics(item)
    assert specifics["Franchise"] == "Star Wars"
    assert "Unopened" in specifics["Packaging"]


def test_description_contains_details():
    """Generated description should include all item metadata."""
    item = Item(
        name="Descartes' Error",
        category=ItemCategory.BOOK,
        description="Softcover, good spine, slight yellowing on edges",
        condition=Condition.VERY_GOOD,
        metadata=ItemMetadata(
            author="Antonio Damasio",
            publisher="Penguin Books",
            year_published=1994,
        ),
    )
    desc = _generate_description(item)
    assert "Descartes' Error" in desc
    assert "Antonio Damasio" in desc
    assert "1994" in desc
    assert "Very Good" in desc


def test_pricing_strategy_narrow_spread():
    """Narrow price spread should suggest fixed pricing."""
    item = Item(
        name="Common Book",
        pricing=PriceEstimate(low=5.0, high=8.0, median=6.5),
    )
    strategy, price, bin_price = _suggest_pricing(item)
    assert strategy == "fixed"
    assert bin_price is None
    assert price is not None


def test_pricing_strategy_wide_spread():
    """Wide price spread should suggest auction."""
    item = Item(
        name="Variable Collectible",
        pricing=PriceEstimate(low=5.0, high=100.0, median=30.0),
    )
    strategy, price, bin_price = _suggest_pricing(item)
    assert strategy == "auction"
    assert price is not None  # starting bid
    assert bin_price is not None  # buy it now


def test_pricing_strategy_no_data():
    """No pricing data should default to $9.99 fixed."""
    item = Item(name="Unknown Thing")
    strategy, price, bin_price = _suggest_pricing(item)
    assert strategy == "fixed"
    assert price == 9.99


def test_generate_listing_full():
    """Full listing generation should produce all required fields."""
    item = Item(
        name="Blade Runner: The Director's Cut",
        category=ItemCategory.DVD,
        condition=Condition.GOOD,
        metadata=ItemMetadata(director="Ridley Scott", genre="Sci-Fi"),
        identifiers=Identifiers(upc="085391631729"),
        pricing=PriceEstimate(low=4.0, high=12.0, median=7.5),
    )
    listing = generate_listing(item, use_llm=False)

    assert isinstance(listing, EbayListing)
    assert len(listing.title) <= 80
    assert listing.category_id == "617"
    assert listing.condition_id == 5000
    assert listing.suggested_price is not None
    assert "Ridley Scott" in listing.description
    assert listing.item_specifics.get("Director") == "Ridley Scott"


def test_listing_to_dict():
    """Listing serialization should not include source_item object, but keep source item name."""
    item = Item(name="Test")
    listing = generate_listing(item, use_llm=False)
    data = listing.to_dict()
    assert "source_item" not in data
    assert data["source_item_name"] == "Test"
    assert "title" in data
    assert "category_id" in data
