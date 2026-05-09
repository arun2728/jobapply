"""Extract structured metadata from a free-form job description.

The ``jobapply tailor`` flow accepts a path to a JD file (txt / md / pdf /
docx) and needs at minimum a ``title`` + ``company`` to drive the
downstream agents and to slugify the output directory. Most JDs encode
that information in their first few lines, but the layout is wildly
inconsistent — pages, headers, "About us" sections, etc. — so we hand
the text to the configured LLM and ask for a structured payload.

Callers can short-circuit this entire step by passing explicit
``--title`` / ``--company`` flags; in that case we never invoke the LLM
for parsing.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from jobapply.models import JobDescriptionMeta


def parse_job_description(llm: BaseChatModel, *, text: str) -> JobDescriptionMeta:
    """Ask the LLM to pull title / company / location out of ``text``.

    Returns an empty :class:`JobDescriptionMeta` when the LLM can't find
    the value; the orchestrator decides whether to prompt the user.
    """
    structured = llm.with_structured_output(JobDescriptionMeta)
    sys = SystemMessage(
        content=(
            "You read a job description and extract three plain-text "
            "fields: title (the role being hired for), company (the "
            "hiring organization), and location (city / country / "
            "remote). Copy values verbatim from the text — do not "
            "rephrase, abbreviate, or guess. If a field is genuinely "
            "absent, leave it empty rather than inventing one."
        ),
    )
    user = HumanMessage(content=f"JOB DESCRIPTION:\n{(text or '')[:12000]}")
    result = structured.invoke([sys, user])
    assert isinstance(result, JobDescriptionMeta)
    return result
