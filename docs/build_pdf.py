"""Build a styled PDF from a Markdown file in docs/.

Usage:  python docs/build_pdf.py [other_file.md]

The Markdown (which may contain HTML blocks) is converted to an HTML page styled by
docs/assets/guide.css, then printed to PDF with headless Edge or Chrome. The HTML page
is kept next to the PDF so the guide can also be read in a browser.
"""
import os
import subprocess
import sys
from pathlib import Path

from markdown_it import MarkdownIt

DOCS = Path(__file__).resolve().parent
BROWSERS = [
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", "")) / "Google/Chrome/Application/chrome.exe",
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/usr/bin/google-chrome"),
    Path("/usr/bin/chromium"),
]

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<link rel="stylesheet" href="assets/guide.css">
</head>
<body>
{body}
</body>
</html>
"""


def find_browser() -> Path:
    for path in BROWSERS:
        if path.is_file():
            return path
    raise SystemExit("No Edge or Chrome found. Open the generated .html file and use Print > Save as PDF.")


def build(source: Path) -> Path:
    body = MarkdownIt("commonmark", {"html": True}).enable("table").render(source.read_text(encoding="utf-8"))
    html = source.with_suffix(".html")
    html.write_text(PAGE.format(title=source.stem.replace("_", " "), body=body), encoding="utf-8")

    pdf = source.with_suffix(".pdf")
    subprocess.run(
        [str(find_browser()), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={pdf}", html.as_uri()],
        check=True, capture_output=True, timeout=120,
    )
    return pdf


if __name__ == "__main__":
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DOCS / "SunDesk_Copilot_Project_Guide.md"
    print(f"Wrote {build(source.resolve())}")
