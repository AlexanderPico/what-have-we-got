"""Vision integration tests."""

from pathlib import Path

from PIL import Image

from whgot.vision import identify_image


def test_identify_image_requests_json_output(monkeypatch, tmp_path: Path):
    image_path = tmp_path / "sample.jpg"
    Image.new("RGB", (8, 8), color="white").save(image_path)

    captured = {}

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return {
            "message": {
                "content": '[{"name": "Sample Book", "category": "book", "confidence": 0.9}]'
            }
        }

    monkeypatch.setattr("whgot.vision.ollama.chat", fake_chat)

    items = identify_image(image_path, model="test-vision-model", batch_mode=False)

    assert len(items) == 1
    assert captured["model"] == "test-vision-model"
    assert captured["format"] == "json"
