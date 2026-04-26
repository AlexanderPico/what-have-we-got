# whgot Web UI + Reliability Roadmap Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Turn `whgot` from a passing-test CLI prototype into a reliable local-first seller research tool with a minimal web UI, broad enough to support overnight execution while staying focused on identification, pricing, listing drafts, and spreadsheet export.

**Architecture:** Keep the existing `Item` schema and CLI pipeline as the canonical backend contract. Add a thin local web app layer over the current Python modules instead of forking logic into a separate prototype stack. Prioritize reliability and eval infrastructure first, then add a lightweight local web surface that reuses the same identification, pricing, condition, and listing code paths.

**Tech Stack:** Python 3.12, Typer, Pydantic v2, Rich, httpx, Ollama, Pillow, pytest, Ruff, plus a small local web layer (preferred: FastAPI + simple server-rendered HTML/htmx or a very thin JS frontend) using only free/local dependencies.

---

## User decisions already locked

- Primary product target: seller-facing local web app
- Priority categories: books/media, toys/collectibles, electronics
- v1 scope: identify + price + listing draft + web UI
- No direct posting; listing drafts + spreadsheet exports only
- Pricing source policy: free/public only unless blocked
- Pricing preference: broad coverage over tight trust for v1
- Photo use case: both single-item and multi-item images matter
- Main use case: individuals working at home / second-hand shopping, not estate-sale swarm mode
- Benchmark corpus: both local real examples and synthetic/public examples
- Overnight emphasis: reliability, evaluation/vision quality, and web UI

## Current grounded repo status

Verified on 2026-04-22:
- Editable install works in a Python 3.12 venv
- `python -m pytest -q` passes: 29 passed
- `python -m compileall src` passes
- `ruff check src tests` fails with 32 issues
- Existing in-repo `.venv` may point to Python 3.9.6, which is below the package requirement
- Current repo already implements:
  - canonical schema
  - Ollama vision/text identification
  - pricing cache + OpenLibrary + heuristic eBay scrape
  - listing generation
  - condition grading
  - CLI commands for identify/scan/ingest/price/listing/grade/version

## Product direction for this phase

This phase should produce a tool that helps a seller answer:
1. what is this item likely to be?
2. is it likely worth attention?
3. what rough comps / price band do I have?
4. what would a usable listing draft look like?
5. can I review many candidate items quickly in a browser?

Not in scope for this phase:
- direct marketplace posting
- heavy cloud dependencies
- mobile-native app
- team / swarm workflow
- deep inventory accounting unless required to support UI review flow

---

## Workstreams

1. Reliability and developer ergonomics
2. Evaluation corpus and repeatable vision checks
3. Thin local web UI built on canonical backend logic
4. Export and review workflow for sellers
5. Documentation and operational handoff

---

## Phase 1: Environment + repo hygiene

### Task 1: Standardize local Python workflow

**Objective:** Remove ambiguity around Python version and installation so every later task runs on a known-good environment.

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Create: `.python-version` or `runtime.txt` only if justified by chosen workflow
- Modify: `.gitignore`

**Steps:**
1. Document Python 3.12 as the preferred development interpreter.
2. Replace ambiguous install instructions with explicit venv creation using `python3.12 -m venv .venv312`.
3. Document exact bootstrap commands and verification commands.
4. Decide whether to keep `.venv312` naming or standardize back to `.venv` once local confusion is addressed.

**Verification:**
- Fresh clone bootstrap instructions work exactly as written.
- `python -m pip install -e '.[dev]'` succeeds in the documented environment.

### Task 2: Make lint green

**Objective:** Clear the 32 Ruff issues so CI can become meaningful.

**Files:**
- Modify: `src/whgot/__init__.py`
- Modify: `src/whgot/cli.py`
- Modify: `src/whgot/condition.py`
- Modify: `src/whgot/listing.py`
- Modify: `src/whgot/pricing.py`
- Modify: `src/whgot/vision.py`
- Modify: `tests/test_pricing.py`

**Steps:**
1. Remove unused imports/variables.
2. Reformat long lines.
3. Fix import ordering.
4. Re-run Ruff until clean.

**Verification:**
- `ruff check src tests`
- expected: all checks pass

### Task 3: Add CI

**Objective:** Make repo health automatically checkable.

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

**Steps:**
1. Add a GitHub Actions workflow for Python 3.12.
2. Install package with dev extras.
3. Run pytest and Ruff.
4. Add badge/instructions only if useful.

**Verification:**
- Workflow YAML is valid.
- Local command set in README matches CI commands.

