"""Tests for the profile skill helpers used by the resume-tailor agent.

The skill source has moved from the old ``profile.md`` ``## Skills`` section
to ``Profile.skills`` (a flat list in ``profile.json``). We only need:

* :func:`jobapply.profile.profile_skill_list` — to dedupe + strip the
  list before passing it as the LLM-side "must include" set.
* :func:`jobapply.profile_validation.merge_skills_preserving_order` — the
  belt-and-suspenders merge that re-attaches missing profile skills to the
  LLM's output.
"""

from __future__ import annotations

from jobapply.profile import Profile, profile_skill_list
from jobapply.profile_validation import merge_skills_preserving_order

# ---- profile_skill_list -------------------------------------------------- #


def test_profile_skill_list_strips_blank_and_dedupes_case_insensitively() -> None:
    profile = Profile(
        skills=[
            "Python",
            "  TypeScript  ",
            "python",  # duplicate via case
            "",  # blank dropped
            "TypeScript",  # exact duplicate
            "Model Context Protocol (MCP)",
        ]
    )
    assert profile_skill_list(profile) == [
        "Python",
        "TypeScript",
        "Model Context Protocol (MCP)",
    ]


def test_profile_skill_list_returns_empty_when_no_skills() -> None:
    assert profile_skill_list(Profile()) == []


# ---- merge_skills_preserving_order --------------------------------------- #


def test_merge_skills_appends_missing_in_profile_order() -> None:
    primary = ["Kubernetes", "Python"]  # LLM's relevance ordering
    profile = ["TypeScript", "Python", "Model Context Protocol (MCP)", "AWS", "Kubernetes"]
    merged = merge_skills_preserving_order(primary, profile)
    assert merged == [
        "Kubernetes",
        "Python",
        "TypeScript",
        "Model Context Protocol (MCP)",
        "AWS",
    ]


def test_merge_skills_is_case_insensitive() -> None:
    primary = ["python", "AWS"]
    profile = ["Python", "TypeScript", "aws"]
    merged = merge_skills_preserving_order(primary, profile)
    assert merged == ["python", "AWS", "TypeScript"]


def test_merge_skills_drops_blank_entries() -> None:
    merged = merge_skills_preserving_order(["", "  ", "Python"], ["", "TypeScript", "  "])
    assert merged == ["Python", "TypeScript"]


def test_merge_skills_with_empty_primary_returns_full_profile() -> None:
    profile = ["Python", "TypeScript"]
    assert merge_skills_preserving_order([], profile) == profile


def test_merge_skills_with_empty_profile_returns_primary_unchanged() -> None:
    primary = ["Python", "TypeScript"]
    assert merge_skills_preserving_order(primary, []) == primary
