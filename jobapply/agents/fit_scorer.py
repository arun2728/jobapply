"""Fit scoring agent — structured output."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from jobapply.models import FitScore, RawJob


def score_fit(
    llm: BaseChatModel,
    *,
    profile_text: str,
    job: RawJob,
    skills: list[str],
) -> FitScore:
    structured = llm.with_structured_output(FitScore)
    jd = (job.description or "")[:12000]
    sys = SystemMessage(
        content=(
            "You are an expert recruiter. Score how well the candidate profile "
            "matches the job (0-1). Be honest about gaps. Return structured JSON only."
        ),
    )
    user = HumanMessage(
        content=(
            f"Primary skills user cares about: {', '.join(skills) if skills else '(none)'}\n\n"
            f"JOB TITLE: {job.title}\nCOMPANY: {job.company}\nLOCATION: {job.location}\n\n"
            f"JOB DESCRIPTION:\n{jd}\n\n"
            f"CANDIDATE PROFILE:\n{profile_text[:16000]}"
        ),
    )
    result = structured.invoke([sys, user])
    assert isinstance(result, FitScore)
    return result
