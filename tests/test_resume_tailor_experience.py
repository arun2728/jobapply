"""Resume-tailor must preserve every profile experience + project.

Pins both ends of the experience-loss bug we hit in production:

* The system prompt must explicitly require EXPERIENCE / PROJECTS to
  be filled (smaller / free-tier models silently drop sections that
  aren't called out).
* When the LLM still returns an empty ``experience`` / ``projects``
  list, the post-call safety net must restore both sections from the
  source :class:`Profile` so the rendered resume always reflects the
  candidate's actual work history.
"""

from __future__ import annotations

import inspect
from typing import Any

from jobapply.agents import resume_tailor as rt_module
from jobapply.agents.resume_tailor import (
    _experience_from_profile,
    _projects_from_profile,
    tailor_resume,
)
from jobapply.models import RawJob, TailoredResume
from jobapply.profile import (
    Profile,
    ProfileEducation,
    ProfileExperience,
    ProfileProject,
)


_PROFILE_TEXT = (
    "# Profile\n"
    "## Header\n- **Name:** Sakshi B.\n- **Email:** s@example.com\n\n"
    "## Skills\n- ETL\n- SQL\n\n"
    "## Experience\n### Fintellix | Consultant I | Mar 2025 - Present\n"
    "- Led ADF implementation for RBI compliance\n"
    "## Education\n### Terna College | BE | 2018 - 2022\n"
)


def _profile_with_experience() -> Profile:
    return Profile(
        name="Sakshi B.",
        email="s@example.com",
        skills=["ETL", "SQL"],
        experience=[
            ProfileExperience(
                company="Fintellix",
                role="Consultant I",
                start_date="March 2025",
                end_date="Present",
                bullets=[
                    "Led ADF implementation for RBI compliance.",
                    "Architected ETL integrations using Informatica.",
                ],
            ),
            ProfileExperience(
                company="Fintellix",
                role="Associate Consultant",
                start_date="July 2022",
                end_date="March 2025",
                bullets=[
                    "Designed complex ETL workflows.",
                    "Built data mappings for regulatory reporting.",
                ],
            ),
        ],
        projects=[
            ProfileProject(
                name="CIMS Reporting",
                description="Daily RBI submissions.",
                bullets=["Reduced manual ops by 30%.", "BRFSD-compliant pipelines."],
            ),
        ],
        education=[
            ProfileEducation(school="Terna College", degree="BE", start_date="2018", end_date="2022"),
        ],
    )


class _FakeStructured:
    def __init__(self, out: TailoredResume) -> None:
        self._out = out

    def invoke(self, _msgs: Any) -> TailoredResume:
        return self._out


class _DroppingLLM:
    """Simulates a small / free-tier model that returns an empty
    experience + projects list (the failure mode this test pins)."""

    captured_messages: Any = None

    def __init__(self, *, drop_experience: bool = True, drop_projects: bool = True) -> None:
        self._drop_exp = drop_experience
        self._drop_proj = drop_projects

    def with_structured_output(self, _schema: type[Any]) -> _FakeStructured:
        out = TailoredResume(
            document_title="Sakshi B.",
            summary="Data engineer.",
            skills=["ETL", "SQL"],
            experience=[] if self._drop_exp else [],  # explicit for clarity
            projects=[] if self._drop_proj else [],
        )
        return _FakeStructured(out)


# ---------------------------------------------------------------- #
# Prompt expectations                                               #
# ---------------------------------------------------------------- #


def test_system_prompt_calls_out_experience_and_projects() -> None:
    """Regression guard: the prompt MUST mention EXPERIENCE and
    PROJECTS by name and instruct the model to keep every entry. We
    learned the hard way that without these clauses, smaller models
    silently emit empty lists and the resume ships with no work
    history."""
    src = inspect.getsource(rt_module.tailor_resume)
    assert "EXPERIENCE:" in src
    assert "every role" in src.lower()
    assert "PROJECTS:" in src
    assert "every project" in src.lower()


# ---------------------------------------------------------------- #
# Fallback: empty LLM → restored from profile                       #
# ---------------------------------------------------------------- #


def _job() -> RawJob:
    return RawJob(
        job_id="job1",
        title="ETL Developer",
        company="PwC",
        description="Looking for ETL + SQL skills.",
    )


