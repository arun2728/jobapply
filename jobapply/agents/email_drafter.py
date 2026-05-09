"""Email-drafting agent for the ``jobapply tailor`` flow.

Given the tailored resume + cover letter the user is about to send, this
agent produces a short, ready-to-paste application email — subject line
plus body — addressed to a specific recruiter or hiring-manager email
address. Optional ``additional_info`` from the user (e.g. "I met you at
PyCon", "referred by Jane", "available to start in two weeks") is folded
into the prompt so the draft sounds personal rather than generic.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from jobapply.models import CoverLetter, EmailDraft, RawJob, TailoredResume


def draft_application_email(
    llm: BaseChatModel,
    *,
    profile_text: str,
    job: RawJob,
    resume: TailoredResume,
    cover: CoverLetter,
    recipient_email: str,
    additional_info: str = "",
    sender_name: str = "",
) -> EmailDraft:
    """Produce an :class:`EmailDraft` ready to copy into a mail client.

    The cover letter is summarized in the body — we deliberately keep the
    email shorter than the cover letter so recruiters skim it, then open
    the attached resume / cover letter for detail. ``additional_info``
    is optional: when blank we just rely on the JD + resume context.
    """
    structured = llm.with_structured_output(EmailDraft)
    name = (sender_name or resume.document_title or "").strip() or "the candidate"
    additional = (additional_info or "").strip() or "(none provided)"
    sys = SystemMessage(
        content=(
            "You draft a concise, ready-to-paste job application email. "
            "Output strictly two fields:\n"
            "- `subject`: a single specific line, no quotes or trailing "
            "punctuation. Mention the role and (when natural) the "
            "candidate's name.\n"
            "- `body`: 3-5 short paragraphs of plain text. Greet the "
            "recipient (use 'Hi <Name>,' if a name is obvious from the "
            "recipient address; otherwise 'Hello,'). State the role "
            "you're applying for, two or three concrete reasons you're "
            "a strong fit (pulled from the resume / cover letter), and "
            "close with a clear call to action. Mention that the "
            "tailored resume and cover letter are attached. Sign off "
            "with the candidate's real name.\n\n"
            "RULES: stay truthful — never invent employers, metrics, "
            "dates, or projects beyond what the resume / profile "
            "supports. Avoid clichés ('passionate', 'rockstar', "
            "'synergy') and any phrasing that sounds AI-generated. "
            "Keep the body under 180 words."
        ),
    )
    user = HumanMessage(
        content=(
            f"RECIPIENT EMAIL: {recipient_email}\n"
            f"CANDIDATE NAME: {name}\n"
            f"ROLE: {job.title or '(unknown)'} at "
            f"{job.company or '(unknown)'}\n"
            f"JOB URL: {job.job_url or job.apply_url or '(none)'}\n\n"
            f"USER-PROVIDED CONTEXT (weave in naturally if helpful):\n"
            f"{additional}\n\n"
            f"COVER LETTER (source of voice + facts):\n"
            f"opening: {cover.opening}\n"
            f"body: {cover.body}\n"
            f"closing: {cover.closing}\n\n"
            f"TAILORED RESUME SUMMARY: {resume.summary}\n"
            f"TOP SKILLS: {', '.join(resume.skills[:20])}\n\n"
            f"PROFILE EXCERPT (for additional grounding):\n"
            f"{(profile_text or '')[:4000]}"
        ),
    )
    result = structured.invoke([sys, user])
    assert isinstance(result, EmailDraft)

    if not result.to.strip() and recipient_email.strip():
        result.to = recipient_email.strip()
    return result
