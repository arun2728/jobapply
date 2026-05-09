"""Resume tailoring agent — structured TailoredResume."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from jobapply.models import (
    ExperienceRole,
    ProjectItem,
    RawJob,
    TailoredResume,
)
from jobapply.profile import Profile
from jobapply.profile_validation import merge_skills_preserving_order


def _format_profile_dates(start: str, end: str) -> str:
    """Mirror the on-resume date format (e.g. ``"Mar 2025 – Present"``).

    Used by the experience/project fallbacks so a profile-sourced row
    matches what the LLM would have produced when it succeeds.
    """
    s = (start or "").strip()
    e = (end or "").strip()
    if s and e:
        return f"{s} – {e}"
    return s or e


def _experience_from_profile(profile: Profile) -> list[ExperienceRole]:
    """Convert ``profile.experience`` into resume :class:`ExperienceRole` objects.

    Used as the safety net when the LLM returns an empty experience
    list (common with smaller / free models that ignore sections not
    explicitly named in the system prompt).
    """
    out: list[ExperienceRole] = []
    for role in profile.experience:
        if not (role.company or role.role or role.bullets):
            continue
        out.append(
            ExperienceRole(
                company=role.company,
                role=role.role,
                dates=_format_profile_dates(role.start_date, role.end_date),
                bullets=[b for b in role.bullets if b and b.strip()],
            )
        )
    return out


def _projects_from_profile(profile: Profile) -> list[ProjectItem]:
    """Same fallback shape as :func:`_experience_from_profile`, for projects."""
    out: list[ProjectItem] = []
    for project in profile.projects:
        if not (project.name or project.bullets):
            continue
        bullets = [b for b in project.bullets if b and b.strip()]
        if project.description and project.description not in bullets:
            bullets.insert(0, project.description.strip())
        out.append(ProjectItem(name=project.name or "Project", bullets=bullets))
    return out


def tailor_resume(
    llm: BaseChatModel,
    *,
    profile_text: str,
    job: RawJob,
    skills: list[str],
    profile_skills: list[str] | None = None,
    profile: Profile | None = None,
) -> TailoredResume:
    """Build a :class:`TailoredResume` for ``job`` from ``profile_text``.

    ``profile_skills`` is the canonical, deduplicated list of every skill on
    the candidate's :class:`Profile`. Pass it from the caller (the graph
    node loads it from ``profile.json``); when ``None`` we skip the
    "guarantee every profile skill survives" merge step entirely.

    ``profile`` is the structured :class:`Profile` object. It's used as a
    safety net: if the LLM returns an empty ``experience`` or ``projects``
    list (we've seen this with smaller/free models that ignore sections
    not explicitly named in the prompt), we fill those sections in from
    the profile verbatim. ``None`` disables the safety net.
    """
    structured = llm.with_structured_output(TailoredResume)
    jd = (job.description or "")[:12000]
    canonical_skills: list[str] = profile_skills or []
    sys = SystemMessage(
        content=(
            "You rewrite the candidate's resume content for THIS job. "
            "Facts must stay truthful—rephrase and emphasize relevance; do not invent employers, "
            "degrees, schools, GPAs, or metrics. Output structured sections only.\n\n"
            "HEADER: Fill document_title with the candidate's real name. Populate the structured "
            "`contact` object from the profile's Header section: email, phone, location (plain "
            "text), and links. Classify each link by host into github / linkedin / medium / "
            "twitter / portfolio (anything that isn't one of the named services goes into "
            "portfolio). Copy URLs verbatim; do not shorten them. Leave a field empty if absent. "
            "Also set contact_line to the same info as a single human-readable plain-text line "
            "(used as a fallback when the renderer can't draw icons).\n\n"
            "SUMMARY: Still set `summary` (the cover-letter agent reads it for context). It is "
            "NOT rendered in the resume itself.\n\n"
            "SKILLS: The `skills` field MUST contain EVERY skill listed in the candidate's "
            "profile `## Skills` section, even ones that aren't directly relevant to this "
            "specific job. Do NOT drop, omit, summarize, filter, or merge skills based on "
            "perceived job-relevance. Preserve the candidate's original wording (including "
            "parenthesized aliases like 'Model Context Protocol (MCP)'). You SHOULD reorder "
            "the list so skills most relevant to the job description appear first; the rest "
            "follow in the candidate's original order. You MAY add a few skills clearly "
            "evidenced by the experience/projects bullets if they're missing — but never "
            "drop any.\n\n"
            "EXPERIENCE: The `experience` field MUST include EVERY role from the candidate's "
            "profile `## Experience` section — do not drop, merge, or omit any role under any "
            "circumstance. For each role, copy `company`, `role`, and the date range exactly "
            "as written; populate `bullets` from the profile's bullets, optionally rephrasing "
            "to emphasize keywords from the job description (without inventing facts, metrics, "
            "or technologies that aren't in the source bullet). Keep ALL bullets — never "
            "truncate the list of bullets to 'save space' or remove ones you think are less "
            "relevant. Order roles newest-first, exactly as the profile lists them.\n\n"
            "PROJECTS: The `projects` field MUST include EVERY project from the candidate's "
            "profile `## Projects` section — same rules as EXPERIENCE: copy the name verbatim, "
            "preserve all bullets (rephrasing for relevance is fine, dropping is not). If the "
            "profile has no projects, return an empty list.\n\n"
            "EDUCATION: For each entry populate school, degree, dates, and split GPA + "
            "coursework into the dedicated fields. `gpa` is the bare value with its scale, e.g. "
            "'9.6/10' or '3.85/4.0' — DO NOT prefix it with 'GPA:' (the renderer adds that). "
            "`coursework` is a comma-separated list of relevant courses with NO leading "
            "'Course Work:' prefix (e.g. 'OS, ML, NLP, DBMS, Networking'). Use `details` only "
            "for honors/thesis text that doesn't fit GPA or coursework. If the profile lacks "
            "GPA or coursework, leave those fields empty rather than fabricating values."
        ),
    )
    profile_skill_line = (
        ", ".join(canonical_skills) if canonical_skills else "(profile has no skills)"
    )
    user = HumanMessage(
        content=(
            f"Target skills to align with: {', '.join(skills) if skills else '(none)'}\n\n"
            f"PROFILE SKILLS (ALL of these must appear in the output `skills` field, "
            f"reordered so the most job-relevant come first): {profile_skill_line}\n\n"
            f"ROLE: {job.title} at {job.company}\n\nJOB DESCRIPTION:\n{jd}\n\n"
            f"BASE PROFILE (source of truth):\n{profile_text[:20000]}"
        ),
    )
    result = structured.invoke([sys, user])
    assert isinstance(result, TailoredResume)

    # Belt-and-suspenders: even with explicit prompting, models occasionally
    # drop "irrelevant" skills. Re-merge against the canonical list so the
    # rendered resume is guaranteed to contain every profile skill, in the
    # order the LLM ranked plus any missing ones appended in profile order.
    if canonical_skills:
        result.skills = merge_skills_preserving_order(result.skills, canonical_skills)

    # Same defense for experience / projects: smaller (and several
    # free-tier) models routinely return empty lists for sections the
    # prompt didn't *originally* call out. Detect the empty-list case
    # and restore from the source profile so the user never gets a
    # tailored resume that's missing their work history.
    if profile is not None:
        if not result.experience and profile.experience:
            result.experience = _experience_from_profile(profile)
        if not result.projects and profile.projects:
            result.projects = _projects_from_profile(profile)

    return result
