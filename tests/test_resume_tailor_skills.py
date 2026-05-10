"""Resume-tailor agent must preserve every profile skill.

The post-call skills merge guarantees that even when the LLM filters
its output down to "JD-relevant" skills only, the rendered resume
still contains every entry from the profile's `## Skills` section
in a sensible order.

Two separate code paths share the same merge contract:

* The deterministic-with-profile path (production) — the LLM is
  asked for ``_TailoredBullets``, and we merge ``bullets.skills``
  with ``profile.skills`` (or with the explicit ``profile_skills``
  override when callers want a custom canonical list).
* The legacy LLM-produces-everything path — kept for callers that
  don't pass a structured ``profile``; same merge runs after the
  LLM returns a full ``TailoredResume``.
"""

from __future__ import annotations

from typing import Any

from jobapply.agents.resume_tailor import _TailoredBullets, tailor_resume
from jobapply.models import RawJob, TailoredResume
from jobapply.profile import Profile, ProfileExperience

PROFILE_TEXT = (
    "# Profile\n"
    "## Header\n"
    "- **Name:** Test User\n"
    "- **Email:** test@example.com\n\n"
    "## Skills\n"
    "- TypeScript\n"
    "- Python\n"
    "- Model Context Protocol (MCP)\n"
    "- AWS\n"
    "- Kubernetes\n\n"
    "## Experience\n"
    "### Acme | Engineer | 2024 - Present\n"
    "- shipped things\n"
)

PROFILE_SKILLS = [
    "TypeScript",
    "Python",
    "Model Context Protocol (MCP)",
    "AWS",
    "Kubernetes",
]


def _structured_profile() -> Profile:
    return Profile(
        name="Test User",
        email="test@example.com",
        skills=list(PROFILE_SKILLS),
        experience=[
            ProfileExperience(
                company="Acme",
                role="Engineer",
                start_date="2024",
                end_date="Present",
                bullets=["shipped things"],
            ),
        ],
    )


class _FakeStructured:
    def __init__(self, out: Any) -> None:
        self._out = out

    def invoke(self, _msgs: Any) -> Any:
        return self._out


class _BulletsLLM:
    """Deterministic-path LLM stub — returns ``_TailoredBullets``."""

    def __init__(self, partial_skills: list[str]) -> None:
        self._payload = _TailoredBullets(
            summary="Engineer.",
            skills=list(partial_skills),
            experience_bullets=[["shipped things"]],
            project_bullets=[],
        )

    def with_structured_output(self, schema: type[Any]) -> _FakeStructured:
        assert schema is _TailoredBullets
        return _FakeStructured(self._payload)


class _LegacyFullResumeLLM:
    """Legacy-path LLM stub — returns a complete ``TailoredResume``."""

    def __init__(self, partial_skills: list[str]) -> None:
        self._resume = TailoredResume(
            document_title="Test User",
            contact_line="test@example.com",
            summary="Engineer.",
            skills=list(partial_skills),
            experience=[],
            projects=[],
        )

    def with_structured_output(self, schema: type[Any]) -> _FakeStructured:
        assert schema is TailoredResume
        return _FakeStructured(self._resume)


def _job() -> RawJob:
    return RawJob(
        job_id="testjobid00000000000000000001",
        title="Backend Engineer",
        company="Acme",
        description="We need Python and Kubernetes.",
    )


# Deterministic path (profile passed) ------------------------------------- #


def test_tailor_resume_appends_missing_profile_skills() -> None:
    """LLM dropped TypeScript / MCP / AWS as 'not relevant' — they must
    come back, in the order they appear in the profile, after the LLM's
    relevance-ordered list.
    """
    out = tailor_resume(
        _BulletsLLM(partial_skills=["Python", "Kubernetes"]),
        profile_text=PROFILE_TEXT,
        job=_job(),
        skills=["Python"],
        profile_skills=PROFILE_SKILLS,
        profile=_structured_profile(),
    )

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
    out = tailor_resume(
        _BulletsLLM(partial_skills=full),
        profile_text=PROFILE_TEXT,
        job=_job(),
        skills=[],
        profile_skills=PROFILE_SKILLS,
        profile=_structured_profile(),
    )

    assert out.skills == full


def test_tailor_resume_dedupes_case_insensitively() -> None:
    """If the LLM returns 'python' (lowercase) and the profile has 'Python',
    only one entry should survive — using the casing the LLM picked.
    """
    out = tailor_resume(
        _BulletsLLM(partial_skills=["python", "kubernetes"]),
        profile_text=PROFILE_TEXT,
        job=_job(),
        skills=[],
        profile_skills=PROFILE_SKILLS,
        profile=_structured_profile(),
    )

    lowered = [s.lower() for s in out.skills]
    assert lowered.count("python") == 1
    assert lowered.count("kubernetes") == 1
    assert "TypeScript" in out.skills
    assert "Model Context Protocol (MCP)" in out.skills
    assert "AWS" in out.skills


def test_tailor_resume_uses_profile_skills_when_canonical_list_omitted() -> None:
    """When ``profile_skills`` isn't provided but a structured profile
    IS, the merge falls back to ``profile.skills`` so the canonical
    list is still applied.
    """
    out = tailor_resume(
        _BulletsLLM(partial_skills=["Python"]),
        profile_text=PROFILE_TEXT,
        job=_job(),
        skills=[],
        profile=_structured_profile(),
    )

    # Every profile skill survives.
    for s in PROFILE_SKILLS:
        assert s in out.skills


# Legacy path (profile=None) ---------------------------------------------- #


def test_legacy_path_no_op_when_profile_skills_omitted() -> None:
    """When the caller doesn't pass ``profile`` AND doesn't pass
    ``profile_skills`` (the oldest legacy signature), the LLM output
    is returned unchanged — there's nothing to merge."""
    out = tailor_resume(
        _LegacyFullResumeLLM(partial_skills=["Python"]),
        profile_text="(no skills section)",
        job=_job(),
        skills=[],
    )

    assert out.skills == ["Python"]


def test_legacy_path_no_op_when_profile_skills_empty_list() -> None:
    out = tailor_resume(
        _LegacyFullResumeLLM(partial_skills=["Python"]),
        profile_text="(no skills section)",
        job=_job(),
        skills=[],
        profile_skills=[],
    )

    assert out.skills == ["Python"]


def test_legacy_path_merges_when_profile_skills_provided() -> None:
    """Without a structured profile but with an explicit
    ``profile_skills`` list, the legacy LLM-produces-everything path
    still merges so callers get the same skill-preservation
    guarantee as the deterministic path."""
    out = tailor_resume(
        _LegacyFullResumeLLM(partial_skills=["Python", "Kubernetes"]),
        profile_text=PROFILE_TEXT,
        job=_job(),
        skills=[],
        profile_skills=PROFILE_SKILLS,
    )

    assert out.skills == [
        "Python",
        "Kubernetes",
        "TypeScript",
        "Model Context Protocol (MCP)",
        "AWS",
    ]
