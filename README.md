# AI Web Research Agent

A Streamlit application that accepts natural-language research instructions, searches the web via TinyFish, extracts structured data, and exports to Excel, CSV, Word, PDF, and Google Sheets. All data persists in PostgreSQL (Supabase).

## How It Works

1. **Describe your task** in plain English (e.g., "Find 50 AI companies in Pakistan. Collect name, website, email...").
2. The **planner** converts your request into a structured plan: search queries, extraction fields, target count, dedup keys, and batch settings. You can edit everything before starting.
3. The **pipeline** executes TinyFish web searches, fetches relevant pages, extracts fields from real page content, deduplicates records, and saves results incrementally to PostgreSQL.
4. **Review and export** results — edit cells, delete rows, filter, then export to XLSX, CSV, DOCX, PDF, or Google Sheets.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure TinyFish (required)

Get an API key from [TinyFish](https://docs.tinyfish.ai/) and set it in your `.env` file:

```
TINYFISH_API_KEY=your-key-here
```

The app will not fabricate results — without a valid key, jobs fail with a clear error message.

### 3. Configure the database

Supabase credentials are pre-configured in `.env`. The schema is applied via the Supabase migration tool (see `supabase/migrations/`). No manual database setup is needed in this environment.

### 4. Configure Google Sheets (optional)

To enable Google Sheets export:

1. Create a Google Cloud project and enable the Sheets API.
2. Create a **service account** and download the JSON key file.
3. Set the path in `.env`:

```
GOOGLE_CLIENT_SECRETS_PATH=/path/to/service-account.json
```

Without this, the other four export formats work normally and the app displays a setup message instead of pretending to export.

## Running the App

```bash
streamlit run app.py
```

## Running Tests

```bash
# Unit tests (mocked, no network required)
python -m pytest tests/ -v

# Live TinyFish smoke test (requires TINYFISH_API_KEY)
python -m pytest tests/test_smoke_live.py -v
```

Unit tests use deterministic mocks. The live smoke test is skipped automatically when no API key is configured — it performs a real search and fetch.

## Project Structure

```
app.py                          # Streamlit application (main entry)
config.py                       # Settings from env/Streamlit secrets
database/connection.py          # Supabase client + repository helpers
services/
    tinyfish_client.py          # TinyFish search/fetch (only provider)
    research_planner.py         # NL prompt → structured plan
    research_pipeline.py        # Search → fetch → extract → dedup → persist
    extraction_service.py       # Field extraction from page content
    deduplication.py            # Cross-batch dedup
    export_service.py           # Export dispatcher
    repositories.py             # DB CRUD operations
exports/
    excel_exporter.py           # XLSX (openpyxl)
    csv_exporter.py             # CSV (UTF-8, formula-safe)
    word_exporter.py            # DOCX report (python-docx)
    pdf_exporter.py             # PDF report (ReportLab)
    google_sheets_exporter.py   # Google Sheets (optional)
workers/research_worker.py      # Background job threads
utils/security.py               # URL validation, SSRF guards, injection filters
tests/                          # Unit + live smoke tests
```

## Key Design Decisions

- **TinyFish only** — no alternative search providers or fallback scraping. If TinyFish fails, the error is surfaced; results are never substituted.
- **Grounded extraction** — every field comes from fetched page content. Missing data is marked as unavailable, never fabricated.
- **Real progress** — job counters (queries, URLs, pages, records, duplicates, failures) are persisted to PostgreSQL and reflect actual execution, not animations.
- **Partial results preserved** — if fewer records exist than requested, you get what was found plus an explanation.
- **Security** — SSRF-protected URL validation, formula-injection-safe exports, prompt-injection filtering on fetched content, and secrets only in environment variables.

## Limitations

- TinyFish live search/fetch requires a valid `TINYFISH_API_KEY`; without one the app blocks job execution (by design, no mock data).
- Google Sheets export requires service-account credentials; the app shows setup instructions when missing.
- Extraction is heuristic (regex/HTML-based) — complex pages may yield missing fields. Use the results editor to fix values manually before export.
- Background jobs run as threads in the Streamlit process; for very large jobs (10k+ records), a separate task-queue worker would be recommended.
