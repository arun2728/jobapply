"""Pydantic models for search input, jobs, agent outputs, and persisted records."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class LedgerStatus(StrEnum):
    pending = "pending"
    tailored = "tailored"
    rendered = "rendered"
    done = "done"
    skipped = "skipped"
    failed = "failed"


class JobSearchInput(BaseModel):
    """User search parameters."""

    titles: list[str] = Field(..., min_length=1, description="One or more job titles to search.")
    skills: list[str] = Field(default_factory=list, description="Primary skills (boost search).")
    location: str | None = Field(None, description="City, country, or empty if remote-only.")
    remote: bool = Field(False, description="If true, bias toward remote-friendly queries.")
    results_wanted: int = Field(30, ge=1, le=500)
    hours_old: int = Field(720, ge=0, description="Max age of postings in hours (JobSpy).")
    site_names: list[str] = Field(
        default_factory=lambda: ["indeed", "linkedin", "google"],
        description="JobSpy site_name list.",
    )


class RawJob(BaseModel):
    """Normalized job row from JobSpy / search layer."""

    model_config = {"extra": "allow"}

    job_id: str = Field(..., description="Stable id for ledger (hash of key fields).")
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    job_url: str | None = None
    apply_url: str | None = None
    site: str = ""
    date_posted: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict, description="Original row as dict.")


class FitScore(BaseModel):
    """Structured output from fit-scoring agent."""

    score: float = Field(..., ge=0.0, le=1.0)
    rationale: str = ""
    missing_keywords: list[str] = Field(default_factory=list)
    must_haves_present: list[str] = Field(default_factory=list)


class ExperienceRole(BaseModel):
    company: str
    role: str
    dates: str = ""
    bullets: list[str] = Field(default_factory=list)


class ProjectItem(BaseModel):
    name: str
    bullets: list[str] = Field(default_factory=list)


class TailoredResume(BaseModel):
    """Structured resume body (rendered to MD/LaTeX)."""

    document_title: str = Field("", description="Candidate name for PDF header.")
    contact_line: str = Field(
        "",
        description="One line: email | phone | links (plain text; escaped for LaTeX).",
    )
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceRole] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)


class CoverLetter(BaseModel):
    header: str = ""
    opening: str = ""
    body: str = ""
    closing: str = ""

    def as_markdown(self) -> str:
        parts = [p for p in (self.header, self.opening, self.body, self.closing) if p.strip()]
        return "\n\n".join(parts).strip() + "\n"


class OutreachMessages(BaseModel):
    referral_request: str = ""
    cold_email: str = ""


class JobArtifacts(BaseModel):
    """Paths written under output/run-.../jobs/<slug>/."""

    job_json: str | None = None
    resume_md: str | None = None
    resume_pdf: str | None = None
    resume_tex: str | None = None
    resume_latex_pdf: str | None = None
    cover_letter_md: str | None = None
    cover_letter_pdf: str | None = None
    networking_json: str | None = None


class JobRecord(BaseModel):
    """Single job entry in jobs.json and in-memory results."""

    job_id: str
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    job_url: str | None = None
    apply_url: str | None = None
    site: str = ""
    status: LedgerStatus = LedgerStatus.pending
    fit: FitScore | None = None
    tailored_resume: TailoredResume | None = None
    cover_letter: CoverLetter | None = None
    networking: OutreachMessages | None = None
    artifacts: JobArtifacts = Field(default_factory=JobArtifacts)
    error: str | None = None
    processed_at: datetime | None = None

    def model_dump_for_json(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        if isinstance(d.get("processed_at"), datetime):
            d["processed_at"] = d["processed_at"].isoformat()
        return d


class JobsIndex(BaseModel):
    """Root object for jobs.json."""

    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    search: JobSearchInput
    profile_path: str
    provider: str
    model: str
    jobs: list[JobRecord] = Field(default_factory=list)
