"""CLI smoke tests."""

import json
from pathlib import Path

from typer.testing import CliRunner

from whgot.cli import app

runner = CliRunner()


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "whgot 0.1.0" in result.stdout


def test_identify_missing_file():
    result = runner.invoke(app, ["identify", "missing.jpg"])
    assert result.exit_code == 1
    assert "Image not found" in result.stdout


def test_scan_missing_directory():
    result = runner.invoke(app, ["scan", "missing-dir"])
    assert result.exit_code == 1
    assert "Not a directory" in result.stdout


def test_price_json_output(tmp_path: Path, monkeypatch):
    import whgot.pricing

    input_path = tmp_path / "items.json"
    input_path.write_text(
        json.dumps(
            [
                {
                    "name": "Test Item",
                    "category": "other",
                    "confidence": 0.5,
                }
            ]
        )
    )

    monkeypatch.setattr(whgot.pricing, "enrich_prices", lambda items, use_cache=True: items)

    result = runner.invoke(app, ["price", str(input_path), "--no-cache", "-f", "json"])
    assert result.exit_code == 0
    assert '"name": "Test Item"' in result.stdout
