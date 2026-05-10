"""End-to-end tests for the FastAPI web UI server.

Exercises the public ``/api`` surface with the search agent, LLMs, and
PDF backends fully stubbed so the suite stays fast, hermetic, and
network-free. We use ``TestClient`` (Starlette's in-process client)
plus a tiny ``_wait_for_task`` helper that polls ``/api/tasks/{id}``
the same way the React frontend does in production.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jobapply.models import (
    CoverLetter,
    EducationItem,
    EmailDraft,
    ExperienceRole,
    RawJob,
    TailoredResume,
)
from jobapply.profile import save_profile, Profile, ProfileExperience
from jobapply.server import create_app
from jobapply.tasks import TaskManager


def _write_minimal_toml(path: Path) -> None:
    """Drop a ``jobapply.toml`` with a stub provider/model so the
    ``_resolve_provider_model`` guard passes in the API."""
    path.write_text(
        'provider = "openai"\n'
        'profile_path = "profile.json"\n'
        'output_dir = "output"\n'
        "results_wanted = 5\n"
        "hours_old = 24\n"
        'sites = ["indeed"]\n'
        '[providers.openai]\n'
        'api_key = "test-key"\n'
        'model = "test-model"\n',
        encoding="utf-8",
    )


def _write_minimal_profile(path: Path) -> None:
    """Save a tiny but complete profile so /api/profile reports
    ``loaded`` and the tailor handler has real text to work with."""
    profile = Profile(
        name="Test Candidate",
        email="test@example.com",
        location="Remote",
        summary="Builds reliable systems.",
        skills=["Python", "Kubernetes"],
        experience=[
            ProfileExperience(
                company="Acme",
                role="Senior Engineer",
                start_date="Jan 2022",
                end_date="Present",
                bullets=["Shipped X.", "Improved Y."],
            )
        ],
    )
    save_profile(profile, path)


def _stub_raw(jid: str, *, title: str = "ML Engineer") -> RawJob:
    return RawJob(
        job_id=jid,
        title=title,
        company="Acme",
        location="Remote",
        description=(
            "Senior ML role. We need Python, ML platforms, and a track "
            "record of shipping production systems."
        ),
        job_url=f"https://example.com/jobs/{jid}",
        apply_url=f"https://example.com/apply/{jid}",
        site="indeed",
    )


def _stub_tailored_resume() -> TailoredResume:
    return TailoredResume(
        document_title="Test Candidate",
        contact_line="test@example.com",
        summary="Tailored summary.",
        skills=["Python", "Kubernetes"],
        experience=[
            ExperienceRole(
                company="Acme",
                role="Senior Engineer",
                dates="2022 – Present",
                bullets=["Shipped X.", "Improved Y."],
            )
        ],
        education=[EducationItem(school="MIT", degree="MEng")],
    )


def _stub_cover_letter() -> CoverLetter:
    return CoverLetter(
        header="Test Candidate\ntest@example.com",
        opening="Dear Hiring Manager,",
        body="I'd love to bring my Python and ML platform experience to your team.",
        closing="Sincerely,\nTest Candidate",
    )


def _wait_for_task(
    client: TestClient, task_id: str, *, timeout: float = 5.0
) -> dict[str, Any]:
    """Poll the task endpoint until the task settles or we time out.

    The server runs tasks on background threads, so even with stubbed
    agents we may need a few hundred ms before the result lands. We
    fail loudly on timeout so a regression doesn't quietly turn into
    an indefinite hang.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["status"] in {"succeeded", "failed", "cancelled"}:
            return body
        time.sleep(0.05)
    raise AssertionError(f"Task {task_id} did not settle within {timeout}s")


