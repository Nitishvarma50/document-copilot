from pathlib import Path

import pytest

from Data.download import (
    calculate_target_filing_years,
    extract_filings,
    find_existing_filing,
    get_user_agent,
    manifest_relative_path,
)


def sample_submission() -> dict:
    return {
        "filings": {
            "recent": {
                "form": ["10-K", "10-Q", "10-K"],
                "accessionNumber": ["one", "two", "three"],
                "primaryDocument": ["one.htm", "two.htm", "three.htm"],
                "filingDate": ["2025-02-01", "2024-08-01", "2021-02-01"],
                "reportDate": ["2024-12-31", "2024-06-30", "2020-12-31"],
            }
        }
    }


def test_calculates_previous_five_complete_years() -> None:
    assert calculate_target_filing_years(5, current_year=2026) == {
        "2021",
        "2022",
        "2023",
        "2024",
        "2025",
    }


def test_target_years_exclude_current_partial_year() -> None:
    years = calculate_target_filing_years(5, current_year=2030)

    assert "2030" not in years
    assert years == {"2025", "2026", "2027", "2028", "2029"}


def test_non_positive_lookback_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        calculate_target_filing_years(0, current_year=2026)


def test_extracts_configured_form_and_filing_years() -> None:
    filings = extract_filings(
        sample_submission(),
        target_filing_years={"2021", "2025"},
        forms={"10-K"},
    )

    assert [filing["accession_number"] for filing in filings] == ["one", "three"]


def test_ignores_unconfigured_forms() -> None:
    filings = extract_filings(
        sample_submission(),
        target_filing_years={"2024"},
        forms={"10-K"},
    )

    assert filings == []


def test_distinguishes_filing_year_from_report_year() -> None:
    filings = extract_filings(
        sample_submission(),
        target_filing_years={"2025"},
        forms={"10-K"},
    )

    assert filings[0]["filing_year"] == "2025"
    assert filings[0]["report_year"] == "2024"


def test_finds_only_the_exact_existing_filing(tmp_path: Path) -> None:
    year_dir = tmp_path / "2025"
    year_dir.mkdir()
    filing = {
        "form": "10-K",
        "filing_year": "2025",
        "filing_date": "2025-02-07",
        "accession_number": "0001018724-25-000004",
        "primary_document": "amzn-20241231.htm",
    }
    stale = year_dir / "amzn_10-k_2026-02-06_0001018724-26-000004.htm"
    stale.write_text("stale filing", encoding="utf-8")

    assert find_existing_filing(tmp_path, "AMZN", filing) is None

    expected = year_dir / "amzn_10-k_2025-02-07_0001018724-25-000004.htm"
    expected.write_text("expected filing", encoding="utf-8")

    assert find_existing_filing(tmp_path, "AMZN", filing) == expected


def test_manifest_path_is_relative_and_portable() -> None:
    filing = Path(__file__).resolve().parents[1] / "Data" / "downloads" / "filing.htm"

    assert manifest_relative_path(filing) == "Data/downloads/filing.htm"


def test_user_agent_is_required_only_for_network_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)

    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        get_user_agent()
