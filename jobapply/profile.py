"""Structured candidate profile (``profile.json``).

``profile.json`` replaces the legacy ``profile.md`` as the single source of
truth for the candidate's resume content. Storing the data as JSON gives us
three things the markdown layout couldn't:

* a stable Pydantic schema we can drive directly from the LLM resume importer
  (``llm.with_structured_output(Profile)``),
* a deterministic textual rendering for the agent prompts (so they keep
  consuming a ``profile_text`` string),
* trivial round-tripping for users who want to hand-edit the file.

The file is parsed and emitted with :func:`load_profile` and
:func:`save_profile`. The agent-facing markdown rendering lives in
:func:`profile_to_text` and intentionally mirrors the section headings the
old ``profile.md`` used so any prompts/tests that pattern-match on
``## Skills``/``## Experience`` keep working.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from jobapply.utils import atomic_write_json


class ProfileLink(BaseModel):
    """An extra link that doesn't fit one of the named handle fields."""

    label: str = Field(..., description="Display label, e.g. 'Personal Site'.")
    url: str = Field(..., description="Full URL or bare username/handle.")


class ProfileExperience(BaseModel):
    """A single role on the candidate's resume."""

    company: str = ""
    role: str = ""
    location: str = ""
    start_date: str = Field("", description="Free-form start, e.g. 'Mar 2025'.")
    end_date: str = Field(
        "",
        description="Free-form end, e.g. 'Present' or 'Aug 2024'.",
    )
    bullets: list[str] = Field(default_factory=list)


class ProfileProject(BaseModel):
    """A side / open-source / portfolio project."""

    name: str = ""
    description: str = Field(
        "",
        description="One-line summary; appears alongside the project title.",
    )
    url: str = Field("", description="Repo or live demo URL.")
    bullets: list[str] = Field(default_factory=list)
    tech: list[str] = Field(
        default_factory=list,
        description="Tech stack used (kept separate so it can be highlighted).",
    )


class ProfileEducation(BaseModel):
    """A school entry on the candidate's resume."""

    school: str = ""
    degree: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    gpa: str = Field("", description="Bare value with scale, e.g. '9.6/10'.")
    coursework: list[str] = Field(
        default_factory=list,
        description="Comma-free list of relevant courses; renderer joins with ', '.",
    )
    honors: str = Field("", description="Awards, scholarships, thesis title, etc.")


class Profile(BaseModel):
    """Top-level candidate profile persisted to ``profile.json``.

    Every list field defaults to empty so partial profiles still validate;
    the dedicated :func:`jobapply.profile_validation.validate_profile` pass
    surfaces required-vs-recommended gaps for the CLI to display.
    """

    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""

    portfolio: str = ""
    linkedin: str = ""
    github: str = ""
    medium: str = ""
    twitter: str = ""
    other_links: list[ProfileLink] = Field(default_factory=list)

    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[ProfileExperience] = Field(default_factory=list)
    projects: list[ProfileProject] = Field(default_factory=list)
    education: list[ProfileEducation] = Field(default_factory=list)


class ProfileLoadError(RuntimeError):
    """Raised when ``profile.json`` is missing, unreadable, or invalid JSON."""


