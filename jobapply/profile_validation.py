"""Lightweight structural checks for ``profile.json``.

Each missing or empty field becomes a :class:`ProfileIssue` the CLI can
render as a friendly warning so the user fixes the file before they kick
off a real run. ``required`` issues block the resume tailor from producing
a useful document; ``recommended`` ones just lower quality.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jobapply.profile import Profile, ProfileLoadError, load_profile

REQUIRED_FIELDS: tuple[str, ...] = ("name", "email")
RECOMMENDED_FIELDS: tuple[str, ...] = ("phone", "location", "links")
REQUIRED_SECTIONS: tuple[str, ...] = ("experience", "education")
RECOMMENDED_SECTIONS: tuple[str, ...] = ("skills", "projects")


@dataclass(frozen=True)
class ProfileIssue:
    """A single problem we noticed in ``profile.json``."""

    field: str
    severity: str  # "required" or "recommended"
    message: str

    @property
    def is_required(self) -> bool:
        return self.severity == "required"


def _has_any_link(profile: Profile) -> bool:
    """True if any named handle field or ``other_links`` entry is populated."""
    if any(
        getattr(profile, key) for key in ("portfolio", "github", "linkedin", "medium", "twitter")
    ):
        return True
    return any((link.url or "").strip() for link in profile.other_links)


def _experience_has_content(profile: Profile) -> bool:
    """Each role must have at least one of company/role and one bullet."""
    for role in profile.experience:
        identifier = (role.company or "").strip() or (role.role or "").strip()
        bullets = [b for b in role.bullets if b and b.strip()]
        if identifier and bullets:
            return True
    return False


def _education_has_content(profile: Profile) -> bool:
    return any((school.school or "").strip() for school in profile.education)


def validate_profile(profile: Profile) -> list[ProfileIssue]:
    """Return ordered :class:`ProfileIssue` entries for ``profile``.

    Required issues come first, then recommended ones. Field values are
    treated as missing when they're empty after stripping whitespace.
    """
    issues: list[ProfileIssue] = []

    if not profile.name.strip():
        issues.append(
            ProfileIssue(
                field="name",
                severity="required",
                message="`name` is empty — set it to your full name.",
            )
        )
    if not profile.email.strip():
        issues.append(
            ProfileIssue(
                field="email",
                severity="required",
                message="`email` is empty — recruiters need a way to reach you.",
            )
        )

    if not _experience_has_content(profile):
        issues.append(
            ProfileIssue(
                field="experience",
                severity="required",
                message=(
                    "`experience` is empty — add at least one role with a "
                    "company/role and at least one bullet."
                ),
            )
        )

    if not _education_has_content(profile):
        issues.append(
            ProfileIssue(
                field="education",
                severity="required",
                message="`education` is empty — add at least one school entry.",
            )
        )

    for field in ("phone", "location"):
        if not getattr(profile, field).strip():
            issues.append(
                ProfileIssue(
                    field=field,
                    severity="recommended",
                    message=(f"`{field}` is empty — recruiters expect this on a resume."),
                )
            )

    if not _has_any_link(profile):
        issues.append(
            ProfileIssue(
                field="links",
                severity="recommended",
                message=(
                    "No links set — populate at least one of `portfolio`, "
                    "`github`, `linkedin`, `medium`, `twitter`, or `other_links`."
                ),
            )
        )

    if not profile.skills:
        issues.append(
            ProfileIssue(
                field="skills",
                severity="recommended",
                message=(
                    "`skills` is empty — add the technologies you want surfaced "
                    "on every tailored resume."
                ),
            )
        )

    if not profile.projects:
        issues.append(
            ProfileIssue(
                field="projects",
                severity="recommended",
                message=(
                    "`projects` is empty — add side / open-source / portfolio "
                    "projects so the tailored resume has more material to draw on."
                ),
            )
        )

    if profile.education:
        for idx, school in enumerate(profile.education):
            label = (school.school or f"#{idx + 1}").strip()
            if not school.gpa.strip():
                issues.append(
                    ProfileIssue(
                        field=f"education[{idx}].gpa",
                        severity="recommended",
                        message=(
                            f"Education entry '{label}' has no `gpa` — add it if "
                            "available so the tailored resume can surface it."
                        ),
                    )
                )
            if not school.coursework:
                issues.append(
                    ProfileIssue(
                        field=f"education[{idx}].coursework",
                        severity="recommended",
                        message=(
                            f"Education entry '{label}' has no `coursework` — list "
                            "relevant courses for the tailored resume to pick from."
                        ),
                    )
                )

    return issues


def validate_profile_path(path: Path) -> list[ProfileIssue]:
    """Read ``path`` (JSON) and run :func:`validate_profile`.

    A missing or unparseable file collapses to a single ``required`` issue
    so the caller can short-circuit with a friendly message.
    """
    try:
        profile = load_profile(path)
    except ProfileLoadError as exc:
        return [ProfileIssue(field="profile", severity="required", message=str(exc))]
    return validate_profile(profile)


# --- Skill merging --------------------------------------------------------- #
#
# Used by the resume-tailor agent to guarantee every profile skill ends up in
# the rendered resume regardless of perceived job-relevance. The skill source
# itself is now ``Profile.skills`` (a flat list), so the markdown parsing the
# old ``profile.md`` flow needed has been retired — only the merge helper
# remains, since the LLM still occasionally drops "irrelevant" skills.


def merge_skills_preserving_order(primary: list[str], required: list[str]) -> list[str]:
    """Return ``primary`` with any missing ``required`` items appended.

    Match is case-insensitive so ``"python"`` and ``"Python"`` collide. The
    casing in ``primary`` wins for entries already present; missing
    entries are appended in their ``required`` order with their original
    casing.
    """
    have = {s.strip().lower() for s in primary if s and s.strip()}
    out = [s for s in primary if s and s.strip()]
    for s in required:
        clean = (s or "").strip()
        if not clean:
            continue
        if clean.lower() in have:
            continue
        have.add(clean.lower())
        out.append(clean)
    return out
