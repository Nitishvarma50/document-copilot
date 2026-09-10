import json
from pathlib import Path

import pytest

from Data.filing_metadata import (
    FilingMetadataError,
    expected_filing_filename,
    expected_source_url,
    validate_download_manifest,
    validate_markdown_manifest,
)


def filing_record() -> dict[str, str]:
    return {
        "ticker": "AMZN",
        "company_name": "Amazon.com, Inc.",
        "cik": "0001018724",
        "filing_year": "2025",
        "report_year": "2024",
        "form": "10-K",
        "filing_date": "2025-02-07",
        "report_date": "2024-12-31",
        "accession_number": "0001018724-25-000004",
        "primary_document": "amzn-20241231.htm",
        "source_url": (
            "https://www.sec.gov/Archives/edgar/data/1018724/"
            "000101872425000004/amzn-20241231.htm"
        ),
        "local_path": (
            "Data\\downloads\\2025\\amzn_10-k_2025-02-07_0001018724-25-000004.htm"
        ),
    }


def manifest(record: dict[str, str]) -> dict:
    return {
        "source": "SEC EDGAR",
        "target_filing_years": ["2025"],
        "company_count": 1,
        "download_count": 1,
        "filings": [record],
    }


def create_local_filing(root: Path, record: dict[str, str]) -> None:
    path = root / str(record["local_path"]).replace("\\", "/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("filing", encoding="utf-8")


def test_expected_filename_and_source_url_are_metadata_derived() -> None:
    record = filing_record()

    assert expected_filing_filename(record) == (
        "amzn_10-k_2025-02-07_0001018724-25-000004.htm"
    )
    assert expected_source_url(record) == record["source_url"]


def test_valid_manifest_is_normalized_without_mutating_input(tmp_path: Path) -> None:
    record = filing_record()
    source = manifest(record)
    create_local_filing(tmp_path, record)

    validated = validate_download_manifest(source, project_root=tmp_path)

    assert validated["filings"][0]["local_path"] == (
        "Data/downloads/2025/amzn_10-k_2025-02-07_0001018724-25-000004.htm"
    )
    assert source["filings"][0]["local_path"].startswith("Data\\downloads")


def test_stale_filename_is_rejected_even_when_file_exists(tmp_path: Path) -> None:
    record = filing_record()
    record["local_path"] = (
        "Data/downloads/2025/amzn_10-k_2026-02-06_0001018724-26-000004.htm"
    )
    create_local_filing(tmp_path, record)

    with pytest.raises(FilingMetadataError, match="local filename"):
        validate_download_manifest(manifest(record), project_root=tmp_path)


def test_inconsistent_dates_url_and_accession_are_reported_together(
    tmp_path: Path,
) -> None:
    record = filing_record()
    record["report_year"] = "2023"
    record["source_url"] = "https://example.invalid/wrong"
    record["accession_number"] = "invalid-accession"

    with pytest.raises(FilingMetadataError) as exc_info:
        validate_download_manifest(
            manifest(record), project_root=tmp_path, require_files=False
        )

    message = str(exc_info.value)
    assert "invalid accession number" in message
    assert "report_year does not match report_date" in message
    assert "source_url does not match filing metadata" in message


def test_duplicate_accessions_and_company_years_are_rejected() -> None:
    record = filing_record()
    source = manifest(record)
    source["filings"].append(record.copy())
    source["download_count"] = 2

    with pytest.raises(FilingMetadataError) as exc_info:
        validate_download_manifest(source, require_files=False)

    message = str(exc_info.value)
    assert "duplicate accession number" in message
    assert "duplicate company/form/filing-year" in message


def test_markdown_manifest_must_match_source_metadata(tmp_path: Path) -> None:
    record = filing_record()
    create_local_filing(tmp_path, record)
    source = manifest(record)
    relative = Path(expected_filing_filename(record))
    markdown_relative = Path("2025") / relative.with_suffix(".md")
    tables_relative = markdown_relative.with_suffix(".tables.json")
    for path in (markdown_relative, tables_relative):
        output = tmp_path / "Data/markdown" / path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("content", encoding="utf-8")
    converted_record = {
        **record,
        "html_local_path": (Path("2025") / relative).as_posix(),
        "local_path": markdown_relative.as_posix(),
        "tables_json_local_path": tables_relative.as_posix(),
    }
    converted = {
        "source": source,
        "converted_count": 1,
        "filings": [converted_record],
    }

    validated = validate_markdown_manifest(converted, project_root=tmp_path)

    assert validated["filings"][0]["local_path"] == markdown_relative.as_posix()


def test_markdown_manifest_rejects_changed_identity(tmp_path: Path) -> None:
    record = filing_record()
    create_local_filing(tmp_path, record)
    converted_record = {
        **record,
        "company_name": "Wrong Company",
        "html_local_path": "2025/amzn_10-k_2025-02-07_0001018724-25-000004.htm",
        "local_path": "2025/amzn_10-k_2025-02-07_0001018724-25-000004.md",
        "tables_json_local_path": (
            "2025/amzn_10-k_2025-02-07_0001018724-25-000004.tables.json"
        ),
    }

    with pytest.raises(FilingMetadataError, match="company_name"):
        validate_markdown_manifest(
            {
                "source": manifest(record),
                "converted_count": 1,
                "filings": [converted_record],
            },
            project_root=tmp_path,
            require_files=False,
        )


def test_repository_manifests_are_valid() -> None:
    root = Path(__file__).resolve().parents[1]
    download_path = root / "Data/downloads/manifest.json"
    markdown_path = root / "Data/markdown/manifest.json"
    source = json.loads(download_path.read_text(encoding="utf-8"))
    markdown = json.loads(markdown_path.read_text(encoding="utf-8"))

    validated_source = validate_download_manifest(source)
    validated_markdown = validate_markdown_manifest(markdown)

    assert len(validated_source["filings"]) == 25
    assert len(validated_markdown["filings"]) == 25
