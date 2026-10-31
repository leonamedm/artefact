"""Build the submission PDF (README + documentation) required by the application form.

Requires pandoc and a Chromium available to Playwright (optional dev tools, not needed to run
the agent). Set CHROMIUM_PATH to use an existing Chromium instead of Playwright's own.
    uv run --with playwright python tools/build_submission_pdf.py   # -> dist/submission.pdf
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CSS = """
body { font-family: -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; color: #1a1a1a;
       background: #fff; max-width: 860px; margin: 0 auto; font-size: 11pt; line-height: 1.5; }
h1 { border-bottom: 2px solid #222; padding-bottom: .2em; page-break-before: always; }
h1:first-of-type { page-break-before: avoid; }
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; margin: .8em 0; }
th, td { border: 1px solid #ccc; padding: 4px 6px; vertical-align: top; text-align: left; }
th { background: #f3f3f3; }
code, pre { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 9pt; }
pre { background: #f6f6f6; padding: 8px; white-space: pre-wrap; border-radius: 4px; }
details { margin: .5em 0; } summary { color: #555; }
"""


def documents() -> list[Path]:
    docs = ROOT / "docs"
    return [
        ROOT / "README.md",
        docs / "architecture.md",
        docs / "data-findings.md",
        docs / "adr" / "README.md",
        *sorted((docs / "adr").glob("0*.md")),
        *sorted((ROOT / "examples").glob("0*.md")),
    ]


def main() -> int:
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    html_path = out_dir / "submission.html"
    pdf_path = out_dir / "submission.pdf"
    css_path = out_dir / "submission.css"
    css_path.write_text(CSS, encoding="utf-8")

    sources = [str(p) for p in documents() if p.exists()]
    subprocess.run(
        [
            "pandoc",
            *sources,
            "--from",
            "gfm",
            "--to",
            "html5",
            "--standalone",
            "--embed-resources",
            "--css",
            str(css_path),
            "--metadata",
            "pagetitle=Empório da Música — Customer Service Agent",
            "--output",
            str(html_path),
        ],
        check=True,
    )

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        page = browser.new_page()
        page.goto(html_path.as_uri())
        page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin={"top": "18mm", "bottom": "18mm", "left": "16mm", "right": "16mm"},
        )
        browser.close()
    print(f"Saved {pdf_path} ({len(sources)} documents)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
