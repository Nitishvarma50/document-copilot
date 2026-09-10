from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "Data" / "downloads" / "manifest.json"
_ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_REQUIRED_FIELDS = (
    "ticker",
    "company_name",
    "cik",
    "filing_year",
    "report_year",
    "form",
    "filing_date",
    "report_date",
    "accession_number",
    "primary_document",
    "source_url",
    "local_path",
)


class FilingMetadataError(ValueError):
    """Raised when filing metadata cannot be trusted for ingestion."""


def expected_filing_filename(filing: dict[str, Any]) -> str:
    """Build the canonical local filename for a filing manifest record."""
    suffix = Path(str(filing["primary_document"])).suffix or ".html"
    return (
        f"{str(filing['ticker']).lower()}_{str(filing['form']).lower()}_"
        f"{filing['filing_date']}_{filing['accession_number']}{suffix}"
    )


def expected_source_url(filing: dict[str, Any]) -> str:
    """Build the canonical SEC archive URL for a filing manifest record."""
    cik = str(int(str(filing["cik"])))
    accession = str(filing["accession_number"]).replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/"
        f"{accession}/{filing['primary_document']}"
    )


def validate_download_manifest(
    manifest: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    require_files: bool = True,
) -> dict[str, Any]:
    """Validate and normalize a downloaded-corpus manifest.

    The returned copy uses repository-relative POSIX paths. All validation errors
    are reported together so stale manifests can be diagnosed in one run.
    """
    normalized = deepcopy(manifest)
    filings = normalized.get("filings")
    if not isinstance(filings, list) or not filings:
        raise FilingMetadataError("manifest: filings must be a non-empty list")

    errors: list[str] = []
    accessions: set[str] = set()
    company_years: set[tuple[str, str, str]] = set()

    for index, filing in enumerate(filings):
        label = f"filings[{index}]"
        if not isinstance(filing, dict):
            errors.append(f"{label}: must be an object")
            continue

        missing = [field for field in _REQUIRED_FIELDS if not filing.get(field)]
        if missing:
            errors.append(f"{label}: missing {', '.join(missing)}")
            continue

        ticker = str(filing["ticker"])
        cik = str(filing["cik"])
        form = str(filing["form"])
        filing_year = str(filing["filing_year"])
        report_year = str(filing["report_year"])
        filing_date = str(filing["filing_date"])
        report_date = str(filing["report_date"])
        accession = str(filing["accession_number"])

        if ticker != ticker.upper() or not ticker:
            errors.append(f"{label}: ticker must be uppercase")
        if len(cik) != 10 or not cik.isdigit():
            errors.append(f"{label}: CIK must contain exactly ten digits")
        if not _ACCESSION_RE.fullmatch(accession):
            errors.append(f"{label}: invalid accession number {accession!r}")

        for field_name, value in (
            ("filing_date", filing_date),
            ("report_date", report_date),
        ):
            try:
                date.fromisoformat(value)
            except ValueError:
                errors.append(f"{label}: invalid {field_name} {value!r}")

        if filing_date[:4] != filing_year:
            errors.append(f"{label}: filing_year does not match filing_date")
        if report_date[:4] != report_year:
            errors.append(f"{label}: report_year does not match report_date")

        local_path_text = str(filing["local_path"]).replace("\\", "/")
        local_path = Path(local_path_text)
        expected_name = expected_filing_filename(filing)
        if local_path.name != expected_name:
            errors.append(
                f"{label}: local filename {local_path.name!r} does not match "
                f"metadata ({expected_name!r})"
            )
        expected_parent = Path("Data") / "downloads" / filing_year
        if local_path.parent.as_posix() != expected_parent.as_posix():
            errors.append(
                f"{label}: local_path must be under {expected_parent.as_posix()}"
            )
        if local_path.is_absolute() or ".." in local_path.parts:
            errors.append(f"{label}: local_path must be repository-relative")
        elif require_files and not (project_root / local_path).is_file():
            errors.append(f"{label}: local file does not exist: {local_path_text}")
        filing["local_path"] = local_path.as_posix()

        expected_url = expected_source_url(filing)
        if filing["source_url"] != expected_url:
            errors.append(f"{label}: source_url does not match filing metadata")

        if accession in accessions:
            errors.append(f"{label}: duplicate accession number {accession}")
        accessions.add(accession)

        company_year = (ticker, form, filing_year)
        if company_year in company_years:
            errors.append(
                f"{label}: duplicate company/form/filing-year record "
                f"{ticker}/{form}/{filing_year}"
            )
        company_years.add(company_year)

    declared_count = normalized.get("download_count")
    if declared_count != len(filings):
        errors.append(
            f"manifest: download_count {declared_count!r} does not match "
            f"{len(filings)} filing records"
        )

    target_years = {str(year) for year in normalized.get("target_filing_years", [])}
    if target_years:
        tickers = {
            str(filing.get("ticker")) for filing in filings if isinstance(filing, dict)
        }
        for ticker in sorted(tickers):
            actual_years = {
                str(filing.get("filing_year"))
                for filing in filings
                if isinstance(filing, dict) and filing.get("ticker") == ticker
            }
            if actual_years != target_years:
                errors.append(
                    f"manifest: {ticker} filing years {sorted(actual_years)} do not "
                    f"match target years {sorted(target_years)}"
                )

    if errors:
        raise FilingMetadataError("Invalid filing metadata:\n- " + "\n- ".join(errors))
    return normalized


