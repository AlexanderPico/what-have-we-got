# whgot eval

Benchmark data for local identification evaluation.

Record fields:
- `id`
- `category`
- `mode` (`single_image`, `multi_image`, `text_only`)
- `image_path` or `text_input`
- `expected_name`
- `expected_category`
- `expected_key_metadata`
- `acceptable_aliases`
- `source_type` (`local_real`, `synthetic_public`)
- `notes`

Suggested local-real image storage:
- keep image files in a repo-local gitignored directory
- keep manifests committed when they do not expose private photo content
