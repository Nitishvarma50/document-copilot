# Continuous Integration setup

This document is the source of truth for the Document Copilot Continuous Integration (CI) pipeline. It records what CI checks, why each check exists, how to run the same checks locally, and how the workflow should expand as the backend and frontend are implemented.

> Status: implemented locally. All Python checks pass; the GitHub Actions run must still be confirmed after pushing.

## Goals

CI must:

- catch errors before code is merged;
- produce the same result locally and on GitHub Actions;
- validate source code without relying on production services;
- remain scalable as companies are added to the filing corpus;
- avoid network calls to SEC EDGAR during tests;
- never require production credentials;
- eventually validate the Python backend and TypeScript frontend independently.

CI is not responsible for deployment, downloading the full filing corpus, applying production database migrations, or running live OpenAI/Supabase requests.

## When CI runs

The workflow will run for every push and pull request:

```yaml
on:
  push:
  pull_request:
```

A manual trigger may also be added for troubleshooting:

```yaml
  workflow_dispatch:
```

## Planned repository files

```text
.github/
└── workflows/
    └── ci.yml

tests/
├── test_corpus_config.py
└── test_download.py

pyproject.toml                 # development dependencies and tool settings
config/corpus.json             # corpus configuration validated by CI
Docs/Guides/ci-setup.md        # this document
```

When the backend and frontend exist, CI will also cover:

```text
backend/tests/
frontend/
```

## Tooling

### uv

`uv` installs the locked Python dependencies and runs Python tools. CI will use:

```bash
uv sync --locked --all-groups
```

`--locked` makes CI fail if `pyproject.toml` and `uv.lock` disagree. Developers must update the lock file intentionally with:

```bash
uv lock
```

### Ruff

Ruff provides Python linting, import checks, and formatting.

```bash
uv run ruff check .
uv run ruff format --check .
```

To fix issues locally:

```bash
uv run ruff check . --fix
uv run ruff format .
```

### mypy

Mypy checks Python type annotations:

```bash
uv run mypy Data main.py tests
```

The checked paths will change when code moves into `backend/`.

### pytest

Pytest runs deterministic unit tests:

```bash
uv run pytest
```

Tests must not download SEC filings or require external services unless they are explicitly marked as integration tests and run in a separate workflow.

### Python compilation

A compile check catches syntax errors even in files not reached by tests:

```bash
uv run python -m compileall -q Data main.py tests
```

## Development dependencies

The root `pyproject.toml` will contain a development dependency group:

```toml
[dependency-groups]
dev = [
    "mypy",
    "pytest",
    "ruff",
]
```

Runtime dependencies and CI/development tools must remain separate.

## Python version policy

The project currently supports:

```toml
requires-python = ">=3.12,<3.15"
```

The initial CI job will use Python 3.12 because it is stable and broadly supported. A version matrix can be added later if the team wants to guarantee support for Python 3.12, 3.13, and 3.14.

## Corpus configuration policy

`config/corpus.json` is the source of truth for:

- configured companies;
- company names and CIKs;
- filing forms;
- the number of previous complete filing years to retrieve.

The configuration should use a lookback value instead of fixed calendar years:

```json
{
  "forms": ["10-K"],
  "lookback_years": 5,
  "companies": {
    "AAPL": {
      "name": "Apple Inc.",
      "cik": "0000320193"
    }
  }
}
```

The downloader will calculate the previous five complete filing years relative to the current UTC year. The current partial year is excluded. For example, with a reference year of 2026, the target filing years are 2021–2025.

CI must not assert that exactly five companies exist. The corpus is expected to grow after pilot approval.

## Corpus configuration tests

`tests/test_corpus_config.py` will verify that:

- [ ] `config/corpus.json` contains valid JSON.
- [ ] At least one company is configured.
- [ ] Every ticker is a non-empty uppercase string.
- [ ] Every company has a non-empty name.
- [ ] Every CIK contains exactly ten numeric characters.
- [ ] Company CIKs are unique.
- [ ] `lookback_years` is a positive integer.
- [ ] At least one filing form is configured.
- [ ] Every filing form is a non-empty string.
- [ ] `10-K` is included in the current corpus configuration.
- [ ] Adding another valid company does not break validation.

The tests intentionally do not impose a maximum company count.

## Downloader tests

`tests/test_download.py` will use in-memory SEC submission fixtures. It will verify that:

- [ ] Target years are calculated dynamically from a supplied reference year.
- [ ] The current partial year is excluded.
- [ ] Exactly `lookback_years` complete years are returned.
- [ ] Filing extraction includes configured forms and filing years.
- [ ] Filing extraction ignores unconfigured forms such as `10-Q`.
- [ ] Filing year and report year are stored separately.
- [ ] A filing can be filed in the year after its report year.
- [ ] Missing filing years are reported clearly.
- [ ] Existing company/year filing files are skipped.
- [ ] Manifest paths are relative to the repository.

