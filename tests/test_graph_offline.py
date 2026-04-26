"""Offline graph test with mocked LLM + no JobSpy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from jobapply.graph import compile_app
from jobapply.models import (
    CoverLetter,
    FitScore,
    JobSearchInput,
    LedgerStatus,
    RawJob,
    TailoredResume,
)


class _FakeStructured:
    def __init__(self, out: Any) -> None:
        self._out = out

    def invoke(self, _msgs: Any) -> Any:
        return self._out


class FakeChatModel:
    def with_structured_output(self, schema: type[Any]) -> _FakeStructured:
        if schema.__name__ == "FitScore":
            return _FakeStructured(
                FitScore(
                    score=0.95,
                    rationale="strong",
                    missing_keywords=[],
                    must_haves_present=[],
                ),
            )
        if schema.__name__ == "TailoredResume":
            return _FakeStructured(
                TailoredResume(
                    document_title="Test User",
                    contact_line="test@example.com",
                    summary="Doer of things.",
                    skills=["Python"],
                    experience=[],
                    projects=[],
                ),
            )
        if schema.__name__ == "CoverLetter":
            return _FakeStructured(
                CoverLetter(
                    header="Test User\ntest@example.com",
                    opening="Hello",
                    body="Body",
                    closing="Thanks",
                ),
            )
        raise AssertionError(f"unexpected schema {schema}")


@pytest.fixture()
def fake_raw_job() -> dict[str, Any]:
    r = RawJob(
        job_id="testjobid00000000000000000001",
        title="Python Engineer",
        company="Acme",
        location="Remote",
        description="We need Python and testing.",
        job_url="https://example.com/job",
        apply_url="https://example.com/apply",
        site="indeed",
    )
    return r.model_dump(mode="json")


def test_graph_processes_one_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_raw_job: dict[str, Any],
) -> None:
    import jobapply.graph_nodes as gn

    monkeypatch.setattr(gn, "create_chat_model", lambda *_a, **_k: FakeChatModel())
    monkeypatch.setattr(gn, "md_to_pdf", lambda *_a, **_k: False)
    monkeypatch.setattr(gn, "tex_to_pdf", lambda *_a, **_k: None)

    run_dir = tmp_path / "run-test"
    run_dir.mkdir(parents=True)
    ledger = tmp_path / "ledger.db"
    prof = tmp_path / "profile.md"
    prof.write_text("# Me\nPython expert.\n", encoding="utf-8")
    inp = JobSearchInput(titles=["Python"], skills=["Python"], location="Remote")
    initial: dict[str, Any] = {
        "run_id": "run-test",
        "run_dir": str(run_dir.resolve()),
        "profile_path": str(prof.resolve()),
        "profile_text": prof.read_text(encoding="utf-8"),
        "profile_hash": "deadbeef",
        "provider": "gemini",
        "model": "fake",
        "min_fit": 0.1,
        "with_networking": False,
        "no_pdf": True,
        "force": True,
        "ledger_db_path": str(ledger.resolve()),
        "search_input": inp.model_dump(mode="json"),
        "jobs_raw": [fake_raw_job],
        "queue": [],
        "skip_search": True,
    }
    ck = run_dir / "checkpoint.sqlite"
    app, conn = compile_app(ck)
    try:
        app.invoke(initial, {"configurable": {"thread_id": "run-test"}})
    finally:
        conn.close()

    jobs_path = run_dir / "jobs.json"
    assert jobs_path.is_file()
    data = json.loads(jobs_path.read_text(encoding="utf-8"))
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["status"] == LedgerStatus.done.value