---

## Phase 2: Testing the product surface, not just internals

### Task 4: Add CLI smoke tests

**Objective:** Validate actual command entrypoints rather than only direct function tests.

**Files:**
- Create: `tests/test_cli.py`
- Modify: `src/whgot/cli.py` only if needed for testability

**Steps:**
1. Add tests for `version`.
2. Add tests for help output.
3. Add tests for invalid file/directory handling.
4. Add tests for JSON input/output flows that do not require live Ollama.

**Verification:**
- `python -m pytest -q tests/test_cli.py`

### Task 5: Add fixture corpus for parser and downstream pipeline tests

**Objective:** Capture realistic model-response shapes and sample items so regressions become visible.

**Files:**
- Create: `tests/fixtures/vision/single-book-response.json.txt`
- Create: `tests/fixtures/vision/batch-shelf-response.json.txt`
- Create: `tests/fixtures/vision/malformed-response-markdown-fence.txt`
- Create: `tests/fixtures/items/books_media_sample.json`
- Create: `tests/fixtures/items/toys_collectibles_sample.json`
- Create: `tests/fixtures/items/electronics_sample.json`
- Create: `tests/test_parsing.py`

**Steps:**
1. Add fenced JSON fixture.
2. Add malformed-but-recoverable fixture.
3. Add representative sample item records by priority vertical.
4. Add parser tests against those fixtures.

**Verification:**
- `python -m pytest -q tests/test_parsing.py`

### Task 6: Add end-to-end offline pipeline tests for listing/export logic

**Objective:** Test realistic Item payloads through price/listing/export surfaces without requiring Ollama.

**Files:**
- Create: `tests/test_pipeline_offline.py`
- Modify: `src/whgot/cli.py` if test seams are needed

**Steps:**
1. Load representative item JSON fixtures.
2. Validate listing generation and CSV/JSON output.
3. Verify category-specific fields for books/media, toys/collectibles, electronics.
4. Assert no crashes on sparse metadata.

**Verification:**
- `python -m pytest -q tests/test_pipeline_offline.py`

---

## Phase 3: Evaluation corpus and repeatable quality measurement

### Task 7: Create a benchmark data contract

**Objective:** Define the shape of evaluation fixtures so real-photo and synthetic examples can coexist.

**Files:**
- Create: `eval/README.md`
- Create: `eval/benchmark_schema.md`
- Create: `eval/benchmarks/starter_manifest.json`

**Benchmark record should include:**
- id
- category
- image_path or text_input
- mode (`single_image`, `multi_image`, `text_only`)
- expected_name
- expected_category
- expected_key_metadata
- acceptable_aliases
- notes
- source_type (`local_real`, `synthetic_public`)

**Verification:**
- Benchmarks are readable and documented.

### Task 8: Add an evaluation runner

**Objective:** Make model/prompt comparisons repeatable.

**Files:**
- Create: `src/whgot/eval.py`
- Create: `tests/test_eval.py`
- Modify: `pyproject.toml` if adding console entrypoint

**Steps:**
1. Add a small evaluation module that runs identification against a manifest.
2. Score category accuracy, exact/alias name hit, and metadata hit rate.
3. Write JSON/CSV summary output.
4. Keep it local-first and tolerant of partial results.

**Verification:**
- Offline unit tests for scoring logic pass.
- Live eval command can be run when Ollama corpus is present.

### Task 9: Add seed benchmark data for priority categories

**Objective:** Give the evaluation runner enough material to expose tradeoffs.

**Files:**
- Create: `eval/benchmarks/books-media/`
- Create: `eval/benchmarks/toys-collectibles/`
- Create: `eval/benchmarks/electronics/`
- Modify: `eval/README.md`

**Steps:**
1. Add a small starter set for each priority category.
2. Include both easy and ambiguous samples.
3. Include at least a few multi-item images.
4. Record known failure modes.

**Verification:**
- Eval runner produces a summary table across the seed corpus.

---

## Phase 4: Pricing hardening for seller triage

### Task 10: Refactor pricing into explicit source adapters

**Objective:** Make the current free/public pricing strategy easier to reason about and extend.

**Files:**
- Modify: `src/whgot/pricing.py`
- Create: `src/whgot/pricing_sources.py` or `src/whgot/pricing/` package if justified
- Modify: `tests/test_pricing.py`

**Steps:**
1. Separate cache, OpenLibrary enrichment, and eBay scraping into explicit units.
2. Preserve current behavior first.
3. Add source-level provenance fields where possible.
4. Prepare for future optional public-source additions without a rewrite.

