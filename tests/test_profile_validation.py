"""Tests for ``profile_validation`` warning logic.

The validator now operates on the structured :class:`Profile` model
backed by ``profile.json`` rather than parsing Markdown sections.
"""

from __future__ import annotations

import json
from pathlib import Path

from jobapply.profile import (
    Profile,
    ProfileEducation,
    ProfileExperience,
    ProfileLink,
    ProfileProject,
)
from jobapply.profile_validation import (
    validate_profile,
    validate_profile_path,
)


def _full_profile() -> Profile:
    return Profile(
        name="Jane Doe",
        email="jane@example.com",
        phone="+1 555 1234",
        location="Remote",
        linkedin="linkedin.com/in/jane",
        summary="Experienced engineer.",
        skills=["Python", "Kubernetes"],
        experience=[
            ProfileExperience(
                company="Acme",
                role="Engineer",
                start_date="2024",
                end_date="Present",
                bullets=["Built things"],
            ),
        ],
        projects=[
            ProfileProject(name="Mini", description="built it"),
        ],
        education=[
            ProfileEducation(
                school="MIT",
                degree="B.S. CS",
                start_date="2018",
                end_date="2022",
                gpa="3.85/4.0",
                coursework=["OS", "ML", "NLP"],
            ),
        ],
    )


def test_full_profile_has_no_issues() -> None:
    assert validate_profile(_full_profile()) == []


def test_missing_name_and_email_are_required() -> None:
    profile = _full_profile()
    profile.name = ""
    profile.email = ""
    issues = validate_profile(profile)
    fields = {i.field: i.severity for i in issues}
    assert fields["name"] == "required"
    assert fields["email"] == "required"


def test_empty_experience_section_is_required() -> None:
    profile = _full_profile()
    profile.experience = []
    required = [i for i in validate_profile(profile) if i.is_required]
    assert any(i.field == "experience" for i in required)


def test_experience_without_bullets_is_required() -> None:
    """A role that has only a company/role with no bullets gives the LLM
    nothing to tailor — flag it so the user fills in achievements."""
    profile = _full_profile()
    profile.experience = [
        ProfileExperience(company="Acme", role="Engineer", bullets=[]),
    ]
    required = [i for i in validate_profile(profile) if i.is_required]
    assert any(i.field == "experience" for i in required)


def test_empty_education_section_is_required() -> None:
    profile = _full_profile()
    profile.education = []
    required = [i for i in validate_profile(profile) if i.is_required]
    assert any(i.field == "education" for i in required)


def test_missing_phone_is_recommended_not_required() -> None:
    profile = _full_profile()
    profile.phone = ""
    issues = validate_profile(profile)
    by_field = {i.field: i.severity for i in issues}
    assert by_field.get("phone") == "recommended"
    assert all(i.field != "name" for i in issues)


def test_no_links_is_recommended() -> None:
    profile = _full_profile()
    profile.linkedin = ""
    profile.github = ""
    profile.portfolio = ""
    profile.medium = ""
    profile.twitter = ""
    profile.other_links = []
    issues = validate_profile(profile)
    fields = {i.field: i.severity for i in issues}
    assert fields.get("links") == "recommended"


def test_other_links_satisfy_link_recommendation() -> None:
    profile = _full_profile()
    profile.linkedin = ""
    profile.other_links = [ProfileLink(label="Dev.to", url="https://dev.to/jane")]
    fields = {i.field for i in validate_profile(profile)}
    assert "links" not in fields


def test_education_without_gpa_or_coursework_is_recommended() -> None:
    profile = _full_profile()
    profile.education = [
        ProfileEducation(
            school="MIT",
            degree="B.S.",
            start_date="2018",
            end_date="2022",
            gpa="",
            coursework=[],
        ),
    ]
    issues = validate_profile(profile)
    fields = {i.field for i in issues}
    assert "education[0].gpa" in fields
    assert "education[0].coursework" in fields
    assert all(i.severity == "recommended" for i in issues if i.field.startswith("education["))


def test_skills_and_projects_empty_is_recommended() -> None:
    profile = _full_profile()
    profile.skills = []
    profile.projects = []
    issues = validate_profile(profile)
    fields = {i.field: i.severity for i in issues}
    assert fields.get("skills") == "recommended"
    assert fields.get("projects") == "recommended"


def test_validate_profile_path_returns_required_issue_when_missing(
    tmp_path: Path,
) -> None:
    issues = validate_profile_path(tmp_path / "nope.json")
    assert len(issues) == 1
    assert issues[0].is_required
    assert issues[0].field == "profile"


def test_validate_profile_path_reads_file(tmp_path: Path) -> None:
    p = tmp_path / "profile.json"
    p.write_text(
        json.dumps(_full_profile().model_dump(mode="json")),
        encoding="utf-8",
    )
    assert validate_profile_path(p) == []


def test_validate_profile_path_handles_invalid_json(tmp_path: Path) -> None:
    """Garbage JSON should collapse to a single ``profile`` required issue
    rather than leaking a traceback through the CLI."""
    p = tmp_path / "profile.json"
    p.write_text("{not valid json", encoding="utf-8")
    issues = validate_profile_path(p)
    assert len(issues) == 1
    assert issues[0].is_required
    assert issues[0].field == "profile"
