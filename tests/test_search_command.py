"""Tests for the search-only CLI command.

The ``jobapply search`` command is a lightweight cousin of ``jobapply
run``: it fans out to JobSpy via the search agent, optionally scores
each result against the user's profile, and writes
``output/search-<ts>/jobs.{json,csv}``. These tests stub the search +
score calls so we can verify the orchestration (CSV columns,
``profile.json`` requirements, provider/model wiring, error handling)
without hitting the network or any LLM provider.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from jobapply import cli as cli_module
from jobapply.cli import _record_from_raw_job, app
from jobapply.models import FitScore, LedgerStatus, RawJob


def _raw(jid: str, *, title: str = "ML Engineer", company: str = "Acme") -> RawJob:
    return RawJob(
        job_id=jid,
        title=title,
        company=company,
        location="Remote",
        description="Build ML systems at scale.",
        job_url=f"https://example.com/jobs/{jid}",
        apply_url=f"https://example.com/apply/{jid}",
        site="indeed",
    )


def _write_minimal_profile(path: Path) -> None:
    """Write a profile.json that satisfies ``load_profile`` requirements."""
    payload = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "experience": [
            {
                "company": "Acme",
                "role": "Engineer",
                "bullets": ["Shipped things"],
            }
        ],
        "education": [
            {"school": "MIT", "degree": "BS CS"},
        ],
        "skills": ["Python", "Kubernetes"],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_minimal_toml(path: Path, *, provider: str = "openai") -> None:
    path.write_text(
        f'provider = "{provider}"\n'
        f"profile_path = \"profile.json\"\n"
        f'output_dir = "output"\n'
        f"results_wanted = 5\n"
        f"hours_old = 24\n"
        f"sites = [\"indeed\"]\n"
        f"[providers.{provider}]\n"
        f'api_key = "test-key"\n'
        f'model = "test-model"\n',
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# _record_from_raw_job — pure helper, no I/O
# ---------------------------------------------------------------------------


def test_record_from_raw_job_default_status_is_pending() -> None:
    """Search-only records aren't tailored, so they sit at `pending` until
    the user runs ``jobapply run`` against the same query."""
    rec = _record_from_raw_job(_raw("a1"))
    assert rec.status == LedgerStatus.pending
    assert rec.fit is None
    assert rec.error is None
    assert rec.processed_at is not None


def test_record_from_raw_job_attaches_fit_score() -> None:
    score = FitScore(score=0.84, rationale="Strong python match", missing_keywords=["Rust"])
    rec = _record_from_raw_job(_raw("a1"), fit=score)
    assert rec.fit is not None
    assert rec.fit.score == pytest.approx(0.84)
    assert rec.fit.missing_keywords == ["Rust"]


def test_record_from_raw_job_truncates_description() -> None:
    big = _raw("big")
    big.description = "x" * 9000
    rec = _record_from_raw_job(big)
    assert len(rec.description) == 5000


def test_record_from_raw_job_carries_error_and_links() -> None:
    rec = _record_from_raw_job(_raw("e1"), error="score failed: boom")
    assert rec.error == "score failed: boom"
    assert rec.apply_url and rec.apply_url.endswith("/apply/e1")
    assert rec.job_url and rec.job_url.endswith("/jobs/e1")


# ---------------------------------------------------------------------------
# CLI: fetch-only path (no scoring)
# ---------------------------------------------------------------------------


def test_search_fetch_only_writes_jobs_json_and_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without --score we should write jobs.{json,csv} containing every
    fetched row, with empty fit-score columns and no LLM calls."""
    monkeypatch.chdir(tmp_path)
    _write_minimal_toml(tmp_path / "jobapply.toml")

    fetched = [_raw("a1"), _raw("b2", title="Senior MLE", company="Globex")]
    monkeypatch.setattr(cli_module, "search_jobs", lambda inp: fetched)

    # If scoring leaks into the fetch-only path, fail loudly.
    def _no_score(*_a: Any, **_kw: Any) -> FitScore:
        raise AssertionError("score_fit should not be called without --score")

    monkeypatch.setattr(cli_module, "score_fit", _no_score)

    result = CliRunner().invoke(
        app,
        ["search", "--titles", "ML Engineer", "--yes"],
    )
    assert result.exit_code == 0, result.output

    search_dirs = sorted((tmp_path / "output").glob("search-*"))
    assert len(search_dirs) == 1
    run_dir = search_dirs[0]

    jobs_path = run_dir / "jobs.json"
    csv_path = run_dir / "jobs.csv"
    meta_path = run_dir / "meta.json"
    assert jobs_path.is_file()
    assert csv_path.is_file()
    assert meta_path.is_file()

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert len(rows) == 2
    job_ids = {r["job_id"] for r in rows}
    assert job_ids == {"a1", "b2"}
    # No scoring → no score, no rationale.
    assert all(r["fit_score"] == "" for r in rows)
    assert all(r["fit_rationale"] == "" for r in rows)
    # The CSV must always carry the job link so users can click through.
    assert all(r["url"].startswith("https://example.com/") for r in rows)

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["scored"] is False
    assert meta["fetched"] == 2
    assert meta["provider"] == ""
    assert meta["model"] == ""


