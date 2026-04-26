"""Lightweight structural checks for ``profile.md``.

We don't try to fully parse the document — just look for the section
headings the resume-tailor relies on and the few "must have" header
fields (Name, Email). Each missing piece becomes a :class:`ProfileIssue`
the CLI can render as a friendly warning so the user can fix the file
before they kick off a real run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Required vs recommended fields. ``required`` blocks resume tailoring from
# producing a useful document; ``recommended`` ones just lower quality.
REQUIRED_HEADER_FIELDS: tuple[str, ...] = ("Name", "Email")
RECOMMENDED_HEADER_FIELDS: tuple[str, ...] = ("Phone", "Location", "Links")
REQUIRED_SECTIONS: tuple[str, ...] = ("Experience", "Education")
RECOMMENDED_SECTIONS: tuple[str, ...] = ("Skills", "Projects")
RECOMMENDED_EDUCATION_FIELDS: tuple[str, ...] = ("GPA", "Course Work")


@dataclass(frozen=True)
class ProfileIssue:
    """A single problem we noticed in ``profile.md``."""

    field: str
    severity: str  # "required" or "recommended"
    message: str

    @property
    def is_required(self) -> bool:
        return self.severity == "required"


_HEADER_LINE_RE = re.compile(
    # Accepts both bullet form (``- **Name:** value``) and bare form
    # (``**Name:** value``) since LLM rewrites often drop the leading dash.
    r"^[ \t]*(?:-[ \t]*)?\*\*(?P<key>[^*]+):\*\*[ \t]*(?P<val>[^\n]*)$",
    re.MULTILINE,
)
_SECTION_RE = re.compile(r"^##\s+(?P<name>[^\n]+?)\s*$", re.MULTILINE)
# An indented continuation line under a header bullet, e.g. ``  - LinkedIn: ...``.
_CONTINUATION_RE = re.compile(r"^[ \t]+\S")


def _section_body(text: str, section: str) -> str:
    """Return the body between ``## <section>`` and the next ``##`` heading.

    Tolerates suffixes after the section name (e.g. ``## Skills (grouped)``
    matches ``Skills``). The match is anchored on a word boundary so
    ``## Skill`` won't accidentally match a section literally named
    ``Skills``.
    """
    pattern = re.compile(
        rf"^##\s+{re.escape(section)}\b[^\n]*\n(?P<body>.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group("body").strip() if match else ""


# Lines copied verbatim from ``_PROFILE_TEMPLATE`` in ``profile_import``.
# When a section contains only these we treat it as still empty so the
# user gets a warning instead of an "all good" green light.
_PLACEHOLDER_LINES: frozenset[str] = frozenset(
    {
        "bullet",
        "description",
        "company",
        "role",
        "school",
        "degree",
        "company | role | start - end",
        "school | degree | start - end",
        "school, degree, years",
        "project: description",
        "(empty resume)",
        "course a, course b, course c",
        "(optional)",
        "0.0/0.0",
    }
)


_LIST_MARKER_RE = re.compile(r"^(?:#{1,6}\s+|[-*+]\s+)")


def _strip_list_marker(line: str) -> str:
    """Remove a single leading bullet or markdown heading marker.

    Keeps inline ``**bold**`` markers intact — important for lines like
    ``- **Languages:** Python`` where stripping all ``*`` would turn the
    label into ``Languages:** Python`` and confuse the regex below.
    """
    return _LIST_MARKER_RE.sub("", line.strip(), count=1).strip()


def _has_substantive_content(body: str) -> bool:
    """True iff the section has at least one non-template, non-blank line.

    A line is "template" when, after stripping list markers and bold key
    labels (``**Foo:**``), the remaining text is empty or matches one of
    the verbatim phrases we ship in ``_PROFILE_TEMPLATE``.
    """
    for raw in body.splitlines():
        line = _strip_list_marker(raw)
        if not line:
            continue
        cleaned = re.sub(r"^\*\*[^*]+:\*\*", "", line).strip()
        candidate = (cleaned or line).lower()
        if candidate in _PLACEHOLDER_LINES:
            continue
        if cleaned:
            return True
    return False


def _document_prefix(text: str) -> str:
    """Return everything before the first ``## ...`` heading.

    LLM rewrites sometimes drop the explicit ``## Header`` section and put
    the contact bullets right under the H1 title — falling back to the
    pre-section prefix means we still find ``**Name:**`` in those files.
    """
    match = re.search(r"(?m)^##\s+\S", text)
    return text[: match.start()] if match else text


def _header_fields(text: str) -> dict[str, str]:
    """Map ``Name`` / ``Email`` / ``Phone`` / ``Location`` / ``Links`` to their value.

    Looks first inside an explicit ``## Header`` section and falls back to
    the document prefix (everything before the first ``## ...`` heading)
    when no Header section exists. A field with no inline value but an
    indented continuation line beneath it counts as populated.
    """
    body = _section_body(text, "Header")
    if not body.strip():
        body = _document_prefix(text)
    lines = body.splitlines()
    out: dict[str, str] = {}
    for idx, raw in enumerate(lines):
        match = _HEADER_LINE_RE.match(raw)
        if not match:
            continue
        key = match.group("key").strip()
        val = match.group("val").strip()
        if not val:
            for follow in lines[idx + 1 :]:
                if not follow.strip():
                    break
                if not _CONTINUATION_RE.match(follow):
                    break
                val = follow.strip()
                break
        out[key] = val
    return out


def validate_profile_text(text: str) -> list[ProfileIssue]:
    """Return ordered :class:`ProfileIssue` entries for ``text``.

    Required issues come first, then recommended ones.
    """
    issues: list[ProfileIssue] = []
    header = _header_fields(text)

    for field in REQUIRED_HEADER_FIELDS:
        if not header.get(field, "").strip():
            issues.append(
                ProfileIssue(
                    field=f"Header.{field}",
                    severity="required",
                    message=f"Header is missing **{field}** — add it to the Header section.",
                )
            )

    for section in REQUIRED_SECTIONS:
        body = _section_body(text, section)
        if not _has_substantive_content(body):
            issues.append(
                ProfileIssue(
                    field=section,
                    severity="required",
                    message=(
                        f"`## {section}` section is empty or only contains the template "
                        "placeholder — add at least one entry."
                    ),
                )
            )

    for field in RECOMMENDED_HEADER_FIELDS:
        if not header.get(field, "").strip():
            issues.append(
                ProfileIssue(
                    field=f"Header.{field}",
                    severity="recommended",
                    message=f"Header is missing **{field}** — recruiters expect this on a resume.",
                )
            )

    for section in RECOMMENDED_SECTIONS:
        body = _section_body(text, section)
        if not _has_substantive_content(body):
            issues.append(
                ProfileIssue(
                    field=section,
                    severity="recommended",
                    message=(
                        f"`## {section}` section is empty — fill it in for stronger tailoring."
                    ),
                )
            )

    education = _section_body(text, "Education")
    if _has_substantive_content(education):
        edu_lower = education.lower()
        for field in RECOMMENDED_EDUCATION_FIELDS:
            if field.lower() not in edu_lower:
                issues.append(
                    ProfileIssue(
                        field=f"Education.{field}",
                        severity="recommended",
                        message=(
                            f"Education section has no **{field}** entry — add it if available "
                            "so the tailored resume can surface it."
                        ),
                    )
                )

    return issues


def validate_profile_path(path: Path) -> list[ProfileIssue]:
    """Read ``path`` and run :func:`validate_profile_text`. Missing files report
    a single required issue so the caller can short-circuit."""
    if not path.is_file():
        return [
            ProfileIssue(
                field="profile",
                severity="required",
                message=f"profile.md not found at {path} — run `jobapply init` first.",
            )
        ]
    return validate_profile_text(path.read_text(encoding="utf-8"))


# --- Skill extraction ------------------------------------------------------ #
#
# Used by the resume-tailor agent to guarantee every profile skill ends up in
# the rendered resume regardless of perceived job-relevance. Lives here so the
# regex/heuristics that "understand" profile.md layout stay in one place.

# Strips a leading ``**Category:**`` or ``**Category**:`` label so we can
# operate on just the comma-separated skill list that follows.
_CATEGORY_LABEL_RE = re.compile(r"^\*\*[^*]+?\*\*\s*:?\s*")


def _split_top_level_commas(value: str) -> list[str]:
    """Split on commas that are not nested inside parentheses or brackets.

    Keeps tokens like ``Model Context Protocol (MCP)`` intact even if they
    happen to contain commas inside the parens.
    """
    out: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in value:
        if ch in "([{":
            depth += 1
            buf.append(ch)
        elif ch in ")]}":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            piece = "".join(buf).strip()
            if piece:
                out.append(piece)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def extract_profile_skills(text: str) -> list[str]:
    """Return every individual skill listed in ``## Skills`` of ``text``.

    Handles the two shapes ``profile.md`` ships with:

    1. Categorized bullets — ``- **Languages:** TypeScript, Python``
    2. Bare bullets — ``- Kubernetes``

    Also tolerates non-bullet lines, sub-bullets, and skills wrapped in
    inline markdown (``*Python*``). Splits each line on top-level commas so
    parenthesized tokens like ``Model Context Protocol (MCP)`` stay
    intact. The result preserves the order skills appear in the profile and
    is deduplicated case-insensitively (first occurrence wins, retaining
    the user's original casing).
    """
    body = _section_body(text, "Skills")
    if not body.strip():
        return []

    seen_lower: set[str] = set()
    skills: list[str] = []

    for raw in body.splitlines():
        line = _strip_list_marker(raw)
        if not line:
            continue
        line = _CATEGORY_LABEL_RE.sub("", line, count=1).strip()
        if not line:
            continue
        for piece in _split_top_level_commas(line):
            cleaned = piece.strip().strip("*_`").strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen_lower:
                continue
            seen_lower.add(key)
            skills.append(cleaned)
    return skills


def merge_skills_preserving_order(
    primary: list[str], required: list[str]
) -> list[str]:
    """Return ``primary`` with any missing ``required`` items appended.

    Match is case-insensitive so ``"python"`` and ``"Python"`` collide. The
    casing in ``primary`` wins for entries already present; missing
    entries are appended in their ``required`` order with their original
    casing. Used by the resume-tailor agent to guarantee every profile
    skill survives the LLM round-trip even if the model drops some.
    """
    have = {s.strip().lower() for s in primary if s.strip()}
    out = [s for s in primary if s and s.strip()]
    for s in required:
        clean = s.strip()
        if not clean:
            continue
        if clean.lower() in have:
            continue
        have.add(clean.lower())
        out.append(clean)
    return out
