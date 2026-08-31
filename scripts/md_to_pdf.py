#!/usr/bin/env python3
"""Render a Markdown file to a print-ready PDF via headless Chrome.

pandoc/wkhtmltopdf are not installed on this machine, but Chrome is, and its
print-to-PDF gives proper page breaks and table rendering.

Usage:
    python scripts/md_to_pdf.py docs/foo.md ~/Downloads/Foo.pdf [--title "Foo"]
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 10.5pt; line-height: 1.55; color: #1a1a1a; margin: 0;
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
h1 { font-size: 20pt; line-height: 1.25; margin: 0 0 4pt; letter-spacing: -0.01em; }
h2 { font-size: 13.5pt; margin: 20pt 0 6pt; padding-top: 8pt;
     border-top: 1px solid #d8d8d8; break-after: avoid; }
h3 { font-size: 11.5pt; margin: 14pt 0 4pt; break-after: avoid; }
h1 + p strong:first-child { color: #444; }
p { margin: 0 0 8pt; }
ul, ol { margin: 0 0 8pt; padding-left: 18pt; }
li { margin-bottom: 3pt; }
strong { font-weight: 650; }
code {
  font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 9pt;
  background: #f2f2f4; padding: 1pt 3pt; border-radius: 3px;
}
pre {
  background: #f7f7f9; border: 1px solid #e3e3e7; border-left: 3px solid #9aa0a6;
  border-radius: 4px; padding: 8pt 10pt; overflow-x: auto; break-inside: avoid;
  margin: 0 0 10pt;
}
pre code { background: none; padding: 0; font-size: 8.8pt; line-height: 1.45; }
blockquote {
  margin: 0 0 10pt; padding: 6pt 12pt; border-left: 3px solid #b9bcc0;
  background: #fafafb; color: #333; font-style: italic;
}
table {
  border-collapse: collapse; width: 100%; margin: 0 0 12pt;
  font-size: 9.2pt; break-inside: avoid;
}
th, td { border: 1px solid #dcdce0; padding: 4.5pt 7pt; text-align: left;
         vertical-align: top; }
th { background: #f1f1f4; font-weight: 650; }
tr:nth-child(even) td { background: #fbfbfc; }
hr { border: 0; border-top: 1px solid #e0e0e4; margin: 16pt 0; }
a { color: #1a4f8a; text-decoration: none; }
/* Keep a heading with the block that follows it. */
h2, h3 { break-inside: avoid; }
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("destination")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    src = Path(args.source).expanduser().resolve()
    dst = Path(args.destination).expanduser()
    if not src.exists():
        sys.exit(f"source not found: {src}")
    if not Path(CHROME).exists():
        sys.exit("Google Chrome not found; cannot render a PDF on this machine")

    text = src.read_text(encoding="utf-8")
    title = args.title or next(
        (m.group(1).strip() for m in [re.match(r"#\s+(.+)", text.splitlines()[0])] if m),
        src.stem)

    body = markdown.markdown(
        text, extensions=["tables", "fenced_code", "sane_lists", "attr_list"])
    html = (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{title}</title><style>{CSS}</style></head>"
            f"<body>{body}</body></html>")

    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page.html"
        page.write_text(html, encoding="utf-8")
        pdf = Path(tmp) / "out.pdf"
        # --headless=new is required on current Chrome; the old flag silently
        # produces nothing on some builds.
        cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
               "--no-pdf-header-footer", f"--print-to-pdf={pdf}", page.as_uri()]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if not pdf.exists() or pdf.stat().st_size < 1000:
            sys.exit(f"Chrome did not produce a PDF.\n{r.stdout}\n{r.stderr}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(pdf), str(dst))

    print(f"✅ {dst}  ({dst.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