**Verification:**
- Existing pricing tests still pass.
- New tests cover source ordering and fallback behavior.

### Task 11: Expose pricing provenance in output

**Objective:** Help users understand why a price band exists instead of treating it as magic.

**Files:**
- Modify: `src/whgot/schema.py`
- Modify: `src/whgot/pricing.py`
- Modify: `src/whgot/cli.py`
- Modify: `src/whgot/listing.py`
- Create: `tests/test_pricing_provenance.py`

**Candidate additions:**
- lookup_source_details
- comp_count
- query_used
- price_confidence or coverage note
- warnings for heuristic-only results

**Verification:**
- Table/JSON output shows provenance fields cleanly.
- Sparse results do not break formatting.

### Task 12: Add a seller triage score

**Objective:** Support the core user need: focus on likely high-potential items among a large collection.

**Files:**
- Create: `src/whgot/triage.py`
- Modify: `src/whgot/schema.py`
- Modify: `src/whgot/cli.py`
- Create: `tests/test_triage.py`

**First-pass heuristics could combine:**
- price median / high band
- category signal
- identifier quality (ISBN/UPC exactness)
- confidence score
- packaging or condition signal
- rarity/commonness hints

**Verification:**
- Priority categories produce understandable sort order.
- Output makes it clear score is heuristic, not guaranteed profit.

---

## Phase 5: Local web UI

### Task 13: Decide the thinnest web architecture that reuses backend logic

**Objective:** Avoid building a disconnected frontend prototype.

**Preferred direction:**
- local FastAPI app with server-rendered pages and minimal JS
- optional htmx for small interactions
- direct reuse of `src/whgot/*` logic

**Files:**
- Create: `src/whgot/web_app.py`
- Create: `src/whgot/web_templates/`
- Create: `src/whgot/web_static/`
- Modify: `pyproject.toml`
- Modify: `README.md`

**Why this direction:**
- true local web app, not fake static prototype
- easy file upload support
- easy spreadsheet export
- easiest path to preserving one source of truth for logic

### Task 14: Build MVP web flow: upload -> identify -> price -> listing draft

**Objective:** Expose the core v1 product journey in-browser.

**Files:**
- Create: `src/whgot/web_app.py`
- Create: `src/whgot/web_templates/base.html`
- Create: `src/whgot/web_templates/index.html`
- Create: `src/whgot/web_templates/results.html`
- Create: `src/whgot/web_static/styles.css`
- Create: `src/whgot/web_static/app.js` only if needed
- Create: `tests/test_web_app.py`

**MVP UI sections:**
- upload single image
- upload multiple images / directory substitute if practical
- paste text descriptions
- choose mode: single item / multi-item image / text list
- choose model
- run identify
- optionally run price enrichment
- inspect listing draft
- export JSON / CSV

**Verification:**
- Start app locally and submit sample inputs.
- Browser can complete the full v1 path.

### Task 15: Add browser review workflow for large collections

**Objective:** Make the tool useful for triaging many items, not just one.

**Files:**
- Modify: `src/whgot/web_templates/results.html`
- Modify: `src/whgot/web_static/styles.css`
- Modify: `src/whgot/web_app.py`
- Create: `tests/test_web_review.py`

**Review UX should include:**
- sortable result list
- filter by category
- filter by confidence / priced vs unpriced
- sort by triage score / price median / confidence
- quick view of listing-ready draft text
- warnings when output is heuristic-only

**Verification:**
- Sample batch results are explorable without dropping to CLI.

### Task 16: Add spreadsheet export and saved session artifacts

**Objective:** Support the real use case of moving findings into seller workflows.

**Files:**
- Modify: `src/whgot/cli.py`
- Modify: `src/whgot/web_app.py`
- Modify: `src/whgot/schema.py` if needed
- Create: `src/whgot/session_store.py`
- Create: `tests/test_exports.py`

**Features:**
- CSV export from web results
- JSON export from web results
- local saved-session bundle under a documented app data directory
- ability to reopen a prior session later

**Verification:**
- Exported files open cleanly in spreadsheet software.
- Session reload restores results view.

---

## Phase 6: Documentation and polish

### Task 17: Rewrite README around the actual product

**Objective:** Make the repo understandable as a local seller research tool with both CLI and web UI.

**Files:**
- Modify: `README.md`
- Create: `docs/roadmap.md`
- Create: `docs/web-ui-flow.md`
- Create: `docs/eval-workflow.md`