Year tests will pass an explicit reference year instead of depending on the clock:

```python
def test_previous_five_complete_years():
    assert calculate_target_filing_years(
        lookback_years=5,
        current_year=2026,
    ) == {"2021", "2022", "2023", "2024", "2025"}
```

Production code will omit `current_year`, causing the function to use the current UTC year.

## Import and environment behavior

Unit tests must be able to import downloader functions without a local `.env` file. `SEC_USER_AGENT` validation should happen only when a network request is made, not at module import time.

Expected behavior:

- importing `Data.download` does not require credentials;
- pure functions can be tested without environment variables;
- a real SEC request fails clearly when `SEC_USER_AGENT` is absent;
- no test contains a real person's email address.

## Initial GitHub Actions workflow

The planned `.github/workflows/ci.yml` is:

```yaml
name: CI

on:
  push:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  python:
    name: Python checks
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Install Python
        run: uv python install 3.12

      - name: Install locked dependencies
        run: uv sync --locked --all-groups

      - name: Lint
        run: uv run ruff check .

      - name: Check formatting
        run: uv run ruff format --check .

      - name: Type check
        run: uv run mypy Data main.py tests

      - name: Run tests
        run: uv run pytest

      - name: Compile Python files
        run: uv run python -m compileall -q Data main.py tests
```

Action versions must be reviewed when the workflow is implemented. Pinning actions to immutable commit SHAs can be added for stronger supply-chain security.

## Secrets and external services

The initial CI workflow requires no secrets. It must not receive:

- `SEC_USER_AGENT`;
- `OPENAI_API_KEY`;
- `SUPABASE_SERVICE_ROLE_KEY`;
- production database credentials;
- a local `.env` file.

Later integration tests requiring Supabase or OpenAI must be isolated in a separate manually approved workflow or protected environment. Pull requests from forks must never receive production secrets.

## Frontend CI expansion

After the Vite frontend exists, add a separate `frontend` job that:

```bash
pnpm install --frozen-lockfile
pnpm lint
pnpm tsc --noEmit
pnpm test
pnpm build
```

The frontend job should use the Node version documented by the project and should cache the pnpm store. A production build must not require secret values; safe test placeholders may be supplied for public `VITE_*` configuration when necessary.

## Backend CI expansion

After the FastAPI backend exists, move backend checks into a dedicated job and add:

- backend unit tests;
- API tests using FastAPI's test client;
- Alembic migration checks;
- a test that upgrades an empty PostgreSQL database to `head`;
- authentication and ownership tests;
- retrieval and grounding tests with deterministic fixtures.

Database integration tests should use an ephemeral PostgreSQL service with `pgvector`, not the production Supabase database.

## Checks intentionally excluded from initial CI

The initial pipeline will not:

- download SEC filings;
- validate live SEC availability;
- call OpenAI;
- connect to production Supabase;
- deploy to Railway;
- commit generated manifests or filing content;
- measure analyst answer quality against live models.

Those concerns belong in separate integration, evaluation, or deployment workflows.

## Local pre-push checklist

Run these commands from the repository root before pushing:

```bash
uv sync --locked --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy Data main.py tests
uv run pytest
uv run python -m compileall -q Data main.py tests
```

All commands should pass locally before CI is expected to pass on GitHub.

## Branch protection

After the workflow passes on the default branch, configure GitHub branch protection for `main`:

- require a pull request before merging;
- require the Python CI status check;
- require the branch to be up to date before merging;
- prevent force pushes;
- prevent branch deletion;
- optionally require one approving review.

## Failure troubleshooting

### Lock-file failure

Run:

```bash
uv lock
uv sync --locked --all-groups
```

Commit both `pyproject.toml` and `uv.lock`.

### Ruff failure

Run:

```bash
uv run ruff check . --fix
uv run ruff format .
```

Review changes before committing them.

### mypy failure

Fix the reported type mismatch rather than adding broad ignores. Use a targeted ignore only when a third-party library has incomplete type information and document why.

### pytest failure

Run the failing test directly with verbose output:

```bash
uv run pytest path/to/test_file.py::test_name -vv
```

Do not make network-dependent tests pass by adding production credentials to CI.

## Implementation checklist

- [x] Replace fixed `target_filing_years` with `lookback_years` in `config/corpus.json`.
- [x] Add a deterministic target-year calculation function.
- [x] Delay `SEC_USER_AGENT` validation until a network request occurs.
- [x] Add the development dependency group.
- [x] Configure Ruff.
- [x] Configure mypy.
- [x] Configure pytest.
- [x] Add corpus configuration tests.
- [x] Add downloader unit tests.
- [x] Run and fix all checks locally.
- [x] Add `.github/workflows/ci.yml`.
- [ ] Push the workflow and confirm it passes in GitHub Actions.
- [ ] Enable branch protection after the required status check exists.
- [x] Update this document whenever CI commands or policies change.
