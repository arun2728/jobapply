"""Resume-tailor agent must preserve every profile skill.

This test exercises the post-processing safety net in
``jobapply.agents.resume_tailor.tailor_resume``: even when the LLM returns
a partial ``skills`` list (filtered down to "relevant" ones), the function
must merge the missing profile skills back in so the rendered resume
always reflects the full skill set.
"""

from __future__ import annotations

from typing import Any

from jobapply.agents.resume_tailor import tailor_resume
from jobapply.models import RawJob, TailoredResume

PROFILE_MD = (
    "# Header\n"
    "**Name:** Test User\n"
    "**Email:** test@example.com\n\n"
    "## Skills\n"
    "- **Languages:** TypeScript, Python\n"
    "- **Frameworks:** Model Context Protocol (MCP)\n"
    "- **Cloud / Infra:** AWS, Kubernetes\n\n"
    "## Experience\n"
    "### Acme | Engineer | 2024 - Present\n"
    "- shipped things\n"
)


class _FakeStructured:
    def __init__(self, out: TailoredResume) -> None:
        self._out = out

    def invoke(self, _msgs: Any) -> TailoredResume:
        return self._out


class _FakeLLM:
    """Returns a TailoredResume with only a partial skill set, simulating
    an LLM that drops "irrelevant" skills despite the prompt."""

    def __init__(self, partial_skills: list[str]) -> None:
        self._resume = TailoredResume(
            document_title="Test User",
            contact_line="test@example.com",
            summary="Engineer.",
            skills=list(partial_skills),
            experience=[],
            projects=[],
        )

    def with_structured_output(self, _schema: type[Any]) -> _FakeStructured:
        return _FakeStructured(self._resume)


def _job() -> RawJob:
    return RawJob(
        job_id="testjobid00000000000000000001",
        title="Backend Engineer",
        company="Acme",
        description="We need Python and Kubernetes.",
    )


def test_tailor_resume_appends_missing_profile_skills() -> None:
    """LLM dropped TypeScript / MCP / AWS as 'not relevant' — they must
    come back, in the order they appear in the profile, after the LLM's
    relevance-ordered list.
    """
    llm = _FakeLLM(partial_skills=["Python", "Kubernetes"])

    out = tailor_resume(llm, profile_text=PROFILE_MD, job=_job(), skills=["Python"])

    assert out.skills == [
        "Python",
        "Kubernetes",
        "TypeScript",
        "Model Context Protocol (MCP)",
        "AWS",
    ]


def test_tailor_resume_keeps_full_set_when_llm_already_returned_all() -> None:
    """No reordering or duplication when the LLM already returned the full
    set in its preferred order.
    """
    full = [
        "Kubernetes",
        "Python",
        "AWS",
        "TypeScript",
        "Model Context Protocol (MCP)",
    ]
    llm = _FakeLLM(partial_skills=full)

    out = tailor_resume(llm, profile_text=PROFILE_MD, job=_job(), skills=[])

    assert out.skills == full


def test_tailor_resume_dedupes_case_insensitively() -> None:
    """If the LLM returns 'python' (lowercase) and the profile has 'Python',
    only one entry should survive — using the casing the LLM picked.
    """
    llm = _FakeLLM(partial_skills=["python", "kubernetes"])

    out = tailor_resume(llm, profile_text=PROFILE_MD, job=_job(), skills=[])

    lowered = [s.lower() for s in out.skills]
    assert lowered.count("python") == 1
    assert lowered.count("kubernetes") == 1
    assert "TypeScript" in out.skills
    assert "Model Context Protocol (MCP)" in out.skills
    assert "AWS" in out.skills


def test_tailor_resume_no_op_when_profile_has_no_skills_section() -> None:
    """If profile lacks a Skills section, the LLM output is returned
    unchanged (nothing to merge)."""
    profile_no_skills = "# Header\n**Name:** Test\n\n## Experience\n- did things\n"
    llm = _FakeLLM(partial_skills=["Python"])

    out = tailor_resume(llm, profile_text=profile_no_skills, job=_job(), skills=[])

    assert out.skills == ["Python"]
