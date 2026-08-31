# Document Copilot

Document Copilot is a research assistant for answering questions from SEC filings.

## Usage and ownership

This project is proprietary and intended for internal use by Driftwood Capital and authorized collaborators only. Do not redistribute its source code, credentials, client data, chat transcripts, or generated research outputs.

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

The pilot corpus is configured in `config/corpus.json`, which is the single source of truth for companies, filing forms, and the filing-year lookback period. The initial pilot contains Apple, Amazon, Alphabet, Microsoft, and NVIDIA. Edit the configuration file rather than hardcoding corpus settings in the downloader.

The downloader selects the previous five complete filing years relative to the current UTC year and excludes the current partial year. The manifest distinguishes `filing_year` from `report_year` because a 10-K may be filed in the calendar year after the fiscal period it covers.

## Project layout

```text
config/     Pilot corpus configuration
Data/       SEC downloader and local filing corpus
Docs/       Product brief, architecture, and implementation checklist
main.py     Application entry point (currently a placeholder)
```

Do not commit `.env` or downloaded filings.
