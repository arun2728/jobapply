"""Tests for ``profile_validation`` warning logic."""

from __future__ import annotations

from pathlib import Path

from jobapply.profile_validation import (
    validate_profile_path,
    validate_profile_text,
)

_FULL_PROFILE = """# Base profile

## Header
- **Name:** Jane Doe
- **Email:** jane@example.com
- **Phone:** +1 555 1234
- **Location:** Remote
- **Links:**
  - LinkedIn: linkedin.com/in/jane

## Summary
Experienced engineer.

## Skills (grouped)
- **Languages:** Python

## Experience

### Acme | Engineer | 2024 - Present
- Built things

## Projects
- **Mini:** built it

## Education

### MIT | B.S. CS | 2018 - 2022
- **GPA:** 3.85/4.0
- **Course Work:** OS, ML, NLP
"""


def test_full_profile_has_no_issues() -> None:
    assert validate_profile_text(_FULL_PROFILE) == []


def test_missing_name_and_email_are_required() -> None:
    text = _FULL_PROFILE.replace("Jane Doe", "").replace("jane@example.com", "")
    issues = validate_profile_text(text)
    fields = {i.field: i.severity for i in issues}
    assert fields["Header.Name"] == "required"
    assert fields["Header.Email"] == "required"


def test_empty_experience_section_is_required() -> None:
    text = (
        "# Profile\n## Header\n- **Name:** Jane\n- **Email:** j@x.io\n\n"
        "## Experience\n\n## Education\n\n### MIT | B.S. | 2018 - 2022\n- **GPA:** 4.0/4.0\n"
    )
    issues = validate_profile_text(text)
    required = [i for i in issues if i.is_required]
    assert any(i.field == "Experience" for i in required)


def test_empty_education_section_is_required() -> None:
    text = (
        "# Profile\n## Header\n- **Name:** Jane\n- **Email:** j@x.io\n\n"
        "## Experience\n### Acme | Engineer | 2024 - Present\n- Built\n\n"
        "## Education\n"
    )
    issues = validate_profile_text(text)
    required = [i for i in issues if i.is_required]
    assert any(i.field == "Education" for i in required)


def test_template_placeholders_count_as_empty() -> None:
    text = (
        "# Profile\n## Header\n- **Name:** Jane\n- **Email:** j@x.io\n\n"
        "## Experience\n### Company | Role | Start - End\n- bullet\n\n"
        "## Education\n### School | Degree | Start - End\n- **GPA:** 0.0/0.0\n"
    )
    issues = validate_profile_text(text)
    required_fields = {i.field for i in issues if i.is_required}
    # Pure placeholder Experience block should be flagged.
    assert "Experience" in required_fields


def test_missing_phone_is_recommended_not_required() -> None:
    text = _FULL_PROFILE.replace("- **Phone:** +1 555 1234", "- **Phone:**")
    issues = validate_profile_text(text)
    by_field = {i.field: i.severity for i in issues}
    assert by_field.get("Header.Phone") == "recommended"
    assert all(i.field != "Header.Name" for i in issues)


def test_education_without_gpa_or_coursework_is_recommended() -> None:
    text = (
        "# Profile\n## Header\n- **Name:** Jane\n- **Email:** j@x.io\n"
        "- **Phone:** +1\n- **Location:** Remote\n- **Links:** linkedin.com/in/jane\n\n"
        "## Skills (grouped)\n- **Languages:** Python\n\n"
        "## Experience\n### Acme | Engineer | 2024 - Present\n- Built\n\n"
        "## Projects\n- **Mini:** desc\n\n"
        "## Education\n### MIT | B.S. | 2018 - 2022\n- Studied things\n"
    )
    issues = validate_profile_text(text)
    fields = {i.field for i in issues}
    assert "Education.GPA" in fields
    assert "Education.Course Work" in fields
    assert all(i.severity == "recommended" for i in issues if i.field.startswith("Education."))


def test_validate_profile_path_returns_required_issue_when_missing(tmp_path: Path) -> None:
    issues = validate_profile_path(tmp_path / "nope.md")
    assert len(issues) == 1
    assert issues[0].is_required
    assert issues[0].field == "profile"


def test_validate_profile_path_reads_file(tmp_path: Path) -> None:
    p = tmp_path / "profile.md"
    p.write_text(_FULL_PROFILE, encoding="utf-8")
    assert validate_profile_path(p) == []


def test_header_without_explicit_section_is_accepted() -> None:
    """LLM rewrites sometimes drop ``## Header`` and write the contact lines
    bare under the H1, with no leading ``-``. We must still recognise them
    so users don't get false-positive 'missing Name/Email' warnings.
    """
    text = (
        "# Base profile\n\n"
        "**Name:** Arun Addagatla  \n"
        "**Email:** arun@example.com  \n"
        "**Phone:** +91 8485019026  \n"
        "**Location:** Mumbai  \n"
        "**Links:** [LinkedIn](https://linkedin.com/in/arun) "
        "[Portfolio](https://arun.dev)\n\n"
        "## Skills\n- **Languages:** Python\n\n"
        "## Experience\n### Acme | Engineer | 2024 - Present\n- Built\n\n"
        "## Education\n### MIT | B.S. CS | 2018 - 2022\n- **GPA:** 4.0/4.0\n"
        "- **Course Work:** OS, ML\n"
    )
    issues = validate_profile_text(text)
    fields = {i.field for i in issues}
    assert "Header.Name" not in fields
    assert "Header.Email" not in fields
    assert "Header.Phone" not in fields
    assert "Header.Location" not in fields
    assert "Header.Links" not in fields