**README should cover:**
- product purpose
- supported workflows
- Python setup
- CLI quick start
- web UI quick start
- limitations and provenance caveats
- where benchmark/eval data lives

### Task 18: Add a bounded overnight execution log plan

**Objective:** Give overnight work a crisp stop condition.

**Files:**
- Create: `docs/overnight-milestones.md`

**Milestone ladder:**
1. lint green
2. CI added
3. CLI smoke tests added
4. parser fixtures added
5. eval scaffold added
6. web app skeleton runs
7. upload -> identify -> price -> listing draft works in browser
8. CSV/JSON export works in browser

---

## Likely files to change overall

Existing files likely to be modified:
- `README.md`
- `pyproject.toml`
- `src/whgot/__init__.py`
- `src/whgot/cli.py`
- `src/whgot/schema.py`
- `src/whgot/pricing.py`
- `src/whgot/listing.py`
- `src/whgot/condition.py`
- `src/whgot/vision.py`
- `tests/test_pricing.py`

Likely new files/directories:
- `.github/workflows/ci.yml`
- `tests/test_cli.py`
- `tests/test_parsing.py`
- `tests/test_pipeline_offline.py`
- `tests/test_eval.py`
- `tests/test_triage.py`
- `tests/test_web_app.py`
- `tests/test_web_review.py`
- `tests/test_exports.py`
- `tests/fixtures/vision/`
- `tests/fixtures/items/`
- `eval/`
- `src/whgot/eval.py`
- `src/whgot/triage.py`
- `src/whgot/web_app.py`
- `src/whgot/session_store.py`
- `src/whgot/web_templates/`
- `src/whgot/web_static/`
- `docs/roadmap.md`
- `docs/web-ui-flow.md`
- `docs/eval-workflow.md`
- `docs/overnight-milestones.md`

---

## Testing / validation matrix

Core repo health:
- `python -m pytest -q`
- `ruff check src tests`

Targeted tests:
- `python -m pytest -q tests/test_cli.py`
- `python -m pytest -q tests/test_parsing.py`
- `python -m pytest -q tests/test_pipeline_offline.py`
- `python -m pytest -q tests/test_pricing.py`
- `python -m pytest -q tests/test_eval.py`
- `python -m pytest -q tests/test_triage.py`
- `python -m pytest -q tests/test_web_app.py`
- `python -m pytest -q tests/test_web_review.py`
- `python -m pytest -q tests/test_exports.py`

Manual verification:
- run web app locally
- upload a single-item image
- submit a multi-item image
- paste a text list
- verify priced results render
- verify listing drafts render
- verify CSV export opens correctly
- verify saved-session reload works

---

## Risks and tradeoffs

1. eBay HTML scraping is fragile.
   - For this phase, keep it but visibly mark heuristic provenance.
   - Do not build too much UX assuming scrape stability.

2. Web UI can sprawl fast.
   - Keep it thin and local-first.
   - Reuse backend logic instead of duplicating JS business logic.

3. Evaluation work can become a research rabbit hole.
   - Start with a small benchmark corpus and simple scoring.
   - Do not wait for a perfect corpus before shipping the MVP web review flow.

4. Single-image and multi-image support may require different UX and eventually different backend logic.
   - Surface them as explicit modes early.

5. Broad pricing coverage may reduce trust.
   - Counter with provenance, warnings, and clear heuristic labels.

---

## Recommended overnight execution order

If Hermes works overnight, the highest-yield order is:
1. Task 2: make lint green
2. Task 3: add CI
3. Task 4: add CLI smoke tests
4. Task 5: add parsing fixtures/tests
5. Task 7: benchmark data contract
6. Task 8: eval runner scaffold
7. Task 13: choose and scaffold web architecture
8. Task 14: MVP web flow
9. Task 11: pricing provenance in output
10. Task 15: review workflow
11. Task 16: exports + saved sessions
12. Task 17: README/docs rewrite

This order matches the user’s stated priority mix: reliability first, then evaluation, then web UI.

---

## Remaining questions before execution

Resolved:
1. First web UI cut should be desktop-first.
2. Add a fast heuristic triage badge early in the UI.
3. Spreadsheet export should be simple first: one row per identified item.
4. Real benchmark photos can live in a gitignored local directory inside the repo tree.

Resolved:
1. Saved sessions should live under `~/.whgot/` from the start.

Implementation default:
- session storage root: `~/.whgot/sessions/`
- benchmark local-real-images root: repo-local gitignored directory
