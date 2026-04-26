"""Verify the run-level CSV export.

Covers column ordering, status sorting (``done`` first, ``failed`` last),
artifact path emission, fit-score formatting, description truncation, and
graceful no-op when ``jobs.json`` is missing.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from jobapply.models import (
    FitScore,
    JobArtifacts,
    JobRecord,
    JobSearchInput,
    JobsIndex,
    LedgerStatus,
)
from jobapply.nodes.persist import (
    CSV_FIELDS,
    upsert_job_record,
    write_jobs_csv,
    write_jobs_csv_from_path,
)


def _make_index(run_id: str = "run-test") -> JobsIndex:
    return JobsIndex(
        run_id=run_id,
        search=JobSearchInput(titles=["ML Engineer"]),
        profile_path="profile.md",
        provider="ollama",
        model="llama3",
    )


def _done_record(
    jid: str,
    score: float,
    *,
    title: str = "ML Eng",
    company: str = "Acme",
) -> JobRecord:
    return JobRecord(
        job_id=jid,
        title=title,
        company=company,
        location="Remote",
        description="Build ML systems at scale.",
        job_url=f"https://example.com/jobs/{jid}",
        apply_url=f"https://example.com/apply/{jid}",
        site="indeed",
        status=LedgerStatus.done,
        fit=FitScore(score=score, rationale="Strong fit", missing_keywords=["Rust"]),
        artifacts=JobArtifacts(
            resume_md=f"/runs/jobs/{jid}/resume.md",
            resume_pdf=f"/runs/jobs/{jid}/resume.pdf",
            cover_letter_md=f"/runs/jobs/{jid}/cover_letter.md",
            cover_letter_pdf=f"/runs/jobs/{jid}/cover_letter.pdf",
            cover_letter_tex=f"/runs/jobs/{jid}/cover_letter.tex",
        ),
        processed_at=datetime(2026, 4, 26, 10, 30, tzinfo=UTC),
    )


def test_writes_csv_with_expected_header(tmp_path: Path) -> None:
    idx = _make_index()
    idx.jobs = [_done_record("a1", 0.7)]
    out = write_jobs_csv(tmp_path, idx)
    assert out == tmp_path / "jobs.csv"
    with out.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames is not None
        assert tuple(reader.fieldnames) == CSV_FIELDS
        rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["job_id"] == "a1"
    assert rows[0]["title"] == "ML Eng"
    assert rows[0]["status"] == "done"


def test_rows_sort_done_then_cached_then_failed(tmp_path: Path) -> None:
    idx = _make_index()
    idx.jobs = [
        JobRecord(job_id="failed-1", status=LedgerStatus.failed),
        JobRecord(job_id="cached-1", status=LedgerStatus.cached),
        _done_record("done-1", 0.55),
        _done_record("done-2", 0.92),
        JobRecord(job_id="skipped-1", status=LedgerStatus.skipped),
    ]
    write_jobs_csv(tmp_path, idx)
    with (tmp_path / "jobs.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    statuses = [r["status"] for r in rows]
    assert statuses == ["done", "done", "cached", "skipped", "failed"]
    # Within ``done`` rows, the higher fit score comes first.
    assert rows[0]["job_id"] == "done-2"
    assert rows[1]["job_id"] == "done-1"


def test_fit_score_is_formatted_to_three_decimals(tmp_path: Path) -> None:
    idx = _make_index()
    idx.jobs = [_done_record("a1", 0.123456789)]
    write_jobs_csv(tmp_path, idx)
    rows = list(csv.DictReader((tmp_path / "jobs.csv").open(encoding="utf-8")))
    assert rows[0]["fit_score"] == "0.123"
    assert rows[0]["missing_keywords"] == "Rust"


def test_artifact_paths_are_emitted_into_dedicated_columns(tmp_path: Path) -> None:
    idx = _make_index()
    rec = _done_record("art1", 0.81)
    idx.jobs = [rec]
    write_jobs_csv(tmp_path, idx)
    rows = list(csv.DictReader((tmp_path / "jobs.csv").open(encoding="utf-8")))
    row = rows[0]
    assert row["resume_md"].endswith("resume.md")
    assert row["resume_pdf"].endswith("resume.pdf")
    assert row["cover_letter_md"].endswith("cover_letter.md")
    assert row["cover_letter_pdf"].endswith("cover_letter.pdf")
    assert row["cover_letter_tex"].endswith("cover_letter.tex")
    # Empty artifacts stay empty (not 'None').
    assert row["resume_tex"] == ""
    assert row["resume_latex_pdf"] == ""


def test_description_is_truncated_with_ellipsis(tmp_path: Path) -> None:
    idx = _make_index()
    rec = _done_record("d1", 0.5)
    rec.description = "x" * 1500
    idx.jobs = [rec]
    write_jobs_csv(tmp_path, idx)
    rows = list(csv.DictReader((tmp_path / "jobs.csv").open(encoding="utf-8")))
    desc = rows[0]["description"]
    assert desc.endswith("…")
    # 1000 chars + the trailing ellipsis byte.
    assert len(desc) == 1001


def test_empty_index_writes_header_only(tmp_path: Path) -> None:
    idx = _make_index()
    write_jobs_csv(tmp_path, idx)
    text = (tmp_path / "jobs.csv").read_text(encoding="utf-8").splitlines()
    assert len(text) == 1
    assert text[0].startswith("run_id,job_id,title,company,location,site")


def test_from_path_returns_none_when_jobs_json_missing(tmp_path: Path) -> None:
    assert write_jobs_csv_from_path(tmp_path / "jobs.json") is None


def test_from_path_round_trips_via_jobs_json(tmp_path: Path) -> None:
    template = _make_index("run-rt")
    upsert_job_record(tmp_path, template, _done_record("rt1", 0.4))
    out = write_jobs_csv_from_path(tmp_path / "jobs.json")
    assert out == tmp_path / "jobs.csv"
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert rows[0]["run_id"] == "run-rt"
    assert rows[0]["job_id"] == "rt1"


def test_processed_at_is_iso_format(tmp_path: Path) -> None:
    idx = _make_index()
    idx.jobs = [_done_record("t1", 0.5)]
    write_jobs_csv(tmp_path, idx)
    rows = list(csv.DictReader((tmp_path / "jobs.csv").open(encoding="utf-8")))
    assert rows[0]["processed_at"].startswith("2026-04-26T10:30:00")


def test_csv_quotes_commas_in_fields(tmp_path: Path) -> None:
    idx = _make_index()
    rec = _done_record("q1", 0.5)
    rec.title = "Engineer, ML & AI"
    rec.fit = FitScore(score=0.5, rationale="Has Python, Go, and Rust", missing_keywords=[])
    idx.jobs = [rec]
    write_jobs_csv(tmp_path, idx)
    raw = (tmp_path / "jobs.csv").read_text(encoding="utf-8")
    # csv.DictWriter with QUOTE_MINIMAL wraps fields containing commas in quotes.
    assert '"Engineer, ML & AI"' in raw
    assert '"Has Python, Go, and Rust"' in raw
