from __future__ import annotations

from pathlib import Path

import pytest

from jobapply.config import AppConfig, ProviderConfig
from jobapply.profile_import import (
    ResumeImportError,
    extract_text_from_resume,
    import_resume_to_profile_md,
)


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


def test_import_falls_back_when_no_api_key(tmp_path: Path) -> None:
    """No api_key configured + non-ollama provider → embed raw text, never call LLM."""
    src = tmp_path / "resume.md"
    src.write_text("# Hi\n\nPython, Kubernetes.\n", encoding="utf-8")

    cfg = AppConfig(provider="gemini", providers={"gemini": ProviderConfig()})

    def factory(*_a: object, **_kw: object) -> object:
        raise AssertionError("LLM should not be invoked when no key is configured")

    out = import_resume_to_profile_md(src, cfg, llm_factory=factory)  # type: ignore[arg-type]
    assert "Imported from `resume.md`" in out
    assert "Python, Kubernetes" in out


def test_import_uses_llm_when_key_present(tmp_path: Path) -> None:
    src = tmp_path / "resume.txt"
    src.write_text("name: Alice\nrole: SWE", encoding="utf-8")

    cfg = AppConfig(
        provider="openai",
        providers={"openai": ProviderConfig(api_key="sk-test")},
    )

    class FakeMessage:
        def __init__(self, content: str) -> None:
            self.content = content

    class FakeLLM:
        def invoke(self, _messages: object) -> FakeMessage:
            return FakeMessage("# Base profile\n\n## Header\n- **Name:** Alice\n")

    def factory(*_a: object, **_kw: object) -> FakeLLM:
        return FakeLLM()

    out = import_resume_to_profile_md(src, cfg, llm_factory=factory)  # type: ignore[arg-type]
    assert "Alice" in out
    assert out.endswith("\n")


def test_import_strips_code_fences(tmp_path: Path) -> None:
    src = tmp_path / "resume.md"
    src.write_text("anything", encoding="utf-8")
    cfg = AppConfig(
        provider="openai",
        providers={"openai": ProviderConfig(api_key="sk-test")},
    )

    class FakeMessage:
        content = "```markdown\n# Profile\n```\n"

    class FakeLLM:
        def invoke(self, _m: object) -> FakeMessage:
            return FakeMessage()

    out = import_resume_to_profile_md(
        src,
        cfg,
        llm_factory=lambda *_a, **_kw: FakeLLM(),  # type: ignore[arg-type,return-value]
    )
    assert "```" not in out
    assert "# Profile" in out


def test_import_blank_extraction(tmp_path: Path) -> None:
    src = tmp_path / "resume.txt"
    src.write_text("   \n  \n", encoding="utf-8")
    with pytest.raises(ResumeImportError, match="any text"):
        import_resume_to_profile_md(src, AppConfig())
