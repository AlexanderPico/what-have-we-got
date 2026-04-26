# whgot benchmark schema

Minimal benchmark manifest shape:

```json
{
  "id": "electronics-001",
  "category": "electronics",
  "mode": "single_image",
  "image_path": "local-real-images/electronics/walkman-001.jpg",
  "expected_name": "Sony Walkman WM-FX195",
  "expected_category": "electronics",
  "expected_key_metadata": {
    "manufacturer": "Sony",
    "model": "WM-FX195"
  },
  "acceptable_aliases": ["Sony Walkman"],
  "source_type": "local_real",
  "notes": "Front-facing product photo"
}
```

Use `text_input` instead of `image_path` for text-only eval samples.
