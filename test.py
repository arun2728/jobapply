"""Compile a .tex file to PDF using a remote LaTeX HTTP API.

Avoids needing a local TeX install. Uses YtoTech's latex-on-http service
(https://github.com/YtoTech/latex-on-http), which can also be self-hosted
via Docker if you outgrow the public instance.
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

LATEX_API_URL = "https://latex.ytotech.com/builds/sync"

TEX_PATH = Path(
    "/Users/arun/Developer/jobs-search-and-apply-api/output/"
    "run-20260426-111840/jobs/"
    "applied-scientist-sponsored-products-off-search-auction-amazon-com-85bde5229205/"
    "cover_letter.tex"
)
OUT_PATH = Path("cover_letter-test.pdf")


def compile_tex_to_pdf(tex_path: Path, out_path: Path) -> None:
    payload = {
        "compiler": "pdflatex",
        "resources": [
            {
                "main": True,
                "content": tex_path.read_text(encoding="utf-8"),
            }
        ],
    }

    resp = requests.post(LATEX_API_URL, json=payload, timeout=120)

    if resp.status_code != 201:
        # latex-on-http returns JSON with a build log on failure.
        print(f"Compilation failed (HTTP {resp.status_code}):", file=sys.stderr)
        try:
            print(resp.json(), file=sys.stderr)
        except ValueError:
            print(resp.text, file=sys.stderr)
        sys.exit(1)

    out_path.write_bytes(resp.content)
    print(f"Wrote {out_path} ({len(resp.content):,} bytes)")


if __name__ == "__main__":
    compile_tex_to_pdf(TEX_PATH, OUT_PATH)
