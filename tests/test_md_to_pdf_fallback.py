"""Sanity checks for the markdown-to-PDF fallback chain.

``md_to_pdf`` walks three backends in order:

1. ``pypandoc`` — best output when pandoc + LaTeX exist.
2. WeasyPrint — needs Pango/Cairo (typically ``brew install pango``).
3. ``fpdf2`` — pure Python, no native deps; always works.

These tests verify the order, that we stop at the first success, and that we
return False (without raising) when every backend is monkeypatched to fail.
The fpdf2 path is also exercised end-to-end since it has no system deps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from jobapply.nodes import render


def test_md_to_pdf_uses_pandoc_when_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    md = tmp_path / "doc.md"
    md.write_text("# Hello\n", encoding="utf-8")
    pdf = tmp_path / "doc.pdf"

    calls: dict[str, int] = {"pandoc": 0, "weasy": 0, "fpdf": 0}

    def fake_pandoc(_md: Path, p: Path) -> bool:
        calls["pandoc"] += 1
        p.write_bytes(b"%PDF-1.4 fake\n")
        return True

    def fake_weasy(*_a: Any, **_kw: Any) -> bool:
        calls["weasy"] += 1
        return True

    def fake_fpdf(*_a: Any, **_kw: Any) -> bool:
        calls["fpdf"] += 1
        return True

    monkeypatch.setattr(render, "_md_to_pdf_pandoc", fake_pandoc)
    monkeypatch.setattr(render, "_md_to_pdf_weasyprint", fake_weasy)
    monkeypatch.setattr(render, "_md_to_pdf_fpdf2", fake_fpdf)

    assert render.md_to_pdf(md, pdf) is True
    assert calls == {"pandoc": 1, "weasy": 0, "fpdf": 0}
    assert pdf.is_file()


def test_md_to_pdf_falls_back_to_weasyprint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    md = tmp_path / "doc.md"
    md.write_text("# Hi\n", encoding="utf-8")
    pdf = tmp_path / "doc.pdf"

    monkeypatch.setattr(render, "_md_to_pdf_pandoc", lambda _md, _p: False)
    fpdf_called: list[bool] = []

    def fake_fpdf(_md: Path, _p: Path) -> bool:
        fpdf_called.append(True)
        return True

    monkeypatch.setattr(render, "_md_to_pdf_fpdf2", fake_fpdf)

    def fake_weasy(_md: Path, p: Path) -> bool:
        p.write_bytes(b"%PDF-1.4 fake-weasy\n")
        return True

    monkeypatch.setattr(render, "_md_to_pdf_weasyprint", fake_weasy)

    assert render.md_to_pdf(md, pdf) is True
    assert pdf.read_bytes().startswith(b"%PDF")
    # fpdf2 should not be invoked because weasyprint succeeded.
    assert fpdf_called == []


def test_md_to_pdf_falls_back_to_fpdf2_when_pandoc_and_weasy_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    md = tmp_path / "doc.md"
    md.write_text("# Hi\n", encoding="utf-8")
    pdf = tmp_path / "doc.pdf"

    monkeypatch.setattr(render, "_md_to_pdf_pandoc", lambda _md, _p: False)
    monkeypatch.setattr(render, "_md_to_pdf_weasyprint", lambda _md, _p: False)

    def fake_fpdf(_md: Path, p: Path) -> bool:
        p.write_bytes(b"%PDF-1.4 fake-fpdf\n")
        return True

    monkeypatch.setattr(render, "_md_to_pdf_fpdf2", fake_fpdf)

    assert render.md_to_pdf(md, pdf) is True
    assert pdf.read_bytes().startswith(b"%PDF")


def test_md_to_pdf_returns_false_when_all_backends_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    md = tmp_path / "doc.md"
    md.write_text("# Hi\n", encoding="utf-8")
    pdf = tmp_path / "doc.pdf"

    monkeypatch.setattr(render, "_md_to_pdf_pandoc", lambda _md, _p: False)
    monkeypatch.setattr(render, "_md_to_pdf_weasyprint", lambda _md, _p: False)
    monkeypatch.setattr(render, "_md_to_pdf_fpdf2", lambda _md, _p: False)

    assert render.md_to_pdf(md, pdf) is False
    assert not pdf.exists()


def test_fpdf2_backend_renders_real_pdf_bytes(tmp_path: Path) -> None:
    """End-to-end fpdf2 render — pure Python, should work on any machine."""
    md = tmp_path / "doc.md"
    md.write_text(
        "# Test Resume\n\n## Skills\n\n- Python\n- LaTeX\n\n"
        "**Bold** and *italic* with [link](https://example.com).\n",
        encoding="utf-8",
    )
    pdf = tmp_path / "doc.pdf"

    assert render._md_to_pdf_fpdf2(md, pdf) is True
    assert pdf.is_file()
    head = pdf.read_bytes()[:5]
    assert head.startswith(b"%PDF-")
    assert pdf.stat().st_size > 500


def test_weasyprint_probe_is_silent_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """When WeasyPrint can't load Pango/Cairo, the probe must be silent
    (no big banner on stderr) and must only run once across many calls.
    """
    import contextlib
    import io

    monkeypatch.setattr(render, "_weasyprint_probe_cache", None)

    cap_err = io.StringIO()
    cap_out = io.StringIO()
    with contextlib.redirect_stderr(cap_err), contextlib.redirect_stdout(cap_out):
        first = render._weasyprint_available()
        # Sentinel: pretend the probe is not cached, then call again — but
        # the cache mechanism should still kick in for the second loop.
        for _ in range(5):
            render._weasyprint_available()

    assert isinstance(first, bool)
    output = cap_err.getvalue() + cap_out.getvalue()
    assert "could not import" not in output.lower(), output
    assert render._weasyprint_probe_cache is first


def test_weasyprint_md_call_uses_cached_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``_md_to_pdf_weasyprint`` must short-circuit when the probe says no,
    so the WeasyPrint banner can't reappear on every per-job call.
    """
    monkeypatch.setattr(render, "_weasyprint_probe_cache", False)
    md = tmp_path / "x.md"
    md.write_text("# hi\n", encoding="utf-8")
    pdf = tmp_path / "x.pdf"
    assert render._md_to_pdf_weasyprint(md, pdf) is False
    assert not pdf.exists()


def test_weasyprint_backend_emits_pdf_bytes_when_installed(tmp_path: Path) -> None:
    """Real end-to-end render via WeasyPrint when cairo/pango are available.

    Skips cleanly on machines without the system libs so CI doesn't flake.
    """
    try:
        import weasyprint  # noqa: F401
    except Exception:
        pytest.skip("weasyprint not importable in this environment")

    md = tmp_path / "doc.md"
    md.write_text(
        "# Test Resume\n\n## Skills\n\n- Python\n- LaTeX\n\n*Italic* and **bold**.\n",
        encoding="utf-8",
    )
    pdf = tmp_path / "doc.pdf"

    ok = render._md_to_pdf_weasyprint(md, pdf)
    if not ok:
        pytest.skip("weasyprint failed to render (likely missing cairo/pango)")
    assert pdf.is_file()
    head = pdf.read_bytes()[:5]
    assert head.startswith(b"%PDF-")
