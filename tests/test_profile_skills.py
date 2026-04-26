"""Tests for ``extract_profile_skills`` and ``merge_skills_preserving_order``.

The resume-tailor agent relies on these helpers to guarantee every profile
skill appears in the rendered resume, regardless of perceived job-relevance.
The parser must handle the two ``profile.md`` shapes (categorized bullets
and bare bullets), keep parenthesized tokens intact, and dedupe
case-insensitively.
"""

from __future__ import annotations

from jobapply.profile_validation import (
    _split_top_level_commas,
    extract_profile_skills,
    merge_skills_preserving_order,
)


def test_split_top_level_commas_keeps_paren_groups_intact() -> None:
    out = _split_top_level_commas("Python, Model Context Protocol (MCP, alias), Kubernetes")
    assert out == ["Python", "Model Context Protocol (MCP, alias)", "Kubernetes"]


def test_split_top_level_commas_handles_unbalanced_parens() -> None:
    # Stray ``)`` shouldn't make depth go negative and start swallowing commas.
    out = _split_top_level_commas("A) , B, C")
    assert out == ["A)", "B", "C"]


def test_extract_profile_skills_categorized_bullets() -> None:
    md = (
        "# Header\n"
        "**Name:** Test\n\n"
        "## Skills\n"
        "- **Languages:** TypeScript, Python\n"
        "- **Frameworks:** Model Context Protocol (MCP)\n"
        "- **Cloud / Infra:** AWS, Kubernetes\n\n"
        "## Experience\n"
        "- something\n"
    )
    assert extract_profile_skills(md) == [
        "TypeScript",
        "Python",
        "Model Context Protocol (MCP)",
        "AWS",
        "Kubernetes",
    ]


def test_extract_profile_skills_bare_bullets() -> None:
    md = "## Skills\n- Python\n- TypeScript\n- Kubernetes\n"
    assert extract_profile_skills(md) == ["Python", "TypeScript", "Kubernetes"]


def test_extract_profile_skills_mixed_shapes_and_dedup() -> None:
    md = (
        "## Skills\n"
        "- **Languages:** Python, TypeScript\n"
        "- python\n"  # duplicate (case-insensitive) — must be dropped
        "- *Go*\n"  # inline italic — markers stripped
        "- **Cloud:** AWS, aws\n"  # duplicate inside same line
    )
    assert extract_profile_skills(md) == ["Python", "TypeScript", "Go", "AWS"]


def test_extract_profile_skills_returns_empty_when_section_missing() -> None:
    assert extract_profile_skills("# Resume\n\n## Experience\n- thing\n") == []


def test_extract_profile_skills_returns_empty_when_section_blank() -> None:
    assert extract_profile_skills("## Skills\n\n## Experience\n- thing\n") == []


def test_extract_profile_skills_tolerates_section_suffix() -> None:
    """``## Skills (grouped)`` must still match — same rule
    ``_section_body`` already applies for validation.
    """
    md = "## Skills (grouped)\n- Python\n- Rust\n"
    assert extract_profile_skills(md) == ["Python", "Rust"]


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