def load_profile(path: Path) -> Profile:
    """Read ``path`` as JSON and return a validated :class:`Profile`.

    Raises :class:`ProfileLoadError` for any file/parse/schema problem so
    the CLI can render a single human-friendly message instead of leaking
    a stack trace.
    """
    if not path.is_file():
        raise ProfileLoadError(
            f"profile.json not found at {path} — run `jobapply init` first.",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileLoadError(
            f"profile.json at {path} is not valid JSON: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno}).",
        ) from exc
    if not isinstance(data, dict):
        raise ProfileLoadError(
            f"profile.json at {path} must be a JSON object, got {type(data).__name__}.",
        )
    try:
        return Profile.model_validate(data)
    except ValidationError as exc:
        raise ProfileLoadError(
            f"profile.json at {path} doesn't match the expected schema:\n{exc}",
        ) from exc


def save_profile(profile: Profile, path: Path) -> None:
    """Atomically write ``profile`` to ``path`` as pretty-printed JSON."""
    atomic_write_json(path, profile.model_dump(mode="json"))


# ---- Markdown rendering for agent prompts -------------------------------- #


def _format_date_range(start: str, end: str) -> str:
    """Join start/end into a ``Start - End`` string, tolerant of empties."""
    s, e = (start or "").strip(), (end or "").strip()
    if s and e:
        return f"{s} - {e}"
    return s or e


def _named_links(profile: Profile) -> list[tuple[str, str]]:
    """Return ``(label, url)`` for every populated handle field, in display order."""
    pairs: list[tuple[str, str]] = []
    if profile.portfolio:
        pairs.append(("Portfolio", profile.portfolio))
    if profile.github:
        pairs.append(("GitHub", profile.github))
    if profile.linkedin:
        pairs.append(("LinkedIn", profile.linkedin))
    if profile.medium:
        pairs.append(("Medium", profile.medium))
    if profile.twitter:
        pairs.append(("Twitter", profile.twitter))
    for link in profile.other_links:
        if link.url.strip():
            pairs.append((link.label or "Link", link.url))
    return pairs


def _render_header(profile: Profile, lines: list[str]) -> None:
    """Append the ``## Header`` section to ``lines``."""
    lines.append("## Header")
    lines.append(f"- **Name:** {profile.name}")
    lines.append(f"- **Email:** {profile.email}")
    if profile.phone:
        lines.append(f"- **Phone:** {profile.phone}")
    if profile.location:
        lines.append(f"- **Location:** {profile.location}")
    links = _named_links(profile)
    if links:
        lines.append("- **Links:**")
        for label, url in links:
            lines.append(f"  - {label}: {url}")
    lines.append("")


def _render_skills(profile: Profile, lines: list[str]) -> None:
    """Append the ``## Skills`` section as bare bullets so all skills are
    obvious to the LLM. Categorization is intentionally dropped — the JSON
    schema is a flat list and the prompt-side merge logic only cares about
    the deduplicated list, not its categories."""
    if not profile.skills:
        return
    lines.append("## Skills")
    for skill in profile.skills:
        s = skill.strip()
        if s:
            lines.append(f"- {s}")
    lines.append("")


def _render_experience(profile: Profile, lines: list[str]) -> None:
    if not profile.experience:
        return
    lines.append("## Experience")
    for role in profile.experience:
        when = _format_date_range(role.start_date, role.end_date)
        title_bits = [role.company or "", role.role or ""]
        if when:
            title_bits.append(when)
        title = " | ".join(b for b in title_bits if b)
        if title:
            lines.append(f"### {title}")
        if role.location:
            lines.append(f"_{role.location}_")
        for bullet in role.bullets:
            b = bullet.strip()
            if b:
                lines.append(f"- {b}")
        lines.append("")


def _render_projects(profile: Profile, lines: list[str]) -> None:
    if not profile.projects:
        return
    lines.append("## Projects")
    for project in profile.projects:
        title = project.name or "Project"
        if project.url:
            title = f"{title} ({project.url})"
        lines.append(f"### {title}")
        if project.description:
            lines.append(project.description)
        if project.tech:
            lines.append(f"_Tech:_ {', '.join(t for t in project.tech if t.strip())}")
        for bullet in project.bullets:
            b = bullet.strip()
            if b:
                lines.append(f"- {b}")
        lines.append("")


def _render_education(profile: Profile, lines: list[str]) -> None:
    if not profile.education:
        return
    lines.append("## Education")
    for school in profile.education:
        when = _format_date_range(school.start_date, school.end_date)
        title_bits = [school.school or "", school.degree or ""]
        if when:
            title_bits.append(when)
        title = " | ".join(b for b in title_bits if b)
        if title:
            lines.append(f"### {title}")
        if school.gpa:
            lines.append(f"- **GPA:** {school.gpa}")
        if school.coursework:
            joined = ", ".join(c for c in school.coursework if c.strip())
            if joined:
                lines.append(f"- **Course Work:** {joined}")
        if school.honors:
            lines.append(f"- **Honors:** {school.honors}")
        lines.append("")


def profile_to_text(profile: Profile) -> str:
    """Render ``profile`` as Markdown for the agent prompts.

    The layout deliberately mirrors the legacy ``profile.md`` shape — with
    ``## Header``, ``## Summary``, ``## Skills``, ``## Experience``,
    ``## Projects``, and ``## Education`` headings — so existing agent
    prompts and any downstream regex helpers keep working unchanged. The
    output is plain Markdown only; secrets like API keys are never
    included since they don't live on the Profile model.
    """
    lines: list[str] = ["# Base profile (starter resume source)", ""]
    _render_header(profile, lines)
    if profile.summary:
        lines.append("## Summary")
        lines.append(profile.summary.strip())
        lines.append("")
    _render_skills(profile, lines)
    _render_experience(profile, lines)
    _render_projects(profile, lines)
    _render_education(profile, lines)
    return "\n".join(lines).rstrip() + "\n"


def profile_skill_list(profile: Profile) -> list[str]:
    """Return the deduplicated, non-blank list of profile skills.

    Case-insensitive dedupe preserves the user's original casing on the
    first occurrence. Used by the resume-tailor agent's safety net to
    guarantee every skill survives the LLM round-trip.
    """
    return _dedupe_preserving_order(profile.skills)


def _dedupe_preserving_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        cleaned = (raw or "").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out
