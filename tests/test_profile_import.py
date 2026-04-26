"""Tests for the resume → profile.json importer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from jobapply.config import AppConfig, ProviderConfig
from jobapply.profile import Profile
from jobapply.profile_import import (
    ResumeImportError,
    extract_profile_from_resume,
    extract_profile_from_text,
    extract_text_from_resume,
)

# ---- Raw text extraction -------------------------------------------------- #


def test_extract_text_from_md(tmp_path: Path) -> None:
    p = tmp_path / "resume.md"
    p.write_text("# Hi\n\nI work in Python.\n", encoding="utf-8")
    text = extract_text_from_resume(p)
    assert "Python" in text


def test_extract_text_from_txt(tmp_path: Path) -> None:
    p = tmp_path / "resume.txt"
    p.write_text("Plain text resume.", encoding="utf-8")
    assert extract_text_from_resume(p) == "Plain text resume."


def test_extract_text_doc_rejected(tmp_path: Path) -> None:
    p = tmp_path / "resume.doc"
    p.write_bytes(b"fake")
    with pytest.raises(ResumeImportError, match="Legacy .doc"):
        extract_text_from_resume(p)


def test_extract_text_unknown_suffix(tmp_path: Path) -> None:
    p = tmp_path / "resume.rtf"
    p.write_text("nope", encoding="utf-8")
    with pytest.raises(ResumeImportError, match="Unsupported"):
        extract_text_from_resume(p)


def test_extract_text_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ResumeImportError, match="No such file"):
        extract_text_from_resume(tmp_path / "missing.md")


# ---- Structured-output extraction ---------------------------------------- #


class _FakeStructured:
    def __init__(self, out: Profile) -> None:
        self._out = out

    def invoke(self, _msgs: Any) -> Profile:
        return self._out


class _FakeLLM:
    """LLM stub that returns a canned ``Profile`` on ``with_structured_output``.

    Captures the schema it was asked for so we can assert the importer is
    calling structured output instead of a free-form completion.
    """

    def __init__(self, out: Profile) -> None:
        self._out = out
        self.structured_schemas: list[type[Any]] = []

    def with_structured_output(self, schema: type[Any]) -> _FakeStructured:
        self.structured_schemas.append(schema)
        return _FakeStructured(self._out)


def _profile() -> Profile:
    return Profile(
        name="Alice Engineer",
        email="alice@example.com",
        skills=["Python", "Kubernetes"],
    )


def test_extract_from_text_uses_structured_output() -> None:
    """The importer must drive ``with_structured_output(Profile)`` so the
    return value is a typed model rather than free-form Markdown."""
    cfg = AppConfig(
        provider="openai",
        providers={"openai": ProviderConfig(api_key="sk-test")},
    )
    fake = _FakeLLM(_profile())

    out = extract_profile_from_text(
        "name: Alice\nrole: SWE",
        cfg,
        llm_factory=lambda *_a, **_kw: fake,  # type: ignore[arg-type,return-value]
    )
    assert isinstance(out, Profile)
    assert out.name == "Alice Engineer"
    assert out.skills == ["Python", "Kubernetes"]
    assert fake.structured_schemas == [Profile]


def test_extract_from_resume_reads_then_calls_llm(tmp_path: Path) -> None:
    src = tmp_path / "resume.md"
    src.write_text("# Hi\n\nPython, Kubernetes.\n", encoding="utf-8")
    cfg = AppConfig(
        provider="openai",
        providers={"openai": ProviderConfig(api_key="sk-test")},
    )
    fake = _FakeLLM(_profile())

    out = extract_profile_from_resume(
        src,
        cfg,
        llm_factory=lambda *_a, **_kw: fake,  # type: ignore[arg-type,return-value]
    )
    assert out.email == "alice@example.com"


def test_extract_raises_when_no_api_key_for_remote_provider(tmp_path: Path) -> None:
    """Without a working API key (and not Ollama) we refuse to call the
    factory — there's nothing to extract with, so we tell the user how to
    fix it instead of silently writing junk."""
    src = tmp_path / "resume.md"
    src.write_text("# Hi\n\nPython.\n", encoding="utf-8")
    cfg = AppConfig(provider="gemini", providers={"gemini": ProviderConfig()})

    def factory(*_a: object, **_kw: object) -> object:
        raise AssertionError("LLM should not be invoked when no key is configured")

    with pytest.raises(ResumeImportError, match="No API key"):
        extract_profile_from_resume(src, cfg, llm_factory=factory)  # type: ignore[arg-type]


def test_extract_blank_resume_text_raises() -> None:
    cfg = AppConfig()
    with pytest.raises(ResumeImportError, match="empty"):
        extract_profile_from_text("   \n   ", cfg)


def test_extract_blank_extraction_from_file(tmp_path: Path) -> None:
    src = tmp_path / "resume.txt"
    src.write_text("   \n  \n", encoding="utf-8")
    with pytest.raises(ResumeImportError, match="any text"):
        extract_profile_from_resume(src, AppConfig())


def test_extract_wraps_llm_errors_in_resumeimporterror() -> None:
    cfg = AppConfig(
        provider="openai",
        providers={"openai": ProviderConfig(api_key="sk-test")},
    )

    class _BoomStructured:
        def invoke(self, _msgs: Any) -> Profile:
            raise RuntimeError("502 Bad Gateway")

    class _BoomLLM:
        def with_structured_output(self, _schema: type[Any]) -> _BoomStructured:
            return _BoomStructured()

    with pytest.raises(ResumeImportError, match="502 Bad Gateway"):
        extract_profile_from_text(
            "anything",
            cfg,
            llm_factory=lambda *_a, **_kw: _BoomLLM(),  # type: ignore[arg-type,return-value]
        )


def test_extract_rejects_non_profile_return() -> None:
    """A provider whose structured-output returns the wrong type must raise
    a clean :class:`ResumeImportError` instead of leaking ``AssertionError``."""
    cfg = AppConfig(
        provider="openai",
        providers={"openai": ProviderConfig(api_key="sk-test")},
    )

    class _WrongTypeStructured:
        def invoke(self, _msgs: Any) -> dict[str, Any]:
            return {"name": "Alice"}

    class _WrongTypeLLM:
        def with_structured_output(self, _schema: type[Any]) -> _WrongTypeStructured:
            return _WrongTypeStructured()

    with pytest.raises(ResumeImportError, match="expected a Profile"):
        extract_profile_from_text(
            "anything",
            cfg,
            llm_factory=lambda *_a, **_kw: _WrongTypeLLM(),  # type: ignore[arg-type,return-value]
        )
