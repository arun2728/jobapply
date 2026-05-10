"""Optional networking outreach — structured JSON."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from jobapply.agents._structured import invoke_structured
from jobapply.models import OutreachMessages, RawJob


def write_networking(
    llm: BaseChatModel,
    *,
    profile_text: str,
    job: RawJob,
) -> OutreachMessages:
    jd = (job.description or "")[:6000]
    sys = SystemMessage(
        content=(
            "Generate two short outreach drafts: referral_request "
            "(LinkedIn DM style, no Subject line) and cold_email "
            "(must start with 'Subject: ...'). Use placeholders like "
            "{{recipient_name}}, {{your_name}}, {{company}}, {{role}}, "
            "{{job_link}} where helpful."
        ),
    )
    user = HumanMessage(
        content=(
            f"JOB: {job.title}\nLINK: {job.job_url or job.apply_url or ''}\n\n"
            f"JD excerpt:\n{jd}\n\nCV/PROFILE excerpt:\n{profile_text[:6000]}"
        ),
    )
    return invoke_structured(llm, OutreachMessages, [sys, user])
