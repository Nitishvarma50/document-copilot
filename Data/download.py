from __future__ import annotations

import json
import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib import error, request

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(__file__).resolve().parent / "downloads"
CORPUS_CONFIG_PATH = PROJECT_ROOT / "config" / "corpus.json"
CLEAR_OUTPUT_DIR = False
REQUEST_DELAY_SECONDS = 0.5
MAX_RETRIES = 3


def validate_corpus_config(config: dict[str, Any]) -> None:
    """Validate corpus configuration without imposing a company-count limit."""
    companies = config.get("companies")
    if not isinstance(companies, dict) or not companies:
        raise ValueError("Corpus configuration must contain at least one company")

    ciks: list[str] = []
    for ticker, company in companies.items():
        if not isinstance(ticker, str) or not ticker or ticker != ticker.upper():
            raise ValueError(f"Invalid ticker: {ticker!r}")
        if not isinstance(company, dict):
            raise ValueError(f"Configuration for {ticker} must be an object")

        name = company.get("name")
        cik = company.get("cik")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{ticker} must have a non-empty company name")
        if not isinstance(cik, str) or len(cik) != 10 or not cik.isdigit():
            raise ValueError(f"{ticker} must have a 10-digit CIK")
        ciks.append(cik)

    if len(ciks) != len(set(ciks)):
        raise ValueError("Company CIKs must be unique")

    forms = config.get("forms")
    if (
        not isinstance(forms, list)
        or not forms
        or not all(isinstance(form, str) and form.strip() for form in forms)
    ):
        raise ValueError("Corpus configuration must contain filing forms")
    if "10-K" not in forms:
        raise ValueError("The current corpus must include form 10-K")

    lookback_years = config.get("lookback_years")
    if (
        not isinstance(lookback_years, int)
        or isinstance(lookback_years, bool)
        or lookback_years <= 0
    ):
        raise ValueError("lookback_years must be a positive integer")


def load_corpus_config(path: Path = CORPUS_CONFIG_PATH) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Corpus configuration must be a JSON object")
    validate_corpus_config(config)
    return config


def calculate_target_filing_years(
    lookback_years: int, current_year: int | None = None
) -> set[str]:
    """Return previous complete filing years, excluding the current year."""
    if lookback_years <= 0:
        raise ValueError("lookback_years must be positive")
    reference_year = current_year or datetime.now(UTC).year
    return {
        str(year) for year in range(reference_year - lookback_years, reference_year)
    }


def get_user_agent() -> str:
    """Read and validate SEC identification only when a request is made."""
    user_agent = os.getenv("SEC_USER_AGENT")
    if not user_agent:
        raise RuntimeError(
            "SEC_USER_AGENT is not configured. Add it to .env, for example: "
            "SEC_USER_AGENT=document-copilot your-email@example.com"
        )
    return user_agent


CORPUS_CONFIG = load_corpus_config()
COMPANIES = cast(dict[str, dict[str, str]], CORPUS_CONFIG["companies"])
FORMS = set(cast(list[str], CORPUS_CONFIG["forms"]))
LOOKBACK_YEARS = cast(int, CORPUS_CONFIG["lookback_years"])
TARGET_FILING_YEARS = calculate_target_filing_years(LOOKBACK_YEARS)
FILINGS_PER_COMPANY = len(TARGET_FILING_YEARS)


