"""Tests for contact-line normalization and the LaTeX subtitle/markdown line.

These cover the structured ``ContactInfo`` -> ``\\href{...}{... \\fa<Icon>\\ ...}``
pipeline in ``jobapply.nodes.render``.
"""

from __future__ import annotations

from jobapply.models import ContactInfo, TailoredResume
from jobapply.nodes.render import (
    _GITHUB_RE,
    _LINKEDIN_RE,
    _MEDIUM_RE,
    _TWITTER_RE,
    _normalize_email,
    _normalize_phone,
    _normalize_portfolio,
    _normalize_via_regex,
    build_contact_markdown,
    build_contact_subtitle,
    fill_resume_tex,
)


def test_phone_normalizes_to_tel_with_digits_only() -> None:
    href, label = _normalize_phone("+91 84850-19026")
    assert href == "tel:+918485019026"
    assert label == "+91 84850-19026"


def test_email_uses_mailto_prefix() -> None:
    href, label = _normalize_email("arun.a@example.com")
    assert href == "mailto:arun.a@example.com"
    assert label == "arun.a@example.com"


def test_github_extracts_username_from_url() -> None:
    href, label = _normalize_via_regex(
        "https://github.com/arun2728",
        _GITHUB_RE,
        "https://github.com/",
        "github",
    )
    assert href == "https://github.com/arun2728"
    assert label == "github/arun2728"


def test_github_accepts_bare_username() -> None:
    href, label = _normalize_via_regex(
        "@arun2728",
        _GITHUB_RE,
        "https://github.com/",
        "github",
    )
    assert href == "https://github.com/arun2728"
    assert label == "github/arun2728"


def test_linkedin_handles_in_path() -> None:
    href, label = _normalize_via_regex(
        "https://linkedin.com/in/arun-addagatla/",
        _LINKEDIN_RE,
        "https://linkedin.com/in/",
        "linkedin",
    )
    assert href == "https://linkedin.com/in/arun-addagatla"
    assert label == "linkedin/arun-addagatla"


def test_medium_keeps_at_in_label() -> None:
    href, label = _normalize_via_regex(
        "https://medium.com/@arunaddagatla",
        _MEDIUM_RE,
        "https://medium.com/@",
        "medium",
        keep_at_in_label=True,
    )
    assert href == "https://medium.com/@arunaddagatla"
    assert label == "medium/@arunaddagatla"


def test_twitter_recognises_x_com() -> None:
    href, label = _normalize_via_regex(
        "https://x.com/arun2728",
        _TWITTER_RE,
        "https://twitter.com/",
        "twitter",
    )
    assert href == "https://twitter.com/arun2728"
    assert label == "twitter/arun2728"


def test_portfolio_strips_www_for_label_keeps_full_url() -> None:
    href, label = _normalize_portfolio("https://www.arun.dev/")
    assert href == "https://www.arun.dev/"
    assert label == "arun.dev"


def test_portfolio_adds_https_when_missing() -> None:
    href, _ = _normalize_portfolio("arunaddagatla.vercel.app")
    assert href.startswith("https://")


def test_subtitle_emits_href_blocks_with_correct_icons() -> None:
    contact = ContactInfo(
        email="arun.a@example.com",
        phone="+91 84850-19026",
        portfolio="https://arunaddagatla.vercel.app/",
        github="https://github.com/arun2728",
        linkedin="https://linkedin.com/in/arun-addagatla/",
    )
    subtitle = build_contact_subtitle(contact)
    assert r"\href{tel:+918485019026}" in subtitle
    assert r"\faPhone" in subtitle
    assert r"\href{mailto:arun.a@example.com}" in subtitle
    assert r"\faEnvelope" in subtitle
    assert r"\href{https://arunaddagatla.vercel.app/}" in subtitle
    assert r"\faGlobe" in subtitle
    assert r"\href{https://github.com/arun2728}" in subtitle
    assert r"\faGithub" in subtitle
    assert r"github/arun2728" in subtitle
    assert r"\href{https://linkedin.com/in/arun-addagatla}" in subtitle
    assert r"\faLinkedin" in subtitle
    assert " ~ | ~ " in subtitle


def test_subtitle_escapes_percent_in_url() -> None:
    contact = ContactInfo(portfolio="https://example.com/foo%20bar")
    subtitle = build_contact_subtitle(contact)
    assert r"\%20" in subtitle
    assert "%20bar" not in subtitle.replace(r"\%20", "")


def test_subtitle_escapes_underscore_in_label() -> None:
    contact = ContactInfo(email="arun_a@example.com")
    subtitle = build_contact_subtitle(contact)
    assert r"arun\_a@example.com" in subtitle


def test_subtitle_empty_for_blank_contact() -> None:
    assert build_contact_subtitle(ContactInfo()) == ""
    assert build_contact_markdown(ContactInfo()) == ""


def test_markdown_line_uses_pipe_separated_links() -> None:
    contact = ContactInfo(
        email="arun.a@example.com",
        github="https://github.com/arun2728",
    )
    line = build_contact_markdown(contact)
    assert "[arun.a@example.com](mailto:arun.a@example.com)" in line
    assert "[github/arun2728](https://github.com/arun2728)" in line
    assert " | " in line


def test_fill_resume_tex_uses_structured_contact() -> None:
    tr = TailoredResume(
        document_title="Arun Addagatla",
        contact_line="should not appear",
        contact=ContactInfo(
            email="arun.a@example.com",
            phone="+918485019026",
            github="arun2728",
        ),
    )
    out = fill_resume_tex(tr)
    assert r"\documentTitle{Arun Addagatla}" in out
    assert r"\href{mailto:arun.a@example.com}" in out
    assert r"\href{tel:+918485019026}" in out
    assert r"\href{https://github.com/arun2728}" in out
    assert "should not appear" not in out


def test_fill_resume_tex_falls_back_to_contact_line() -> None:
    tr = TailoredResume(
        document_title="Plain User",
        contact_line="plain@example.com | github.com/plain",
    )
    out = fill_resume_tex(tr)
    assert "plain@example.com" in out
    assert r"\href{" not in out
