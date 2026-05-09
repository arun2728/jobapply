"""Email-drafter agent + EmailDraft.as_text() tests.

The agent itself is a thin wrapper around an LLM call, so the
interesting behaviour is the post-processing — making sure the
recipient address is preserved on the returned ``EmailDraft`` even when
the LLM forgets to echo it back, and that ``as_text()`` produces the
copy-paste-ready format the CLI advertises.
"""

from __future__ import annotations

from typing import Any

from jobapply.agents.email_drafter import draft_application_email
from jobapply.models import CoverLetter, EmailDraft, RawJob, TailoredResume


class _FakeStructured:
    """Minimal stand-in for ``llm.with_structured_output(EmailDraft)``."""

    def __init__(self, out: EmailDraft) -> None:
        self._out = out

    def invoke(self, _msgs: Any) -> EmailDraft:
        return self._out


class _FakeLLM:
    def __init__(self, out: EmailDraft) -> None:
        self._out = out

    def with_structured_output(self, _schema: type[Any]) -> _FakeStructured:
        return _FakeStructured(self._out)


def _job() -> RawJob:
    return RawJob(
        job_id="testjobid00000000000000000001",
        title="Backend Engineer",
        company="Acme",
        description="JD",
        site="local",
    )


def _resume() -> TailoredResume:
    return TailoredResume(
        document_title="Jane Doe",
        contact_line="jane@example.com",
        summary="Experienced backend engineer.",
        skills=["Python", "Postgres", "Kubernetes"],
        experience=[],
        projects=[],
    )


def _cover() -> CoverLetter:
    return CoverLetter(
        header="Jane Doe",
        opening="Hi team,",
        body="I'd love to join Acme.",
        closing="Best,\nJane",
    )


def test_email_draft_fills_in_missing_to_field() -> None:
    """LLM returned an EmailDraft with empty `to` — agent must echo the
    recipient back so the persisted artifact is self-contained."""
    llm = _FakeLLM(
        EmailDraft(
            to="",
            subject="Application: Backend Engineer at Acme",
            body="Hi team,\n\nApplication body.\n\nBest,\nJane",
        )
    )

    out = draft_application_email(
        llm,
        profile_text="profile",
        job=_job(),
        resume=_resume(),
        cover=_cover(),
        recipient_email="recruiter@acme.com",
        additional_info="Referred by Bob.",
        sender_name="Jane Doe",
    )

    assert out.to == "recruiter@acme.com"
    assert out.subject.startswith("Application")
    assert "Application body" in out.body


def test_email_draft_preserves_to_when_llm_returned_one() -> None:
    """If the LLM populated `to`, we don't overwrite it."""
    llm = _FakeLLM(
        EmailDraft(
            to="careers@acme.com",
            subject="Backend Engineer Application — Jane Doe",
            body="Hi,\n\nbody",
        )
    )

    out = draft_application_email(
        llm,
        profile_text="profile",
        job=_job(),
        resume=_resume(),
        cover=_cover(),
        recipient_email="recruiter@acme.com",
        additional_info="",
        sender_name="Jane Doe",
    )

    assert out.to == "careers@acme.com"


def test_email_draft_as_text_format() -> None:
    """``as_text()`` is what the CLI writes to ``email.txt`` — keep its
    shape stable so users can copy-paste into any mail client."""
    draft = EmailDraft(
        to="recruiter@acme.com",
        subject="Backend Engineer at Acme — Jane Doe",
        body="Hi team,\n\nMy body.\n\nBest,\nJane",
    )

    text = draft.as_text()
    lines = text.splitlines()
    assert lines[0] == "To: recruiter@acme.com"
    assert lines[1] == "Subject: Backend Engineer at Acme — Jane Doe"
    assert lines[2] == ""
    assert "My body." in text
    assert text.endswith("\n")


def test_email_draft_as_text_omits_to_when_blank() -> None:
    draft = EmailDraft(to="", subject="Hi", body="Body")
    lines = draft.as_text().splitlines()
    assert lines[0] == "Subject: Hi"