def validate_markdown_manifest(
    manifest: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    require_files: bool = True,
) -> dict[str, Any]:
    """Validate converted files against their trusted download records."""
    normalized = deepcopy(manifest)
    source = normalized.get("source")
    if not isinstance(source, dict):
        raise FilingMetadataError("markdown manifest: source manifest is missing")
    validated_source = validate_download_manifest(
        source,
        project_root=project_root,
        require_files=require_files,
    )
    normalized["source"] = validated_source
    source_by_accession = {
        filing["accession_number"]: filing for filing in validated_source["filings"]
    }

    filings = normalized.get("filings")
    if not isinstance(filings, list):
        raise FilingMetadataError("markdown manifest: filings must be a list")

    errors: list[str] = []
    seen: set[str] = set()
    identity_fields = (
        "ticker",
        "company_name",
        "cik",
        "filing_year",
        "report_year",
        "report_date",
        "form",
        "filing_date",
        "accession_number",
        "primary_document",
        "source_url",
    )

    for index, filing in enumerate(filings):
        label = f"markdown filings[{index}]"
        if not isinstance(filing, dict):
            errors.append(f"{label}: must be an object")
            continue
        accession = str(filing.get("accession_number", ""))
        source_filing = source_by_accession.get(accession)
        if source_filing is None:
            errors.append(f"{label}: accession is absent from the source manifest")
            continue
        if accession in seen:
            errors.append(f"{label}: duplicate accession number {accession}")
        seen.add(accession)

        for field in identity_fields:
            if filing.get(field) != source_filing.get(field):
                errors.append(f"{label}: {field} does not match the source manifest")

        expected_html = Path(source_filing["local_path"]).relative_to(
            Path("Data/downloads")
        )
        expected_markdown = expected_html.with_suffix(".md")
        expected_tables = expected_html.with_suffix(".tables.json")
        for field, expected, base_dir in (
            ("html_local_path", expected_html, project_root / "Data/downloads"),
            ("local_path", expected_markdown, project_root / "Data/markdown"),
            (
                "tables_json_local_path",
                expected_tables,
                project_root / "Data/markdown",
            ),
        ):
            actual_text = str(filing.get(field, "")).replace("\\", "/")
            actual = Path(actual_text)
            if actual.as_posix() != expected.as_posix():
                errors.append(
                    f"{label}: {field} {actual.as_posix()!r} does not match "
                    f"{expected.as_posix()!r}"
                )
            elif require_files and not (base_dir / actual).is_file():
                errors.append(f"{label}: {field} file does not exist: {actual_text}")
            filing[field] = actual.as_posix()

    if len(filings) != len(validated_source["filings"]):
        errors.append(
            "markdown manifest: converted filing count does not match source manifest"
        )
    if normalized.get("converted_count") != len(filings):
        errors.append(
            "markdown manifest: converted_count does not match filing records"
        )
    if seen != set(source_by_accession):
        errors.append("markdown manifest: converted accession set is incomplete")

    if errors:
        raise FilingMetadataError(
            "Invalid converted filing metadata:\n- " + "\n- ".join(errors)
        )
    return normalized


def main() -> None:
    manifest = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    validated = validate_download_manifest(manifest)
    print(f"Validated {len(validated['filings'])} download metadata records.")

    markdown_path = PROJECT_ROOT / "Data" / "markdown" / "manifest.json"
    if markdown_path.is_file():
        markdown = json.loads(markdown_path.read_text(encoding="utf-8"))
        converted = validate_markdown_manifest(markdown)
        print(f"Validated {len(converted['filings'])} converted metadata records.")


if __name__ == "__main__":
    main()
