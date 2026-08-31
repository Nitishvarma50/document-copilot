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


def test_finds_existing_company_year_filing(tmp_path: Path) -> None:
    year_dir = tmp_path / "2025"
    year_dir.mkdir()
    expected = year_dir / "aapl_10-k_2025-01-01_accession.htm"
    expected.write_text("filing", encoding="utf-8")

    assert find_existing_filing(tmp_path, "AAPL", "10-K", "2025") == expected
    assert find_existing_filing(tmp_path, "MSFT", "10-K", "2025") is None


def test_manifest_path_is_relative_and_portable() -> None:
    filing = Path(__file__).resolve().parents[1] / "Data" / "downloads" / "filing.htm"

    assert manifest_relative_path(filing) == "Data/downloads/filing.htm"


def test_user_agent_is_required_only_for_network_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)

    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        get_user_agent()
