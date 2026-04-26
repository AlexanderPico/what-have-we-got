"""Persistence helpers for saved web sessions under ~/.whgot/sessions."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from whgot.listing import EbayListing
from whgot.schema import Item

DEFAULT_SESSION_ROOT = Path.home() / ".whgot" / "sessions"


class SessionNotFoundError(FileNotFoundError):
    """Raised when a saved session bundle does not exist."""


class SessionStore:
    """Manage saved analysis sessions on local disk."""

    def __init__(self, root: Path = DEFAULT_SESSION_ROOT):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create_session_dir(self) -> tuple[str, Path]:
        session_id = datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{uuid4().hex[:8]}"
        session_dir = self.root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_id, session_dir

    def session_dir(self, session_id: str) -> Path:
        return self.root / session_id

    def list_sessions(self) -> list[dict]:
        sessions: list[dict] = []
        for session_dir in sorted(self.root.iterdir(), reverse=True):
            if not session_dir.is_dir():
                continue
            session_file = session_dir / "session.json"
            if not session_file.exists():
                continue
            try:
                payload = json.loads(session_file.read_text())
            except json.JSONDecodeError:
                continue
            items = payload.get("items", [])
            sessions.append(
                {
                    "session_id": payload.get("session_id", session_dir.name),
                    "saved_at": payload.get("saved_at"),
                    "mode": payload.get("metadata", {}).get("mode", "unknown"),
                    "model": payload.get("metadata", {}).get("model", "unknown"),
                    "item_count": len(items),
                    "priced_count": sum(
                        1 for item in items if item.get("pricing", {}).get("median")
                    ),
                }
            )
        return sessions

    def save_bundle(
        self,
        session_id: str,
        *,
        items: list[Item],
        listings: list[EbayListing],
        metadata: dict,
    ) -> Path:
        session_dir = self.session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "session_id": session_id,
            "saved_at": datetime.now().isoformat(),
            "metadata": metadata,
            "items": [item.model_dump(mode="json", exclude_none=True) for item in items],
            "listings": [listing.to_dict() for listing in listings],
        }
        path = session_dir / "session.json"
        path.write_text(json.dumps(payload, indent=2))
        self.write_csv(session_id, items)
        return path

    def load_bundle(self, session_id: str) -> dict:
        path = self.session_dir(session_id) / "session.json"
        if not path.exists():
            raise SessionNotFoundError(f"Session not found: {session_id}")
        return json.loads(path.read_text())

    def write_csv(self, session_id: str, items: list[Item]) -> Path:
        session_dir = self.session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        path = session_dir / "items.csv"
        rows = []
        for item in items:
            rows.append(
                {
                    "name": item.name,
                    "category": item.category.value,
                    "condition": item.condition.value,
                    "confidence": item.confidence,
                    "price_low": item.pricing.low or "",
                    "price_high": item.pricing.high or "",
                    "price_median": item.pricing.median or "",
                    "price_source": item.pricing.source or "",
                    "triage_badge": item.triage.badge.value,
                    "triage_score": item.triage.score,
                }
            )

        with open(path, "w", newline="") as handle:
            if rows:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            else:
                handle.write("")
        return path
