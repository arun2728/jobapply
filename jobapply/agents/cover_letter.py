"""Cover letter agent — structured CoverLetter sections."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from jobapply.models import CoverLetter, RawJob, TailoredResume


def write_cover_letter(
    llm: BaseChatModel,
    *,
    profile_text: str,
    job: RawJob,
    resume: TailoredResume,
) -> CoverLetter:
    structured = llm.with_structured_output(CoverLetter)
    jd = (job.description or "")[:10000]
    sys = SystemMessage(
        content=(
            "You write a concise, specific cover letter. Warm but professional. "
            "Use the candidate's real details from the profile header where possible. "
            "No clichés. Output structured parts: header, opening, body, closing."
        ),
    )
    user = HumanMessage(
        content=(
            f"JOB: {job.title} at {job.company}\nURL: {job.job_url or job.apply_url or ''}\n\n"
            f"JD:\n{jd}\n\n"
            f"PROFILE:\n{profile_text[:8000]}\n\n"
            f"TAILORED RESUME SUMMARY:\n{resume.summary}\n"
            f"TOP SKILLS: {', '.join(resume.skills[:25])}"
        ),
    )
    result = structured.invoke([sys, user])
    assert isinstance(result, CoverLetter)
    return result
