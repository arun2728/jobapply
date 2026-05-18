"""Cover letter agent — structured CoverLetter sections."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from jobapply.agents._structured import invoke_structured
from jobapply.models import CoverLetter, RawJob, TailoredResume


def write_cover_letter(
    llm: BaseChatModel,
    *,
    profile_text: str,
    job: RawJob,
    resume: TailoredResume,
) -> CoverLetter:
    jd = (job.description or "")[:10000]
    sys = SystemMessage(
        content=(
            "You write a concise, specific cover letter. Warm but "
            "professional. Use the candidate's real details from the profile "
            "header where possible. No clichés.\n\n"
            "Output a SINGLE JSON object (never a list) with exactly four "
            "string fields: `header`, `opening`, `body`, `closing`. Each "
            "field MUST be plain text. Do NOT use nested objects, arrays, "
            "or sub-keys like `from`/`to`/`date` — write those details as "
            "regular lines inside the `header` string instead.\n\n"
            "- `header`: candidate's name and contact info, recipient/company, "
            "and date — newline-separated plain text.\n"
            "- `opening`: salutation + first paragraph.\n"
            "- `body`: 1–3 paragraphs tailored to the role.\n"
            "- `closing`: sign-off paragraph and signature lines."
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
    return invoke_structured(llm, CoverLetter, [sys, user])
