"""Regression: empty Experience / Projects shouldn't render headings.

Previously the Markdown template emitted ``## Experience`` and
``## Projects`` even when the corresponding lists were empty, which
left a confusing "header but no content" hole in the rendered
resume. The current template wraps each section in an ``{% if %}``
guard so empty lists produce no output at all.
"""

from __future__ import annotations

from jobapply.models import (
    ContactInfo,
    EducationItem,
    ExperienceRole,
    ProjectItem,
    TailoredResume,
)
from jobapply.nodes.render import render_resume_markdown


def _resume(**overrides) -> TailoredResume:
    base = dict(
        document_title="Jane Doe",
        contact=ContactInfo(email="jane@example.com"),
        skills=["Python", "SQL"],
        experience=[],
        projects=[],
        education=[
            EducationItem(school="State University", degree="BS", dates="2019-2023"),
        ],
    )
    base.update(overrides)
    return TailoredResume(**base)


def test_md_skips_empty_experience_section() -> None:
    md = render_resume_markdown(_resume())
    assert "## Skills" in md
    assert "## Experience" not in md
    assert "## Projects" not in md
    assert "## Education" in md


def test_md_skips_empty_projects_section_only() -> None:
    md = render_resume_markdown(
        _resume(
            experience=[
                ExperienceRole(
                    company="Acme",
                    role="Engineer",
                    dates="2024",
                    bullets=["Shipped things."],
                )
            ],
            projects=[],
        )
    )
    assert "## Experience" in md
    assert "Acme" in md
    assert "## Projects" not in md


def test_md_renders_all_sections_when_present() -> None:
    md = render_resume_markdown(
        _resume(
            experience=[
                ExperienceRole(
                    company="Acme",
                    role="Engineer",
                    dates="2024",
                    bullets=["Shipped things."],
                )
            ],
            projects=[
                ProjectItem(name="Cool Tool", bullets=["Uses Python."]),
            ],
        )
    )
    assert "## Skills" in md
    assert "## Experience" in md
    assert "## Projects" in md
    assert "## Education" in md
    assert "Cool Tool" in md
