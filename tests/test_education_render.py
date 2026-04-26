"""Education rendering: GPA + coursework slots and the dropped Summary."""

from __future__ import annotations

from jobapply.models import EducationItem, ExperienceRole, TailoredResume
from jobapply.nodes.render import (
    _education_latex,
    fill_resume_tex,
    render_resume_markdown,
)


def _resume_with(education: list[EducationItem], summary: str = "") -> TailoredResume:
    return TailoredResume(
        document_title="Jane Doe",
        contact_line="jane@example.com",
        summary=summary,
        skills=["Python"],
        experience=[
            ExperienceRole(
                company="Acme",
                role="Engineer",
                dates="2024 - Present",
                bullets=["Built things"],
            )
        ],
        projects=[],
        education=education,
    )


def test_education_latex_uses_gpa_in_right_cell() -> None:
    edu = EducationItem(
        school="MIT",
        degree="B.S. Computer Science",
        dates="2018 - 2022",
        gpa="3.85/4.0",
    )
    out = _education_latex([edu])
    assert r"\headingBf{MIT}{2018 - 2022}" in out
    # GPA renders bold and prefixed by the template, not by the LLM.
    assert r"\headingIt{B.S. Computer Science}{\textbf{GPA:} \textbf{3.85/4.0}}" in out


def test_education_latex_renders_coursework_on_own_line() -> None:
    edu = EducationItem(
        school="MIT",
        degree="B.S. CS",
        dates="2018 - 2022",
        gpa="3.85/4.0",
        coursework="OS, ML, NLP, DBMS",
    )
    out = _education_latex([edu])
    assert r"\headingIt{Course Work: OS, ML, NLP, DBMS}{}" in out


def test_education_latex_falls_back_to_details_when_no_gpa_or_coursework() -> None:
    edu = EducationItem(
        school="MIT",
        degree="B.S. CS",
        dates="2018 - 2022",
        details="Magna Cum Laude",
    )
    out = _education_latex([edu])
    assert r"\headingIt{B.S. CS}{Magna Cum Laude}" in out
    # Coursework line should not appear.
    assert "Course Work" not in out


def test_education_latex_keeps_details_below_when_gpa_present() -> None:
    edu = EducationItem(
        school="MIT",
        degree="B.S. CS",
        dates="2018 - 2022",
        gpa="3.85/4.0",
        details="Magna Cum Laude",
    )
    out = _education_latex([edu])
    # GPA in right cell of the degree line.
    assert r"\textbf{GPA:} \textbf{3.85/4.0}" in out
    # Details surface on their own line so they don't get lost.
    assert r"\headingIt{Magna Cum Laude}{}" in out


def test_education_empty_list_returns_empty_string() -> None:
    assert _education_latex([]) == ""


def test_resume_tex_omits_summary_section() -> None:
    resume = _resume_with(education=[], summary="This summary should not appear.")
    out = fill_resume_tex(resume)
    assert "Summary" not in out
    assert "This summary should not appear." not in out


def test_resume_tex_keeps_skills_experience_when_summary_dropped() -> None:
    resume = _resume_with(education=[], summary="Should be invisible.")
    out = fill_resume_tex(resume)
    assert r"\section{Skills}" in out
    assert r"\section{Experience}" in out


def test_resume_markdown_omits_summary_heading() -> None:
    resume = _resume_with(
        education=[
            EducationItem(
                school="MIT",
                degree="B.S. CS",
                dates="2018 - 2022",
                gpa="3.85/4.0",
                coursework="OS, ML",
            )
        ],
        summary="Hidden summary.",
    )
    out = render_resume_markdown(resume)
    assert "## Summary" not in out
    assert "Hidden summary." not in out
    assert "GPA: 3.85/4.0" in out
    assert "Course Work:" in out and "OS, ML" in out


def test_resume_markdown_falls_back_to_details_without_gpa() -> None:
    resume = _resume_with(
        education=[
            EducationItem(
                school="MIT",
                degree="B.S. CS",
                details="Magna Cum Laude",
            )
        ],
    )
    out = render_resume_markdown(resume)
    assert "Magna Cum Laude" in out
    assert "GPA:" not in out
