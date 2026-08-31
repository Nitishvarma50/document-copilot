import json
from copy import deepcopy
from pathlib import Path

import pytest

from Data.download import load_corpus_config, validate_corpus_config

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "corpus.json"


def test_repository_corpus_config_is_valid() -> None:
    config = load_corpus_config(CONFIG_PATH)

    assert config["companies"]
    assert config["lookback_years"] > 0
    assert "10-K" in config["forms"]


def test_company_metadata_is_valid_and_unique() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    companies = config["companies"]
    ciks = []

    for ticker, company in companies.items():
        assert ticker
        assert ticker == ticker.upper()
        assert company["name"].strip()
        assert len(company["cik"]) == 10
        assert company["cik"].isdigit()
        ciks.append(company["cik"])

    assert len(ciks) == len(set(ciks))


def test_configuration_scales_beyond_five_companies() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    expanded = deepcopy(config)
    expanded["companies"]["TEST"] = {
        "name": "Test Company",
        "cik": "0000000001",
    }

    validate_corpus_config(expanded)
    assert len(expanded["companies"]) > 5


@pytest.mark.parametrize("lookback_years", [0, -1, True, "5"])
def test_invalid_lookback_years_are_rejected(lookback_years: object) -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config["lookback_years"] = lookback_years

    with pytest.raises(ValueError, match="lookback_years"):
        validate_corpus_config(config)


def test_duplicate_ciks_are_rejected() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config["companies"]["TEST"] = {
        "name": "Duplicate CIK Company",
        "cik": config["companies"]["AAPL"]["cik"],
    }

    with pytest.raises(ValueError, match="CIKs must be unique"):
        validate_corpus_config(config)