def test_empty_experience_is_backfilled_from_profile() -> None:
    out = tailor_resume(
        _DroppingLLM(),
        profile_text=_PROFILE_TEXT,
        job=_job(),
        skills=[],
        profile_skills=["ETL", "SQL"],
        profile=_profile_with_experience(),
    )
    assert len(out.experience) == 2
    companies = [r.company for r in out.experience]
    assert companies == ["Fintellix", "Fintellix"]
    roles = [r.role for r in out.experience]
    assert roles == ["Consultant I", "Associate Consultant"]
    # Bullets are preserved verbatim.
    assert "Led ADF implementation for RBI compliance." in out.experience[0].bullets
    assert "Designed complex ETL workflows." in out.experience[1].bullets
    # Date range is formatted as "start – end".
    assert "March 2025" in out.experience[0].dates
    assert "Present" in out.experience[0].dates


def test_empty_projects_is_backfilled_from_profile() -> None:
    out = tailor_resume(
        _DroppingLLM(),
        profile_text=_PROFILE_TEXT,
        job=_job(),
        skills=[],
        profile_skills=["ETL"],
        profile=_profile_with_experience(),
    )
    assert len(out.projects) == 1
    assert out.projects[0].name == "CIMS Reporting"
    # ``description`` is promoted to the first bullet so it lands
    # in the rendered resume (the renderer doesn't have a separate
    # description slot).
    assert out.projects[0].bullets[0] == "Daily RBI submissions."
    assert "Reduced manual ops by 30%." in out.projects[0].bullets


def test_fallback_does_not_overwrite_non_empty_llm_output() -> None:
    """When the LLM did emit experience entries, we MUST trust them —
    the LLM presumably rewrote them for relevance and we don't want
    to clobber that with the raw profile text."""

    class _GoodLLM:
        def with_structured_output(self, _schema: type[Any]) -> _FakeStructured:
            from jobapply.models import ExperienceRole

            return _FakeStructured(
                TailoredResume(
                    document_title="Sakshi B.",
                    skills=["ETL"],
                    experience=[
                        ExperienceRole(
                            company="Fintellix",
                            role="Consultant",
                            dates="2025",
                            bullets=["Tailored bullet for THIS job."],
                        ),
                    ],
                )
            )

    out = tailor_resume(
        _GoodLLM(),
        profile_text=_PROFILE_TEXT,
        job=_job(),
        skills=[],
        profile_skills=["ETL"],
        profile=_profile_with_experience(),
    )
    assert len(out.experience) == 1
    assert out.experience[0].bullets == ["Tailored bullet for THIS job."]


def test_no_fallback_when_profile_is_none() -> None:
    """Backwards-compat: callers that don't pass ``profile`` (e.g.
    legacy tests / older code paths) shouldn't get any new
    behaviour. Empty experience stays empty."""
    out = tailor_resume(
        _DroppingLLM(),
        profile_text=_PROFILE_TEXT,
        job=_job(),
        skills=[],
        profile_skills=["ETL"],
        profile=None,
    )
    assert out.experience == []
    assert out.projects == []


# ---------------------------------------------------------------- #
# Helpers behave correctly on edge cases                            #
# ---------------------------------------------------------------- #


def test_experience_helper_skips_blank_rows() -> None:
    """A profile row with no company / role / bullets is junk and
    should be dropped from the fallback so we don't render an empty
    bullet list."""
    profile = Profile(
        experience=[
            ProfileExperience(),  # all-blank
            ProfileExperience(company="X", role="Y", bullets=["b1"]),
        ]
    )
    out = _experience_from_profile(profile)
    assert len(out) == 1
    assert out[0].company == "X"


def test_projects_helper_promotes_description_to_bullets() -> None:
    profile = Profile(
        projects=[
            ProfileProject(name="P", description="Cool stuff", bullets=["did things"]),
        ]
    )
    out = _projects_from_profile(profile)
    assert out[0].bullets == ["Cool stuff", "did things"]


def test_projects_helper_avoids_duplicate_description() -> None:
    """If the description already appears in the bullets list, don't
    add it twice — users sometimes copy the same line into both fields."""
    profile = Profile(
        projects=[
            ProfileProject(name="P", description="Cool stuff", bullets=["Cool stuff"]),
        ]
    )
    out = _projects_from_profile(profile)
    assert out[0].bullets == ["Cool stuff"]
