"""Session store and export tests."""

from pathlib import Path

from whgot.listing import generate_listings
from whgot.schema import Item, ItemCategory, PriceEstimate
from whgot.session_store import SessionStore
from whgot.triage import assess_items


def test_session_store_saves_json_and_csv(tmp_path: Path):
    store = SessionStore(root=tmp_path)
    session_id, _ = store.create_session_dir()
    items = assess_items(
        [
            Item(
                name="Saved Item",
                category=ItemCategory.BOOK,
                pricing=PriceEstimate(median=12.0, source="test"),
            )
        ]
    )
    listings = generate_listings(items, use_llm=False)
    store.save_bundle(session_id, items=items, listings=listings, metadata={"mode": "single"})

    bundle = store.load_bundle(session_id)
    assert bundle["session_id"] == session_id
    assert bundle["items"][0]["name"] == "Saved Item"
    assert (tmp_path / session_id / "items.csv").exists()
