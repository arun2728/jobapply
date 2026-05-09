"""End-to-end tailor_one tests with a fully mocked LLM.

These tests exercise the orchestration layer in
``jobapply.tailor_one`` without hitting the network: the fake LLM
returns canned structured outputs for every schema the pipeline
requests, so we can assert on the artifact tree on disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from jobapply.models import (
    CoverLetter,
    EmailDraft,
    JobDescriptionMeta,
    TailoredResume,
)
from jobapply.tailor_one import (
    JobDescriptionReadError,
    TailorEmailRequest,
    read_job_description_text,
    tailor_for_job_description,
)


PROFILE_TEXT = (
    "# Profile\n"
    "## Header\n"
    "- **Name:** Jane Doe\n"
    "- **Email:** jane@example.com\n\n"
    "## Skills\n- Python\n- Kubernetes\n"
)


class _FakeStructured:
    def __init__(self, out: Any) -> None:
        self._out = out

    def invoke(self, _msgs: Any) -> Any:
        return self._out


class FakeChatModel:
    """Returns a sensible canned object for every schema the pipeline
    asks for. Matches the schemas used by the tailor flow only — fit
    scoring isn't part of single-JD tailoring."""

    def with_structured_output(self, schema: type[Any]) -> _FakeStructured:
        if schema.__name__ == "JobDescriptionMeta":
            return _FakeStructured(
                JobDescriptionMeta(
                    title="Backend Engineer",
                    company="Acme",
                    location="Remote",
                )
            )
        if schema.__name__ == "TailoredResume":
            return _FakeStructured(
                TailoredResume(
                    document_title="Jane Doe",
                    contact_line="jane@example.com",
                    summary="Experienced backend engineer.",
                    skills=["Python", "Kubernetes"],
                    experience=[],
                    projects=[],
                )
            )
        if schema.__name__ == "CoverLetter":
            return _FakeStructured(
                CoverLetter(
                    header="Jane Doe",
                    opening="Hi team,",
                    body="I would love to join.",
                    closing="Best,\nJane",
                )
            )
        if schema.__name__ == "EmailDraft":
            return _FakeStructured(
                EmailDraft(
                    to="",
                    subject="Backend Engineer Application — Jane Doe",
                    body="Hi team,\n\nReady-to-paste body.\n\nBest,\nJane",
                )
            )
        raise AssertionError(f"unexpected schema {schema}")


@pytest.fixture()
def jd_path(tmp_path: Path) -> Path:
    p = tmp_path / "jd.txt"
    p.write_text(
        "We are hiring a Backend Engineer at Acme. Remote. "
        "Python, Postgres, Kubernetes required.\n",
        encoding="utf-8",
    )
    return p


def test_tailor_writes_resume_and_cover_letter(tmp_path: Path, jd_path: Path) -> None:
    output_root = tmp_path / "tailor-test"
    out = tailor_for_job_description(
        FakeChatModel(),
        jd_path=jd_path,
        profile_text=PROFILE_TEXT,
        profile_skills=["Python", "Kubernetes"],
        output_root=output_root,
        target_skills=["Python"],
        no_pdf=True,
    )

    assert out.job.title == "Backend Engineer"
    assert out.job.company == "Acme"
    assert out.job.location == "Remote"

    assert out.resume_md.is_file()
    assert out.resume_tex.is_file()
    assert out.cover_md.is_file()
    assert out.cover_tex.is_file()

    assert out.resume_pdf is None  # no_pdf=True
    assert out.cover_pdf is None
    assert out.email is None
    assert out.email_path is None

    assert "Jane Doe" in out.resume_md.read_text(encoding="utf-8")
    assert "I would love to join" in out.cover_md.read_text(encoding="utf-8")

    meta_file = out.job_dir / "tailor_meta.json"
    assert meta_file.is_file()
    assert "Backend Engineer" in meta_file.read_text(encoding="utf-8")


def test_tailor_with_email_writes_email_artifact(tmp_path: Path, jd_path: Path) -> None:
    output_root = tmp_path / "tailor-test"
    out = tailor_for_job_description(
        FakeChatModel(),
        jd_path=jd_path,
        profile_text=PROFILE_TEXT,
        profile_skills=["Python", "Kubernetes"],
        output_root=output_root,
        no_pdf=True,
        email=TailorEmailRequest(
            recipient="recruiter@acme.com",
            additional_info="Referred by Bob.",
        ),
    )

    assert out.email is not None
    assert out.email.to == "recruiter@acme.com"
    assert out.email_path is not None
    assert out.email_path.is_file()

    text = out.email_path.read_text(encoding="utf-8")
    assert text.startswith("To: recruiter@acme.com")
    assert "Subject: Backend Engineer Application" in text
    assert "Ready-to-paste body" in text


def test_tailor_skips_llm_meta_call_when_overrides_complete(
    tmp_path: Path, jd_path: Path
) -> None:
    """When --title/--company/--location are all supplied, the JD parser
    is skipped (saves a call) and the overrides are honoured verbatim."""
    output_root = tmp_path / "tailor-test"

    class _NoMetaLLM(FakeChatModel):
        def with_structured_output(self, schema: type[Any]) -> _FakeStructured:
            assert schema.__name__ != "JobDescriptionMeta", (
                "JD parser should be skipped when overrides are complete"
            )
            return super().with_structured_output(schema)

    out = tailor_for_job_description(
        _NoMetaLLM(),
        jd_path=jd_path,
        profile_text=PROFILE_TEXT,
        profile_skills=["Python", "Kubernetes"],
        output_root=output_root,
        title_override="Senior Platform Engineer",
        company_override="Globex",
        location_override="NYC",
        no_pdf=True,
    )

    assert out.job.title == "Senior Platform Engineer"
    assert out.job.company == "Globex"
    assert out.job.location == "NYC"


def test_read_job_description_rejects_unsupported_extension(tmp_path: Path) -> None:
    bad = tmp_path / "jd.html"
    bad.write_text("<p>jd</p>", encoding="utf-8")
    with pytest.raises(JobDescriptionReadError, match="Unsupported"):
        read_job_description_text(bad)


def test_read_job_description_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(JobDescriptionReadError, match="No such file"):
        read_job_description_text(tmp_path / "does_not_exist.txt")


def test_read_job_description_rejects_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "empty.txt"
    p.write_text("   \n   ", encoding="utf-8")
    with pytest.raises(JobDescriptionReadError, match="extract any text"):
        read_job_description_text(p)


def test_tailor_falls_back_to_synthetic_meta_when_overrides_missing(
    tmp_path: Path, jd_path: Path
) -> None:
    """Even when the LLM (somehow) returns blank metadata and the user
    didn't override, the pipeline still writes artifacts under a sane
    fallback slug rather than crashing."""

    class _BlankMetaLLM(FakeChatModel):
        def with_structured_output(self, schema: type[Any]) -> _FakeStructured:
            if schema.__name__ == "JobDescriptionMeta":
                return _FakeStructured(JobDescriptionMeta())
            return super().with_structured_output(schema)

    output_root = tmp_path / "tailor-test"
    out = tailor_for_job_description(
        _BlankMetaLLM(),
        jd_path=jd_path,
        profile_text=PROFILE_TEXT,
        profile_skills=["Python", "Kubernetes"],
        output_root=output_root,
        no_pdf=True,
    )

    assert out.job.title == "Tailored Application"
    assert out.job.company == "Unknown Company"
    assert out.resume_md.is_file()
