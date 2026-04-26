"""Atomic jobs.json updates and run-level exports (CSV)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from jobapply.models import JobRecord, JobsIndex
from jobapply.utils import atomic_write_json


def load_or_init_index(path: Path, template: JobsIndex) -> JobsIndex:
    if not path.is_file():
        atomic_write_json(path, template.model_dump(mode="json"))
        return template
    data = json.loads(path.read_text(encoding="utf-8"))
    return JobsIndex.model_validate(data)


def upsert_job_record(run_dir: Path, template: JobsIndex, record: JobRecord) -> None:
    path = run_dir / "jobs.json"
    idx = load_or_init_index(path, template)
    by_id = {j.job_id: j for j in idx.jobs}
    by_id[record.job_id] = record
    idx.jobs = sorted(by_id.values(), key=lambda j: j.job_id)
    atomic_write_json(path, idx.model_dump(mode="json"))


def write_job_json(job_dir: Path, payload: dict[str, Any]) -> None:
    p = job_dir / "job.json"
    atomic_write_json(p, payload)


# ----------------------------- CSV export -------------------------------- #

# Column order is tuned for Google Sheets triage: identifying info first,
# scoring next, links + artifact paths last. ``=HYPERLINK(url, "open")`` is
# a typical Sheets formula users can apply on URL/path columns.
CSV_FIELDS: tuple[str, ...] = (
    "run_id",
    "job_id",
    "title",
    "company",
    "location",
    "site",
    "date_posted",
    "status",
    "fit_score",
    "fit_rationale",
    "missing_keywords",
    "url",
    "apply_url",
    "description",
    "resume_md",
    "resume_pdf",
    "resume_tex",
    "resume_latex_pdf",
    "cover_letter_md",
    "cover_letter_pdf",
    "cover_letter_tex",
    "cover_letter_latex_pdf",
    "networking_json",
    "error",
    "processed_at",
)

_DESCRIPTION_TRUNC = 1000


def _flatten_record(record: JobRecord, run_id: str) -> dict[str, str]:
    fit = record.fit
    art = record.artifacts
    raw_desc = (record.description or "").replace("\r", "")
    description = raw_desc.strip()
    if len(description) > _DESCRIPTION_TRUNC:
        description = description[:_DESCRIPTION_TRUNC].rstrip() + "…"
    processed = ""
    if record.processed_at is not None:
        processed = record.processed_at.isoformat()
    row: dict[str, str] = {
        "run_id": run_id,
        "job_id": record.job_id,
        "title": record.title or "",
        "company": record.company or "",
        "location": record.location or "",
        "site": record.site or "",
        "date_posted": "",
        "status": str(record.status),
        "fit_score": f"{fit.score:.3f}" if fit else "",
        "fit_rationale": (fit.rationale if fit else ""),
        "missing_keywords": ", ".join(fit.missing_keywords) if fit else "",
        "url": record.job_url or record.apply_url or "",
        "apply_url": record.apply_url or "",
        "description": description,
        "resume_md": art.resume_md or "",
        "resume_pdf": art.resume_pdf or "",
        "resume_tex": art.resume_tex or "",
        "resume_latex_pdf": art.resume_latex_pdf or "",
        "cover_letter_md": art.cover_letter_md or "",
        "cover_letter_pdf": art.cover_letter_pdf or "",
        "cover_letter_tex": art.cover_letter_tex or "",
        "cover_letter_latex_pdf": art.cover_letter_latex_pdf or "",
        "networking_json": art.networking_json or "",
        "error": (record.error or "").strip(),
        "processed_at": processed,
    }
    return row


def write_jobs_csv(run_dir: Path, idx: JobsIndex) -> Path:
    """Write a Google-Sheets-friendly CSV of the run's jobs.

    One row per :class:`JobRecord` in ``jobs.json``, sorted by descending
    fit score (``done`` first, ``cached``/``skipped``/``failed`` after) so
    the most relevant rows surface at the top when imported. Returns the
    written path.
    """
    csv_path = run_dir / "jobs.csv"

    def _sort_key(rec: JobRecord) -> tuple[int, float]:
        rank_by_status = {
            "done": 0,
            "cached": 1,
            "skipped": 2,
            "failed": 3,
            "pending": 4,
        }
        rank = rank_by_status.get(str(rec.status), 5)
        score = -(rec.fit.score if rec.fit else 0.0)
        return (rank, score)

    sorted_records = sorted(idx.jobs, key=_sort_key)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(CSV_FIELDS), quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for record in sorted_records:
            writer.writerow(_flatten_record(record, run_id=idx.run_id))
    return csv_path


def write_jobs_csv_from_path(jobs_json: Path, run_dir: Path | None = None) -> Path | None:
    """Convenience wrapper: load ``jobs.json`` and emit ``jobs.csv`` next to it.

    Returns ``None`` when ``jobs.json`` is missing or unparseable so the CLI
    summary can degrade gracefully.
    """
    if not jobs_json.is_file():
        return None
    try:
        data = json.loads(jobs_json.read_text(encoding="utf-8"))
        idx = JobsIndex.model_validate(data)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    target_dir = run_dir or jobs_json.parent
    return write_jobs_csv(target_dir, idx)