def get_bytes(url: str, accept: str = "application/json") -> bytes:
    for attempt in range(1, MAX_RETRIES + 1):
        req = request.Request(
            url,
            headers={"Accept": accept, "User-Agent": get_user_agent()},
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                return response.read()
        except error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == MAX_RETRIES:
                raise
            time.sleep(attempt * 2)
        except (TimeoutError, error.URLError):
            if attempt == MAX_RETRIES:
                raise
            time.sleep(attempt * 2)

    raise RuntimeError(f"Unable to download {url}")


def get_json(url: str) -> dict[str, Any]:
    result = json.loads(get_bytes(url).decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"Expected a JSON object from {url}")
    return result


def extract_filings(
    submission: dict[str, Any],
    target_filing_years: set[str],
    forms: set[str],
) -> list[dict[str, str | None]]:
    recent = submission.get("filings", {}).get("recent", submission)
    filings: list[dict[str, str | None]] = []

    for form, accession, document, filing_date, report_date in zip(
        recent.get("form", []),
        recent.get("accessionNumber", []),
        recent.get("primaryDocument", []),
        recent.get("filingDate", []),
        recent.get("reportDate", []),
        strict=False,
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
    year_dir = output_dir / filing_year
    matches = sorted(year_dir.glob(f"{ticker.lower()}_{form.lower()}_*"))
    return matches[0] if matches else None


def manifest_relative_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def write_manifest(manifest: dict[str, Any]) -> None:
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=4), encoding="utf-8")


def download_filings() -> dict[str, Any]:
    if CLEAR_OUTPUT_DIR and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "source": "SEC EDGAR",
        "generated_at": datetime.now(UTC).isoformat(),
        "forms": sorted(FORMS),
        "lookback_years": LOOKBACK_YEARS,
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

        filings: list[dict[str, str | None]] = []
        for sec_submission in submissions:
            filings.extend(extract_filings(sec_submission, TARGET_FILING_YEARS, FORMS))
            if len(filings) >= FILINGS_PER_COMPANY:
                break

        by_year = {filing["filing_year"]: filing for filing in filings}
        filings = sorted(
            by_year.values(),
            key=lambda filing: filing["filing_year"] or "",
            reverse=True,
        )

        found_years = {
            year for filing in filings if (year := filing["filing_year"]) is not None
        }
        missing_years = TARGET_FILING_YEARS - found_years
        if missing_years:
            raise RuntimeError(
                f"{ticker}: missing {sorted(missing_years)} filings; "
                f"found {sorted(found_years)}"
            )

        for filing in filings[:FILINGS_PER_COMPANY]:
            form = filing["form"]
            filing_year = filing["filing_year"]
            accession_number = filing["accession_number"]
            primary_document = filing["primary_document"]
            filing_date = filing["filing_date"]
            if (
                form is None
                or filing_year is None
                or accession_number is None
                or primary_document is None
                or filing_date is None
            ):
                raise ValueError(f"Incomplete SEC filing metadata for {ticker}")

            accession_path = accession_number.replace("-", "")
            source_url = (
                "https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{accession_path}/{primary_document}"
            )
            year_dir = OUTPUT_DIR / filing_year
            year_dir.mkdir(parents=True, exist_ok=True)
            local_path = find_existing_filing(OUTPUT_DIR, ticker, form, filing_year)
            if local_path:
                print(f"Skipping {ticker} {filing_year}: filing already exists")
            else:
                local_path = year_dir / (
                    f"{ticker.lower()}_{form.lower()}_"
                    f"{filing_date}_{accession_number}"
                    f"{Path(primary_document).suffix or '.html'}"
                )
                local_path.write_bytes(
                    get_bytes(source_url, accept="text/html,application/xhtml+xml")
                )

            manifest["filings"].append(
                {
                    "ticker": ticker,
                    "company_name": company["name"],
                    "cik": cik,
                    "filing_year": filing_year,
                    "report_year": filing["report_year"],
                    "form": form,
                    "filing_date": filing_date,
                    "accession_number": accession_number,
                    "primary_document": primary_document,
                    "source_url": source_url,
                    "local_path": manifest_relative_path(local_path),
                }
            )
            manifest["download_count"] += 1
            write_manifest(manifest)
            time.sleep(REQUEST_DELAY_SECONDS)

    return manifest


if __name__ == "__main__":
    downloaded_manifest = download_filings()
    print(f"Downloaded {downloaded_manifest['download_count']} filings.")
    print(f"Manifest saved to {OUTPUT_DIR / 'manifest.json'}")
