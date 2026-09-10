from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from docling.document_converter import DocumentConverter

# Running a file directly puts ``Data`` on sys.path, not the repository root.
# Add the root so the top-level ``Backend`` package can be imported on all
# platforms (the directory is capitalized in this repository).
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from Backend.app.Ingest.sec_tables import (  # noqa: E402
    extract_sec_tables,
    tables_to_json,
    tables_to_markdown,
)
from Data.filing_metadata import (  # noqa: E402
    validate_download_manifest,
    validate_markdown_manifest,
)

INPUT_DIR = Path(__file__).resolve().parent / "downloads"
OUTPUT_DIR = Path(__file__).resolve().parent / "markdown"
CLEAR_OUTPUT_DIR = False
SKIP_EXISTING = True


def convert_downloads_to_markdown() -> dict:
    manifest_path = INPUT_DIR / "manifest.json"

    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Missing {manifest_path}. Run 'uv run data/download.py' first "
        )

    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_manifest = validate_download_manifest(
        source_manifest,
        project_root=PROJECT_ROOT,
    )

    filings = source_manifest.get("filings", [])

    if not filings:
        raise ValueError(f"No filing listed in {manifest_path}")

    if CLEAR_OUTPUT_DIR and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    converter = DocumentConverter()

    manifest = {
        "source": source_manifest,
        "converted_at_utc": datetime.now(UTC).isoformat(),
        "form": source_manifest.get("form", "10-k"),
        "converted_count": 0,
        "filings": [],
    }

    for filing in filings:
        manifest_path = Path(filing["local_path"])
        repository_path = PROJECT_ROOT / manifest_path
        if repository_path.is_file():
            html_path = repository_path
        else:
            # Support manifests that store paths relative to Data/downloads.
            html_path = INPUT_DIR / manifest_path

        if not html_path.is_file():
            raise FileNotFoundError(f"Missing HTML file: {html_path}")

        html_relative = html_path.relative_to(INPUT_DIR)
        md_relative = html_relative.with_suffix(".md")
        md_path = OUTPUT_DIR / md_relative
        md_path.parent.mkdir(parents=True, exist_ok=True)
        tables_json_path = md_path.with_suffix(".tables.json")
        html = html_path.read_text(encoding="utf-8")
        tables = extract_sec_tables(html)

        if SKIP_EXISTING and md_path.exists():
            print(f"Skipping Existing {md_relative}")
            if tables and "# Normalized Tables" not in md_path.read_text(
                encoding="utf-8"
            ):
                with md_path.open("a", encoding="utf-8") as output:
                    output.write(
                        f"\n\n# Normalized Tables \n\n {tables_to_markdown(tables)}"
                    )
            if tables and not tables_json_path.exists():
                tables_json_path.write_text(
                    json.dumps(tables_to_json(tables), indent=2) + "\n",
                    encoding="utf-8",
                )
        else:
            print(f"Converting {html_relative}...")
            result = converter.convert(str(html_path))
            markdown = result.document.export_to_markdown()
            if tables:
                markdown = (
                    f"{markdown}\n\n# Normalized Tables\n\n{tables_to_markdown(tables)}"
                )
            md_path.write_text(markdown, encoding="utf-8")
            if tables:
                tables_json_path.write_text(
                    json.dumps(tables_to_json(tables), indent=2) + "\n",
                    encoding="utf-8",
                )

        manifest_filing = {
            **filing,
            "html_local_path": str(html_relative),
            "local_path": str(md_relative),
        }
        if tables_json_path.exists():
            manifest_filing["tables_json_local_path"] = str(
                md_relative.with_suffix(".tables.json")
            )

        manifest["filings"].append(manifest_filing)
        manifest["converted_count"] += 1
    manifest = validate_markdown_manifest(
        manifest,
        project_root=PROJECT_ROOT,
    )
    output_manifest_path = OUTPUT_DIR / "manifest.json"
    output_manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    return manifest


if __name__ == "__main__":
    result = convert_downloads_to_markdown()
    print(f"Converted {result['converted_count']} filings to markdown.")
    print(f"Markdown files are stored in {OUTPUT_DIR / 'manifest.json'}")
