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
            "degrees, or metrics. Output structured sections only. "
            "Fill document_title with the candidate's real name and contact_line with a single "
            "line of contact info copied from the profile header (email, phone, links)."
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
