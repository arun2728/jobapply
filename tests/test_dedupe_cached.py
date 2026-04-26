"""Verify the dedupe node emits cached JobRecord entries for ledger hits.

Repro for the bug where every subsequent run of the same search produced an
empty run dir (no ``jobs.json``, no per-job folders) because all jobs were
already marked ``done`` in the global ledger.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from jobapply.graph import compile_app
from jobapply.ledger import (
    get_engine,
    init_db,
    update_status,
    upsert_pending,
)
from jobapply.models import (
    JobSearchInput,
    LedgerStatus,
    RawJob,
)


@pytest.fixture()
def fake_raw_job() -> dict[str, Any]:
    return RawJob(
        job_id="cachedjob000000000000000000000001",
        title="Senior Python Engineer",
        company="Acme",
        location="Remote",
        description="Use Python and ship things.",
        job_url="https://example.com/job",
        apply_url="https://example.com/apply",
        site="indeed",
    ).model_dump(mode="json")


def _initial_state(
    *,
    tmp_path: Path,
    job_dump: dict[str, Any],
    ledger_path: Path,
    profile_hash: str,
    force: bool = False,
) -> dict[str, Any]:
    run_dir = tmp_path / "run-cached"
    run_dir.mkdir(parents=True, exist_ok=True)
    prof = tmp_path / "profile.md"
    prof.write_text("# Me\nPython.\n", encoding="utf-8")
    inp = JobSearchInput(titles=["Python"], skills=["Python"], location="Remote")
    return {
        "run_id": "run-cached",
        "run_dir": str(run_dir.resolve()),
        "profile_path": str(prof.resolve()),
        "profile_text": prof.read_text(encoding="utf-8"),
        "profile_hash": profile_hash,
        "provider": "gemini",
        "model": "fake",
        "min_fit": 0.1,
        "with_networking": False,
        "no_pdf": True,
        "force": force,
        "ledger_db_path": str(ledger_path.resolve()),
        "search_input": inp.model_dump(mode="json"),
        "jobs_raw": [job_dump],
        "queue": [],
        "skip_search": True,
    }


def test_dedupe_emits_cached_record_for_prior_done_job(
    tmp_path: Path, fake_raw_job: dict[str, Any]
) -> None:
    """Job marked ``done`` in the ledger is rewritten as a ``cached`` entry."""
    ledger = tmp_path / "ledger.db"
    engine = get_engine(ledger)
    init_db(engine)
    profile_hash = "abc123"

    upsert_pending(
        engine,
        job_id=fake_raw_job["job_id"],
        profile_hash=profile_hash,
        site=fake_raw_job["site"],
        company=fake_raw_job["company"],
        title=fake_raw_job["title"],
        location=fake_raw_job["location"],
        apply_url=fake_raw_job["apply_url"],
        job_url=fake_raw_job["job_url"],
        run_id="run-prior",
    )
    update_status(
        engine,
        fake_raw_job["job_id"],
        LedgerStatus.done,
        paths={"resume_md": "/prev/run/resume.md"},
        run_id="run-prior",
    )

    initial = _initial_state(
        tmp_path=tmp_path,
        job_dump=fake_raw_job,
        ledger_path=ledger,
        profile_hash=profile_hash,
    )
    run_dir = Path(initial["run_dir"])
    ck = run_dir / "checkpoint.sqlite"
    app, conn = compile_app(ck)
    try:
        app.invoke(initial, {"configurable": {"thread_id": "run-cached"}})
    finally:
        conn.close()

    jobs_path = run_dir / "jobs.json"
    assert jobs_path.is_file(), "jobs.json must always be written"
    data = json.loads(jobs_path.read_text(encoding="utf-8"))
    assert len(data["jobs"]) == 1
    rec = data["jobs"][0]
    assert rec["status"] == LedgerStatus.cached.value
    assert rec["job_id"] == fake_raw_job["job_id"]
    assert "run-prior" in (rec.get("error") or "")
    assert "--force" in (rec.get("error") or "")
    assert rec["artifacts"]["resume_md"] == "/prev/run/resume.md"


def test_dedupe_force_bypasses_cached_path(tmp_path: Path, fake_raw_job: dict[str, Any]) -> None:
    """``--force`` should ignore ledger hits and put the job back in the queue."""
    ledger = tmp_path / "ledger.db"
    engine = get_engine(ledger)
    init_db(engine)
    profile_hash = "abc123"

    upsert_pending(
        engine,
        job_id=fake_raw_job["job_id"],
        profile_hash=profile_hash,
        site=fake_raw_job["site"],
        company=fake_raw_job["company"],
        title=fake_raw_job["title"],
        location=fake_raw_job["location"],
        apply_url=fake_raw_job["apply_url"],
        job_url=fake_raw_job["job_url"],
        run_id="run-prior",
    )
    update_status(engine, fake_raw_job["job_id"], LedgerStatus.done, run_id="run-prior")

    from jobapply.graph_nodes import dedupe_node

    initial = _initial_state(
        tmp_path=tmp_path,
        job_dump=fake_raw_job,
        ledger_path=ledger,
        profile_hash=profile_hash,
        force=True,
    )
    out = dedupe_node(initial)
    assert len(out["queue"]) == 1, "force=True must enqueue the job"
    assert not out.get("results"), "force=True must not emit cached records"
