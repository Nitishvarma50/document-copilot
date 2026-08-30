from __future__ import annotations

import json
import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib import error, request

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(__file__).resolve().parent / "downloads"
CLEAR_OUTPUT_DIR = False
FILINGS_PER_COMPANY = 5
TARGET_YEARS = {"2021", "2022", "2023", "2024", "2025"}
REQUEST_DELAY_SECONDS = 0.5
MAX_RETRIES = 3

USER_AGENT = os.getenv("SEC_USER_AGENT")
if not USER_AGENT:
    raise RuntimeError(
        "SEC_USER_AGENT is not configured. Add it to .env, for example: "
        "SEC_USER_AGENT=document-copilot your-email@example.com"
    )

TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "JPM", "V", "JNJ"]

COMPANY_CIKS = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "TSLA": "0001318605",
    "META": "0001326801",
    "NVDA": "0001045810",
    "JPM": "0000019617",
    "V": "0001403161",
    "JNJ": "0000200406",
}


def get_bytes(url: str, accept: str = "application/json") -> bytes:
    for attempt in range(1, MAX_RETRIES + 1):
        req = request.Request(
            url,
            headers={
                "Accept": accept,
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                return response.read()
        except error.HTTPError as exc:
            # Retry rate limits and temporary server failures, but fail clearly
            # for authentication or request errors such as an invalid User-Agent.
            if exc.code not in {429, 500, 502, 503, 504} or attempt == MAX_RETRIES:
                raise
            time.sleep(attempt * 2)
        except (TimeoutError, error.URLError):
            if attempt == MAX_RETRIES:
                raise
            time.sleep(attempt * 2)

    raise RuntimeError(f"Unable to download {url}")


def get_json(url: str) -> dict:
    return json.loads(get_bytes(url).decode("utf-8"))


def extract_10k_filings(
    submission: dict, target_years: set[str]
) -> list[dict[str, str]]:
    recent = submission.get("filings", {}).get("recent", submission)
    filings = []

    for form, accession, document, filing_date, report_date in zip(
        recent.get("form", []),
        recent.get("accessionNumber", []),
        recent.get("primaryDocument", []),
        recent.get("filingDate", []),
        recent.get("reportDate", []),
    ):
        year = (report_date or filing_date)[:4]
        if form == "10-K" and year in target_years:
            filings.append(
                {
                    "form": form,
                    "accession_number": accession,
                    "primary_document": document,
                    "filing_date": filing_date,
                    "report_date": report_date,
                    "year": year,
                }
            )

    return filings


def write_manifest(manifest: dict) -> None:
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=4),
        encoding="utf-8",
    )


def download_filings() -> dict:
    if CLEAR_OUTPUT_DIR and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {
        "source": "SEC EDGAR",
        "generated_at": datetime.now(UTC).isoformat(),
        "form": "10-K",
        "target_years": sorted(TARGET_YEARS),
        "download_count": 0,
        "filings": [],
    }

    for ticker in TICKERS:
        print(f"Downloading filings for {ticker}...")
        cik = COMPANY_CIKS[ticker]
        submission = get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
        submissions = [submission]
        submissions.extend(
            get_json(f"https://data.sec.gov/submissions/{item['name']}")
            for item in submission.get("filings", {}).get("files", [])
        )

        filings = []
        for sec_submission in submissions:
            filings.extend(extract_10k_filings(sec_submission, TARGET_YEARS))
            if len(filings) >= FILINGS_PER_COMPANY:
                break

        # Keep one filing per fiscal year and prefer the first SEC result.
        filings = list({filing["year"]: filing for filing in filings}.values())
        filings.sort(key=lambda filing: filing["year"], reverse=True)

        if len(filings) < FILINGS_PER_COMPANY:
            raise RuntimeError(
                f"{ticker}: expected {FILINGS_PER_COMPANY} filings for "
                f"{sorted(TARGET_YEARS)}, found {len(filings)}"
            )

        for filing in filings[:FILINGS_PER_COMPANY]:
            accession_path = filing["accession_number"].replace("-", "")
            source_url = (
                "https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{accession_path}/{filing['primary_document']}"
            )
            year_dir = OUTPUT_DIR / filing["year"]
            year_dir.mkdir(parents=True, exist_ok=True)
            existing_files = sorted(year_dir.glob(f"{ticker.lower()}_10-k_*"))
            if existing_files:
                local_path = existing_files[0]
                print(f"Skipping {ticker} {filing['year']}: filing already exists")
            else:
                local_path = year_dir / (
                    f"{ticker.lower()}_{filing['form'].lower()}_"
                    f"{filing['filing_date']}_{filing['accession_number']}"
                    f"{Path(filing['primary_document']).suffix or '.html'}"
                )
                local_path.write_bytes(
                    get_bytes(source_url, accept="text/html,application/xhtml+xml")
                )

            manifest["filings"].append(
                {
                    "ticker": ticker,
                    "cik": cik,
                    "year": filing["year"],
                    "form": filing["form"],
                    "filing_date": filing["filing_date"],
                    "accession_number": filing["accession_number"],
                    "primary_document": filing["primary_document"],
                    "source_url": source_url,
                    "local_path": str(local_path.relative_to(PROJECT_ROOT)),
                }
            )
            manifest["download_count"] += 1
            write_manifest(manifest)
            time.sleep(REQUEST_DELAY_SECONDS)

    return manifest


if __name__ == "__main__":
    manifest = download_filings()
    print(f"Downloaded {manifest['download_count']} filings.")
    print(f"Manifest saved to {OUTPUT_DIR / 'manifest.json'}")