@pytest.fixture
def app_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Build a fresh FastAPI app rooted at ``tmp_path``.

    Every test gets its own workspace directory + jobapply.toml +
    profile.json so they can run in parallel without colliding on
    SQLite handles.
    """

    def _make() -> tuple[TestClient, Path, TaskManager]:
        monkeypatch.chdir(tmp_path)
        _write_minimal_toml(tmp_path / "jobapply.toml")
        _write_minimal_profile(tmp_path / "profile.json")
        # Clean LLM API env vars so create_chat_model never tries to
        # reach the real provider during the (rare) paths we don't
        # stub. Tests that need an LLM patch the agent functions
        # directly so create_chat_model is never called for real.
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        manager = TaskManager()
        client = TestClient(
            create_app(
                cwd=tmp_path,
                workspace_path=tmp_path / "ws",
                task_manager=manager,
            )
        )
        return client, tmp_path, manager

    return _make


def test_status_reports_workspace_and_profile(app_factory: Any) -> None:
    client, tmp_path, _ = app_factory()
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile_loaded"] is True
    assert body["profile_name"] == "Test Candidate"
    assert body["workspace_total_jobs"] == 0
    assert body["workspace"].endswith("/ws")
    assert body["provider"] == "openai"


def test_providers_endpoint_lists_known_providers(app_factory: Any) -> None:
    """``/api/providers`` should expose every supported provider plus
    flags for the picker UI (``configured`` and ``has_credentials``).
    The test toml only has an ``openai`` block, so other providers
    must come back as ``configured=False`` while still appearing in
    the list."""
    client, *_ = app_factory()
    body = client.get("/api/providers").json()
    assert body["active_provider"] == "openai"
    assert body["active_model"] == "test-model"
    names = {p["name"] for p in body["providers"]}
    # Every canonical provider in PROVIDER_NAMES must be reachable
    # so the dropdown is consistent across installs.
    assert {"openai", "gemini", "anthropic", "ollama"}.issubset(names)
    openai = next(p for p in body["providers"] if p["name"] == "openai")
    assert openai["configured"] is True
    assert openai["has_credentials"] is True
    assert openai["default_model"] == "test-model"
    gemini = next(p for p in body["providers"] if p["name"] == "gemini")
    assert gemini["configured"] is False
    # gemini default model comes from DEFAULT_MODELS rather than the toml
    assert gemini["default_model"]


def test_jobs_list_starts_empty(app_factory: Any) -> None:
    client, *_ = app_factory()
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["jobs"] == []


def test_get_job_404_for_unknown(app_factory: Any) -> None:
    client, *_ = app_factory()
    resp = client.get("/api/jobs/missing-job-id")
    assert resp.status_code == 404


def test_search_endpoint_populates_workspace(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/search should run the (stubbed) search agent and
    persist the results into the workspace catalog."""
    client, tmp_path, _ = app_factory()

    # The server module imports iter_search_jobs at module load time;
    # patch the bound symbol so the handler picks our stub up.
    from jobapply import server as srv

    monkeypatch.setattr(
        srv,
        "iter_search_jobs",
        lambda inp: iter([_stub_raw("a1"), _stub_raw("b2", title="Backend")]),
    )

    resp = client.post(
        "/api/search",
        json={"titles": ["ML Engineer"], "skills": ["Python"]},
    )
    assert resp.status_code == 200, resp.text
    task = resp.json()
    final = _wait_for_task(client, task["task_id"])
    assert final["status"] == "succeeded", final
    assert final["result"]["new_jobs"] == 2
    assert final["result"]["duplicate_jobs"] == 0

    # Catalog now has both jobs and the per-job folders exist.
    listing = client.get("/api/jobs").json()
    assert listing["total"] == 2
    titles = {j["title"] for j in listing["jobs"]}
    assert titles == {"ML Engineer", "Backend"}
    assert (tmp_path / "ws" / "jobs.json").is_file()
    assert (tmp_path / "ws" / "jobs.csv").is_file()


