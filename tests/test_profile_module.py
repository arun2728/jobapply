"""Tests for the structured :class:`Profile` model and JSON I/O."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobapply.profile import (
    Profile,
    ProfileEducation,
    ProfileExperience,
    ProfileLink,
    ProfileLoadError,
    ProfileProject,
    load_profile,
    profile_skill_list,
    profile_to_text,
    save_profile,
)


def _sample_profile() -> Profile:
    return Profile(
        name="Jane Doe",
        email="jane@example.com",
        phone="+1 555 1234",
        location="Mumbai",
        linkedin="https://linkedin.com/in/jane",
        github="janedev",
        portfolio="https://jane.dev",
        other_links=[ProfileLink(label="Dev.to", url="https://dev.to/jane")],
        summary="Engineer with 5 yoe.",
        skills=["Python", "Kubernetes"],
        experience=[
            ProfileExperience(
                company="Acme",
                role="Engineer",
                location="Remote",
                start_date="2024",
                end_date="Present",
                bullets=["Shipped X", "Built Y"],
            ),
        ],
        projects=[
            ProfileProject(
                name="Toolkit",
                description="A handy CLI",
                url="https://github.com/jane/toolkit",
                tech=["Python", "Click"],
                bullets=["1k stars"],
            ),
        ],
        education=[
            ProfileEducation(
                school="MIT",
                degree="B.S. CS",
                start_date="2018",
                end_date="2022",
                gpa="3.85/4.0",
                coursework=["OS", "ML"],
                honors="Dean's list",
            ),
        ],
    )


# ---- JSON round-trip ---------------------------------------------------- #


def test_save_profile_writes_pretty_json(tmp_path: Path) -> None:
    target = tmp_path / "profile.json"
    save_profile(_sample_profile(), target)
    raw = target.read_text(encoding="utf-8")
    # Pretty-printed (indent=2) so the file is human-editable.
    assert "\n  " in raw
    data = json.loads(raw)
    assert data["name"] == "Jane Doe"
    assert data["other_links"][0]["label"] == "Dev.to"
    assert data["education"][0]["coursework"] == ["OS", "ML"]


def test_load_profile_round_trips(tmp_path: Path) -> None:
    target = tmp_path / "profile.json"
    save_profile(_sample_profile(), target)
    loaded = load_profile(target)
    assert loaded == _sample_profile()


def test_load_profile_missing_file_raises_friendly_error(tmp_path: Path) -> None:
    with pytest.raises(ProfileLoadError, match="not found"):
        load_profile(tmp_path / "missing.json")


def test_load_profile_invalid_json_raises_friendly_error(tmp_path: Path) -> None:
    target = tmp_path / "profile.json"
    target.write_text("{not valid", encoding="utf-8")
    with pytest.raises(ProfileLoadError, match="not valid JSON"):
        load_profile(target)


def test_load_profile_non_object_raises_friendly_error(tmp_path: Path) -> None:
    target = tmp_path / "profile.json"
    target.write_text("[]", encoding="utf-8")
    with pytest.raises(ProfileLoadError, match="JSON object"):
        load_profile(target)


def test_load_profile_schema_mismatch_raises_friendly_error(tmp_path: Path) -> None:
    target = tmp_path / "profile.json"
    target.write_text(
        json.dumps({"skills": "not a list"}),
        encoding="utf-8",
    )
    with pytest.raises(ProfileLoadError, match="doesn't match"):
        load_profile(target)


# ---- profile_to_text ---------------------------------------------------- #


def test_profile_to_text_includes_canonical_section_headings() -> None:
    """Agent prompts and downstream regex helpers pattern-match these
    section headings, so they must always appear when the corresponding
    field has data."""
    text = profile_to_text(_sample_profile())
    assert "## Header" in text
    assert "## Summary" in text
    assert "## Skills" in text
    assert "## Experience" in text
    assert "## Projects" in text
    assert "## Education" in text


def test_profile_to_text_renders_header_fields() -> None:
    text = profile_to_text(_sample_profile())
    assert "**Name:** Jane Doe" in text
    assert "**Email:** jane@example.com" in text
    assert "**Phone:** +1 555 1234" in text
    assert "**Location:** Mumbai" in text
    # Named links come before other_links and use stable labels.
    assert "Portfolio: https://jane.dev" in text
    assert "GitHub: janedev" in text
    assert "LinkedIn: https://linkedin.com/in/jane" in text
    assert "Dev.to: https://dev.to/jane" in text


def test_profile_to_text_renders_each_skill_as_a_bullet() -> None:
    text = profile_to_text(_sample_profile())
    assert "- Python" in text
    assert "- Kubernetes" in text


def test_profile_to_text_renders_experience_bullets_and_dates() -> None:
    text = profile_to_text(_sample_profile())
    assert "Acme | Engineer | 2024 - Present" in text
    assert "- Shipped X" in text
    assert "- Built Y" in text


def test_profile_to_text_renders_education_gpa_and_coursework() -> None:
    text = profile_to_text(_sample_profile())
    assert "**GPA:** 3.85/4.0" in text
    assert "**Course Work:** OS, ML" in text


def test_profile_to_text_skips_empty_sections() -> None:
    """Profile with only required fields shouldn't render empty headings —
    those would confuse the LLM into thinking we have data we don't."""
    bare = Profile(name="A", email="a@b.com")
    text = profile_to_text(bare)
    assert "## Header" in text
    assert "## Skills" not in text
    assert "## Experience" not in text
    assert "## Projects" not in text
    assert "## Education" not in text
    assert "## Summary" not in text


def test_profile_to_text_uses_only_end_date_when_start_missing() -> None:
    """A role with only ``end_date`` should still render the date in the
    title rather than dropping it entirely or leaving a stray ' - '."""
    profile = Profile(
        name="A",
        email="a@b.com",
        experience=[
            ProfileExperience(
                company="Acme",
                role="Eng",
                start_date="",
                end_date="2024",
                bullets=["did it"],
            ),
        ],
    )
    text = profile_to_text(profile)
    assert "Acme | Eng | 2024" in text
    assert "Acme | Eng |  - 2024" not in text


# ---- profile_skill_list ------------------------------------------------- #


def test_profile_skill_list_dedupes_and_strips() -> None:
    profile = Profile(
        skills=["Python", "  Python ", "python", "", "Kubernetes"],
    )
    assert profile_skill_list(profile) == ["Python", "Kubernetes"]
