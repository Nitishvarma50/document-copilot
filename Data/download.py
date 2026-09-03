from __future__ import annotations

import json
import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, request

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(__file__).resolve().parent / "downloads"
CORPUS_CONFIG_PATH = PROJECT_ROOT / "Data" / "config" / "corpus.json"
CLEAR_OUTPUT_DIR = False
REQUEST_DELAY_SECONDS = 0.5
MAX_RETRIES = 3


def validate_corpus_config(config: dict) -> None:
    """Validate the scalable corpus configuration."""
    companies = config.get("companies")
    forms = config.get("forms")
    lookback_years = config.get("lookback_years")

    if not isinstance(companies, dict) or not companies:
        raise ValueError("companies must contain at least one company")
    if not isinstance(lookback_years, int) or isinstance(lookback_years, bool):
        raise ValueError("lookback_years must be a positive integer")
    if lookback_years <= 0:
        raise ValueError("lookback_years must be a positive integer")
    if (
        not isinstance(forms, list)
        or not forms
        or not all(isinstance(form, str) and form.strip() for form in forms)
    ):
        raise ValueError("forms must contain at least one non-empty string")

    ciks = []
    for ticker, company in companies.items():
        if not isinstance(ticker, str) or not ticker or ticker != ticker.upper():
            raise ValueError("company tickers must be non-empty uppercase strings")
        if not isinstance(company, dict) or not str(company.get("name", "")).strip():
            raise ValueError(f"{ticker}: company name must be non-empty")
        cik = company.get("cik")
        if not isinstance(cik, str) or len(cik) != 10 or not cik.isdigit():
            raise ValueError(f"{ticker}: CIK must contain exactly ten digits")
        ciks.append(cik)

    if len(ciks) != len(set(ciks)):
        raise ValueError("CIKs must be unique")


def load_corpus_config(path: Path = CORPUS_CONFIG_PATH) -> dict:
    """Load and validate the corpus configuration from disk."""
    config = json.loads(path.read_text(encoding="utf-8"))
    validate_corpus_config(config)
    return config


def calculate_target_filing_years(
    lookback_years: int, current_year: int | None = None
) -> set[str]:
    """Return the previous complete filing years, excluding the current year."""
    if not isinstance(lookback_years, int) or isinstance(lookback_years, bool):
        raise ValueError("lookback_years must be positive")
    if lookback_years <= 0:
        raise ValueError("lookback_years must be positive")
    year = current_year if current_year is not None else datetime.now(UTC).year
    return {str(target_year) for target_year in range(year - lookback_years, year)}


CORPUS_CONFIG = load_corpus_config()
COMPANIES = CORPUS_CONFIG["companies"]
TARGET_FILING_YEARS = calculate_target_filing_years(CORPUS_CONFIG["lookback_years"])
FORMS = set(CORPUS_CONFIG["forms"])
FILINGS_PER_COMPANY = len(TARGET_FILING_YEARS)


def get_user_agent() -> str:
    """Return the SEC User-Agent, validating it only before network access."""
    user_agent = os.getenv("SEC_USER_AGENT")
    if not user_agent:
        raise RuntimeError(
            "SEC_USER_AGENT is not configured. Add it to .env, for example: "
            "SEC_USER_AGENT=document-copilot your-email@example.com"
        )
    return user_agent


def get_bytes(url: str, accept: str = "application/json") -> bytes:
    user_agent = get_user_agent()
    for attempt in range(1, MAX_RETRIES + 1):
        req = request.Request(
            url,
            headers={
                "Accept": accept,
                "User-Agent": user_agent,
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


def extract_filings(
    submission: dict, target_filing_years: set[str], forms: set[str]
) -> list[dict[str, str]]:
    recent = submission.get("filings", {}).get("recent", submission)
    filings = []

    for form, accession, document, filing_date, report_date in zip(
        recent.get("form", []),
        recent.get("accessionNumber", []),
        recent.get("primaryDocument", []),
        recent.get("filingDate", []),
        recent.get("reportDate", []),
        strict=True,
    ):
        filing_year = filing_date[:4]
        report_year = report_date[:4] if report_date else None
        if form in forms and filing_year in target_filing_years:
            filings.append(
                {
                    "form": form,
                    "accession_number": accession,
                    "primary_document": document,
                    "filing_date": filing_date,
                    "report_date": report_date,
                    "filing_year": filing_year,
                    "report_year": report_year,
                }
            )

    return filings


def find_existing_filing(
    output_dir: Path, ticker: str, form: str, filing_year: str
) -> Path | None:
    """Find an existing local filing for a company, form, and filing year."""
    year_dir = output_dir / filing_year
    matches = sorted(year_dir.glob(f"{ticker.lower()}_{form.lower()}_*"))
    return matches[0] if matches else None


def manifest_relative_path(path: Path) -> str:
    """Return a repository-relative, POSIX-style manifest path."""
    return path.relative_to(PROJECT_ROOT).as_posix()


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

    manifest: dict[str, Any] = {
        "source": "SEC EDGAR",
        "generated_at": datetime.now(UTC).isoformat(),
        "forms": sorted(FORMS),
        "target_filing_years": sorted(TARGET_FILING_YEARS),
        "company_count": len(COMPANIES),
        "download_count": 0,
        "filings": [],
    }

    for ticker, company in COMPANIES.items():
        print(f"Downloading filings for {ticker}...")
        cik = company["cik"]
        submission = get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
        submissions = [submission]
        submissions.extend(
            get_json(f"https://data.sec.gov/submissions/{item['name']}")
            for item in submission.get("filings", {}).get("files", [])
        )

        filings = []
        for sec_submission in submissions:
            filings.extend(extract_filings(sec_submission, TARGET_FILING_YEARS, FORMS))
            if len(filings) >= FILINGS_PER_COMPANY:
                break

        # Keep one filing per filing year and prefer the first SEC result.
        filings = list({filing["filing_year"]: filing for filing in filings}.values())
        filings.sort(key=lambda filing: filing["filing_year"], reverse=True)

        found_years = {filing["filing_year"] for filing in filings}
        missing_years = TARGET_FILING_YEARS - found_years
        if missing_years:
            raise RuntimeError(
                f"{ticker}: missing {sorted(missing_years)} filings; "
                f"found {sorted(found_years)}"
            )

        for filing in filings[:FILINGS_PER_COMPANY]:
            accession_path = filing["accession_number"].replace("-", "")
            source_url = (
                "https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{accession_path}/{filing['primary_document']}"
            )
            year_dir = OUTPUT_DIR / filing["filing_year"]
            year_dir.mkdir(parents=True, exist_ok=True)
            existing_files = sorted(
                year_dir.glob(f"{ticker.lower()}_{filing['form'].lower()}_*")
            )
            if existing_files:
                local_path = existing_files[0]
                print(
                    f"Skipping {ticker} {filing['filing_year']}: filing already exists"
                )
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
                    "company_name": company["name"],
                    "cik": cik,
                    "filing_year": filing["filing_year"],
                    "report_year": filing["report_year"],
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