def test_search_endpoint_dedupes_on_second_call(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second search returning the same job_id should be reported
    as a duplicate and not double-counted in the catalog."""
    client, *_ = app_factory()
    from jobapply import server as srv

    monkeypatch.setattr(
        srv, "iter_search_jobs", lambda inp: iter([_stub_raw("a1")])
    )
    first = client.post("/api/search", json={"titles": ["X"]}).json()
    _wait_for_task(client, first["task_id"])

    monkeypatch.setattr(
        srv, "iter_search_jobs", lambda inp: iter([_stub_raw("a1")])
    )
    second = client.post("/api/search", json={"titles": ["X"]}).json()
    final = _wait_for_task(client, second["task_id"])
    assert final["result"]["new_jobs"] == 0
    assert final["result"]["duplicate_jobs"] == 1
    assert client.get("/api/jobs").json()["total"] == 1


def test_freeform_endpoint_creates_tailored_job(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/freeform should add a synthetic job + run the tailor
    pipeline (with stubs) and the resulting JobRecord should expose
    the tailored resume / cover letter to the UI."""
    client, tmp_path, _ = app_factory()

    from jobapply import server as srv

    monkeypatch.setattr(
        srv, "create_chat_model", lambda *a, **kw: object()
    )
    # `tailor_for_job_description` is the heavy entry point — easier
    # to stub the whole thing than to mock six different agents.
    captured: dict[str, Any] = {}

    def _fake_tailor(llm: Any, **kwargs: Any) -> Any:
        from jobapply.tailor_one import TailorOutputs

        output_root = Path(kwargs["output_root"])
        # Mirror the real layout: read the persisted job.json so we
        # can derive the slug/job folder it lives in.
        jd_path = Path(kwargs["jd_path"])
        captured["jd_path"] = jd_path
        captured["output_root"] = output_root
        job_json = json.loads(jd_path.read_text(encoding="utf-8"))
        job = RawJob(
            job_id=job_json["job_id"],
            title=job_json.get("title") or "Tailored",
            company=job_json.get("company") or "Acme",
            location=job_json.get("location") or "",
            description=job_json.get("description") or "",
            site="freeform",
        )
        # The tailor function writes resume.md/.tex/cover_letter.* into
        # the per-job dir; we replicate the minimum the JobRecord cares
        # about.
        job_dir = jd_path.parent
        (job_dir / "resume.md").write_text("# Resume\n", encoding="utf-8")
        (job_dir / "resume.tex").write_text("% resume tex", encoding="utf-8")
        (job_dir / "cover_letter.md").write_text(
            "# Cover\n", encoding="utf-8"
        )
        (job_dir / "cover_letter.tex").write_text(
            "% cover tex", encoding="utf-8"
        )
        return TailorOutputs(
            job_dir=job_dir,
            job=job,
            resume=_stub_tailored_resume(),
            cover=_stub_cover_letter(),
            email=None,
            resume_md=job_dir / "resume.md",
            resume_tex=job_dir / "resume.tex",
            cover_md=job_dir / "cover_letter.md",
            cover_tex=job_dir / "cover_letter.tex",
        )

    monkeypatch.setattr(srv, "tailor_for_job_description", _fake_tailor)

    payload = {
        "description": (
            "We are hiring a Backend Engineer. Python, Postgres, "
            "Kubernetes. Send your CV to recruiter@acme.com."
        ),
        "title": "Backend Engineer",
        "company": "Acme",
        "no_pdf": True,
    }
    resp = client.post("/api/freeform", json=payload)
    assert resp.status_code == 200, resp.text
    task = resp.json()
    final = _wait_for_task(client, task["task_id"])
    assert final["status"] == "succeeded", final
    job_id = final["result"]["job"]["job_id"]

    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["status"] == "done"
    assert detail["tailored_resume"] is not None
    assert detail["cover_letter"] is not None
    # The tailor stub was actually invoked and wrote artifacts.
    assert "resume.md" in (detail["available_artifacts"] or {})
    # And the auto-detected recipient surfaces to the UI's email
    # modal.
    hints = client.get(f"/api/jobs/{job_id}/email-hint").json()
    assert hints["primary_email"] == "recruiter@acme.com"


def test_tailor_one_endpoint_runs_pipeline(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/jobs/<id>/tailor should run the same stubbed pipeline
    against an already-cataloged job and update its status to ``done``."""
    client, tmp_path, _ = app_factory()
    from jobapply import server as srv

    # Seed the workspace with a single pending job via the search
    # endpoint (using the search stub) so we don't have to touch the
    # workspace internals from the test.
    monkeypatch.setattr(
        srv, "iter_search_jobs", lambda inp: iter([_stub_raw("a1")])
    )
    seed = client.post("/api/search", json={"titles": ["X"]}).json()
    _wait_for_task(client, seed["task_id"])
    assert client.get("/api/jobs").json()["total"] == 1

    monkeypatch.setattr(srv, "create_chat_model", lambda *a, **kw: object())

    def _fake_tailor(llm: Any, **kwargs: Any) -> Any:
        from jobapply.tailor_one import TailorOutputs

        jd_path = Path(kwargs["jd_path"])
        job_dir = jd_path.parent
        (job_dir / "resume.md").write_text("R", encoding="utf-8")
        (job_dir / "resume.tex").write_text("R", encoding="utf-8")
        (job_dir / "cover_letter.md").write_text("C", encoding="utf-8")
        (job_dir / "cover_letter.tex").write_text("C", encoding="utf-8")
        return TailorOutputs(
            job_dir=job_dir,
            job=_stub_raw("a1"),
            resume=_stub_tailored_resume(),
            cover=_stub_cover_letter(),
            email=None,
            resume_md=job_dir / "resume.md",
            resume_tex=job_dir / "resume.tex",
            cover_md=job_dir / "cover_letter.md",
            cover_tex=job_dir / "cover_letter.tex",
        )

    monkeypatch.setattr(srv, "tailor_for_job_description", _fake_tailor)

    resp = client.post("/api/jobs/a1/tailor", json={"no_pdf": True})
    assert resp.status_code == 200, resp.text
    final = _wait_for_task(client, resp.json()["task_id"])
    assert final["status"] == "succeeded", final

    detail = client.get("/api/jobs/a1").json()
    assert detail["status"] == "done"
    assert detail["tailored_resume"]["document_title"] == "Test Candidate"


def test_tailor_one_returns_400_when_description_empty(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tailor endpoint should refuse jobs whose description we
    couldn't recover, with a friendly hint pointing at the freeform
    paste route."""
    client, tmp_path, _ = app_factory()
    from jobapply import server as srv

    empty = _stub_raw("e1")
    empty.description = ""
    monkeypatch.setattr(srv, "iter_search_jobs", lambda inp: iter([empty]))
    seed = client.post("/api/search", json={"titles": ["X"]}).json()
    _wait_for_task(client, seed["task_id"])

    resp = client.post("/api/jobs/e1/tailor", json={})
    assert resp.status_code == 400
    assert "description" in resp.json()["detail"].lower()


def test_email_endpoint_drafts_after_tailor(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/jobs/<id>/email should refuse to draft until the job
    has been tailored, then succeed once tailor results exist."""
    client, *_ = app_factory()
    from jobapply import server as srv

    monkeypatch.setattr(
        srv, "iter_search_jobs", lambda inp: iter([_stub_raw("a1")])
    )
    seed = client.post("/api/search", json={"titles": ["X"]}).json()
    _wait_for_task(client, seed["task_id"])

    too_early = client.post(
        "/api/jobs/a1/email", json={"recipient": "rec@example.com"}
    )
    assert too_early.status_code == 400

    monkeypatch.setattr(srv, "create_chat_model", lambda *a, **kw: object())

    def _fake_tailor(llm: Any, **kwargs: Any) -> Any:
        from jobapply.tailor_one import TailorOutputs

        jd_path = Path(kwargs["jd_path"])
        job_dir = jd_path.parent
        for name in (
            "resume.md",
            "resume.tex",
            "cover_letter.md",
            "cover_letter.tex",
        ):
            (job_dir / name).write_text("X", encoding="utf-8")
        return TailorOutputs(
            job_dir=job_dir,
            job=_stub_raw("a1"),
            resume=_stub_tailored_resume(),
            cover=_stub_cover_letter(),
            email=None,
            resume_md=job_dir / "resume.md",
            resume_tex=job_dir / "resume.tex",
            cover_md=job_dir / "cover_letter.md",
            cover_tex=job_dir / "cover_letter.tex",
        )

    monkeypatch.setattr(srv, "tailor_for_job_description", _fake_tailor)
    tailor_resp = client.post("/api/jobs/a1/tailor", json={"no_pdf": True})
    _wait_for_task(client, tailor_resp.json()["task_id"])

    monkeypatch.setattr(
        srv,
        "draft_application_email",
        lambda llm, **kw: EmailDraft(
            to=kw["recipient_email"],
            subject="Application — ML Engineer",
            body="Hi! Attached is my resume.",
        ),
    )

    resp = client.post(
        "/api/jobs/a1/email", json={"recipient": "rec@example.com"}
    )
    assert resp.status_code == 200, resp.text
    final = _wait_for_task(client, resp.json()["task_id"])
    assert final["status"] == "succeeded", final
    assert final["result"]["to"] == "rec@example.com"
    assert "ML Engineer" in final["result"]["subject"]


def test_delete_job_removes_from_catalog(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, *_ = app_factory()
    from jobapply import server as srv

    monkeypatch.setattr(
        srv, "iter_search_jobs", lambda inp: iter([_stub_raw("a1")])
    )
    seed = client.post("/api/search", json={"titles": ["X"]}).json()
    _wait_for_task(client, seed["task_id"])
    assert client.get("/api/jobs").json()["total"] == 1

    resp = client.delete("/api/jobs/a1")
    assert resp.status_code == 200
    assert resp.json()["workspace_total_jobs"] == 0
    assert client.get("/api/jobs").json()["total"] == 0
    assert client.get("/api/jobs/a1").status_code == 404


def test_searches_history_records_each_run(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, *_ = app_factory()
    from jobapply import server as srv

    monkeypatch.setattr(
        srv, "iter_search_jobs", lambda inp: iter([_stub_raw("a1")])
    )
    a = client.post("/api/search", json={"titles": ["A"]}).json()
    _wait_for_task(client, a["task_id"])
    monkeypatch.setattr(
        srv, "iter_search_jobs", lambda inp: iter([_stub_raw("b2")])
    )
    b = client.post("/api/search", json={"titles": ["B"]}).json()
    _wait_for_task(client, b["task_id"])

    body = client.get("/api/searches").json()
    assert len(body["searches"]) == 2
    cmds = {row["command"] for row in body["searches"]}
    assert cmds == {"search"}


def test_artifact_endpoint_serves_resume_md(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After tailoring, /api/jobs/<id>/artifacts/resume.md should
    return the file the pipeline wrote."""
    client, *_ = app_factory()
    from jobapply import server as srv

    monkeypatch.setattr(
        srv, "iter_search_jobs", lambda inp: iter([_stub_raw("a1")])
    )
    seed = client.post("/api/search", json={"titles": ["X"]}).json()
    _wait_for_task(client, seed["task_id"])

    monkeypatch.setattr(srv, "create_chat_model", lambda *a, **kw: object())

    def _fake_tailor(llm: Any, **kwargs: Any) -> Any:
        from jobapply.tailor_one import TailorOutputs

        jd_path = Path(kwargs["jd_path"])
        job_dir = jd_path.parent
        (job_dir / "resume.md").write_text(
            "# Tailored resume body\n", encoding="utf-8"
        )
        (job_dir / "resume.tex").write_text("R", encoding="utf-8")
        (job_dir / "cover_letter.md").write_text("C", encoding="utf-8")
        (job_dir / "cover_letter.tex").write_text("C", encoding="utf-8")
        return TailorOutputs(
            job_dir=job_dir,
            job=_stub_raw("a1"),
            resume=_stub_tailored_resume(),
            cover=_stub_cover_letter(),
            email=None,
            resume_md=job_dir / "resume.md",
            resume_tex=job_dir / "resume.tex",
            cover_md=job_dir / "cover_letter.md",
            cover_tex=job_dir / "cover_letter.tex",
        )

    monkeypatch.setattr(srv, "tailor_for_job_description", _fake_tailor)
    tailor_resp = client.post("/api/jobs/a1/tailor", json={"no_pdf": True})
    _wait_for_task(client, tailor_resp.json()["task_id"])

    md = client.get("/api/jobs/a1/artifacts/resume.md")
    assert md.status_code == 200
    assert "Tailored resume body" in md.text


def test_artifact_endpoint_rejects_path_traversal(
    app_factory: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, *_ = app_factory()
    from jobapply import server as srv

    monkeypatch.setattr(
        srv, "iter_search_jobs", lambda inp: iter([_stub_raw("a1")])
    )
    seed = client.post("/api/search", json={"titles": ["X"]}).json()
    _wait_for_task(client, seed["task_id"])

    forbidden = client.get("/api/jobs/a1/artifacts/..%2Fworkspace.db")
    # The ASGI router rejects ``..`` segments before the handler runs;
    # either way the user must not get a 200.
    assert forbidden.status_code in {400, 404}
    not_allowed = client.get("/api/jobs/a1/artifacts/secret.txt")
    assert not_allowed.status_code == 404