def test_search_no_jobs_still_writes_empty_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty fetch shouldn't crash — we still write a header-only CSV."""
    monkeypatch.chdir(tmp_path)
    _write_minimal_toml(tmp_path / "jobapply.toml")

    monkeypatch.setattr(cli_module, "search_jobs", lambda inp: [])
    result = CliRunner().invoke(
        app, ["search", "--titles", "Nonexistent Role", "--yes"]
    )
    assert result.exit_code == 0, result.output

    csv_path = next((tmp_path / "output").glob("search-*/jobs.csv"))
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert rows == []


def test_search_warns_when_provider_passed_without_score(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bare --provider/--model without --score is a no-op — surface that."""
    monkeypatch.chdir(tmp_path)
    _write_minimal_toml(tmp_path / "jobapply.toml")
    monkeypatch.setattr(cli_module, "search_jobs", lambda inp: [_raw("a1")])

    result = CliRunner().invoke(
        app,
        ["search", "--titles", "X", "--provider", "openai", "--yes"],
    )
    assert result.exit_code == 0, result.output
    assert "ignored without --score" in result.output


# ---------------------------------------------------------------------------
# CLI: scoring path
# ---------------------------------------------------------------------------


def test_search_with_score_attaches_fit_and_skips_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--score should call score_fit per job and tolerate per-job failures
    (the failing row lands with status=pending + an error message but
    the rest of the batch still completes)."""
    monkeypatch.chdir(tmp_path)
    _write_minimal_toml(tmp_path / "jobapply.toml")
    _write_minimal_profile(tmp_path / "profile.json")

    jobs = [_raw("a1"), _raw("b2"), _raw("c3", title="Lead MLE")]
    monkeypatch.setattr(cli_module, "search_jobs", lambda inp: jobs)

    # Stub create_chat_model so we never touch the network. The scorer
    # only cares that the object isn't None — `score_fit` is stubbed
    # below to ignore it entirely.
    monkeypatch.setattr(cli_module, "create_chat_model", lambda *a, **kw: object())

    score_calls: list[str] = []

    def _fake_score(_llm: Any, *, profile_text: str, job: RawJob, skills: list[str]) -> FitScore:
        score_calls.append(job.job_id)
        if job.job_id == "b2":
            raise RuntimeError("kaboom")
        return FitScore(
            score=0.9 if job.job_id == "a1" else 0.4,
            rationale=f"scored {job.job_id}",
            missing_keywords=[],
        )

    monkeypatch.setattr(cli_module, "score_fit", _fake_score)

    result = CliRunner().invoke(
        app,
        ["search", "--titles", "ML Engineer", "--score", "--yes"],
    )
    assert result.exit_code == 0, result.output
    assert score_calls == ["a1", "b2", "c3"]

    csv_path = next((tmp_path / "output").glob("search-*/jobs.csv"))
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert len(rows) == 3

    by_id = {r["job_id"]: r for r in rows}
    assert by_id["a1"]["fit_score"] == "0.900"
    assert by_id["c3"]["fit_score"] == "0.400"
    # The failed score gets recorded so the user can see what went
    # wrong without losing the rest of the batch.
    assert by_id["b2"]["fit_score"] == ""
    assert "kaboom" in by_id["b2"]["error"]


def test_search_with_score_requires_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--score without a profile.json should exit non-zero with a helpful
    message — we deliberately don't fall back to defaults because the
    fit scorer would silently produce garbage."""
    monkeypatch.chdir(tmp_path)
    _write_minimal_toml(tmp_path / "jobapply.toml")
    # NO profile.json on disk.
    monkeypatch.setattr(cli_module, "search_jobs", lambda inp: [_raw("a1")])
    monkeypatch.setattr(cli_module, "create_chat_model", lambda *a, **kw: object())
    monkeypatch.setattr(cli_module, "score_fit", lambda *a, **kw: FitScore(score=0.5))

    result = CliRunner().invoke(
        app,
        ["search", "--titles", "X", "--score", "--yes"],
    )
    assert result.exit_code != 0
    # No CSV should be written when we bail out before scoring.
    assert not list((tmp_path / "output").glob("search-*/jobs.csv"))


def test_search_uses_explicit_provider_and_model_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--provider / --model from the CLI should be plumbed into both the
    LLM factory and the meta.json snapshot."""
    monkeypatch.chdir(tmp_path)
    _write_minimal_toml(tmp_path / "jobapply.toml", provider="openai")
    _write_minimal_profile(tmp_path / "profile.json")
    monkeypatch.setattr(cli_module, "search_jobs", lambda inp: [_raw("a1")])

    captured: dict[str, Any] = {}

    def _fake_factory(provider: str, model: str, cfg: Any) -> object:
        captured["provider"] = provider
        captured["model"] = model
        return object()

    monkeypatch.setattr(cli_module, "create_chat_model", _fake_factory)
    monkeypatch.setattr(
        cli_module,
        "score_fit",
        lambda *a, **kw: FitScore(score=0.5, rationale="ok"),
    )

    result = CliRunner().invoke(
        app,
        [
            "search",
            "--titles", "X",
            "--score",
            "--provider", "anthropic",
            "--model", "claude-3-5-sonnet",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured == {"provider": "anthropic", "model": "claude-3-5-sonnet"}

    meta = json.loads(next((tmp_path / "output").glob("search-*/meta.json")).read_text())
    assert meta["provider"] == "anthropic"
    assert meta["model"] == "claude-3-5-sonnet"
    assert meta["scored"] is True
