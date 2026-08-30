# Document Copilot

Document Copilot is a research assistant for answering questions from SEC filings.

## Setup

This project uses `uv` and Python 3.12+.

```bat
uv sync
copy .env.example .env
```

Edit `.env` and replace `your-email@example.com` with a real contact email:

```env
SEC_USER_AGENT=document-copilot your-email@example.com
```

The SEC does not require an account or API key, but it does require an identifying User-Agent.

## Download SEC filings

```bat
uv run Data\download.py
```

Filings are saved under `Data/downloads/`. The generated manifest is at:

```text
Data/downloads/manifest.json
```

The downloader currently retrieves five 10-K filings for each configured company for fiscal years 2021–2025.

## Project layout

```text
Data/       SEC downloader and local filing corpus
Docs/       Product brief and architecture notes
main.py     Application entry point (currently a placeholder)
```

Do not commit `.env` or downloaded filings.
