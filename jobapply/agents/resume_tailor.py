"""Resume tailoring agent — structured TailoredResume."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from jobapply.models import RawJob, TailoredResume


def tailor_resume(
    llm: BaseChatModel,
    *,
    profile_text: str,
    job: RawJob,
    skills: list[str],
) -> TailoredResume:
    structured = llm.with_structured_output(TailoredResume)
    jd = (job.description or "")[:12000]
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
            "EDUCATION: For each entry populate school, degree, dates, and split GPA + "
            "coursework into the dedicated fields. `gpa` is the bare value with its scale, e.g. "
            "'9.6/10' or '3.85/4.0' — DO NOT prefix it with 'GPA:' (the renderer adds that). "
            "`coursework` is a comma-separated list of relevant courses with NO leading "
            "'Course Work:' prefix (e.g. 'OS, ML, NLP, DBMS, Networking'). Use `details` only "
            "for honors/thesis text that doesn't fit GPA or coursework. If the profile lacks "
            "GPA or coursework, leave those fields empty rather than fabricating values."
        ),
    )
    user = HumanMessage(
        content=(
            f"Target skills to align with: {', '.join(skills) if skills else '(none)'}\n\n"
            f"ROLE: {job.title} at {job.company}\n\nJOB DESCRIPTION:\n{jd}\n\n"
            f"BASE PROFILE (source of truth):\n{profile_text[:20000]}"
        ),
    )
    result = structured.invoke([sys, user])
    assert isinstance(result, TailoredResume)
    return result
