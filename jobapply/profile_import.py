"""Convert an existing resume into a `profile.md` the rest of the CLI can read.

Supports plain text formats (``.md``, ``.txt``), Word ``.docx`` files, and any
PDF (LinkedIn's "Save to PDF" export is just a normal PDF). For ``.doc`` we
ask the user to convert to ``.docx`` because the legacy binary format would
require a fragile native dependency.

When an LLM is configured for the active provider we ask it to reshape the
extracted text into the same section layout as the bundled template so the
downstream resume-tailoring agent has consistent inputs. Without an API key
we fall back to writing the raw text under a generated header.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from jobapply.config import AppConfig, get_api_key

if TYPE_CHECKING:  # pragma: no cover - import for type hints only
    from langchain_core.language_models.chat_models import BaseChatModel

SUPPORTED_SUFFIXES: tuple[str, ...] = (".md", ".txt", ".docx", ".pdf")


class ResumeImportError(RuntimeError):
    """Raised when a resume file can't be read or converted."""


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover - dependency declared in pyproject
        raise ResumeImportError(
            "python-docx is required to read .docx files. "
            "Run `pip install python-docx` or reinstall the package.",
        ) from exc

    doc = Document(str(path))
    parts: list[str] = []
    for para in doc.paragraphs:
        text = (para.text or "").strip()
        if text:
            parts.append(text)
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts).strip()


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency declared in pyproject
        raise ResumeImportError(
            "pypdf is required to read PDF files. "
            "Run `pip install pypdf` or reinstall the package.",
        ) from exc

    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # pragma: no cover - rare malformed PDFs
            text = ""
        text = text.strip()
        if text:
            pages.append(text)
    return "\n\n".join(pages).strip()


def extract_text_from_resume(path: Path) -> str:
    """Return raw text for ``path`` based on its extension."""
    if not path.is_file():
        raise ResumeImportError(f"No such file: {path}")
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return _read_text_file(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".doc":
        raise ResumeImportError(
            "Legacy .doc isn't supported. Open the file and re-save as .docx, then retry.",
        )
    raise ResumeImportError(
        f"Unsupported resume format '{suffix}'. " f"Use one of: {', '.join(SUPPORTED_SUFFIXES)}.",
    )


_PROFILE_TEMPLATE = """# Base profile (starter resume source)

## Header
- **Name:**
- **Email:**
- **Phone:**
- **Location:**
- **Links:**

## Summary

## Skills (grouped)
- **Languages:**
- **Frameworks:**
- **Cloud / Infra:**

## Experience

### Company | Role | Start - End
- bullet

## Projects
- **Project:** description

## Education
- **School**, Degree, years
"""


_SYSTEM_PROMPT = (
    "You convert a candidate's existing resume into a clean Markdown profile "
    "used as the source of truth for downstream resume tailoring. "
    "Preserve every fact: do not invent employers, dates, metrics, schools, "
    "or skills. Drop boilerplate, recruiter notes, and page numbers. "
    "Output ONLY the Markdown document, no commentary or code fences. "
    "Follow this exact section layout (omit a section only if the source has "
    "absolutely no signal for it):\n\n"
    f"{_PROFILE_TEMPLATE}"
)


def llm_rewrite_to_profile_md(llm: BaseChatModel, raw_text: str) -> str:
    """Ask the LLM to reformat ``raw_text`` into a profile.md document."""
    user = HumanMessage(content=f"RESUME SOURCE TEXT:\n\n{raw_text[:30000]}")
    response = llm.invoke([SystemMessage(content=_SYSTEM_PROMPT), user])
    content = response.content
    if isinstance(content, list):  # some providers return list-of-parts
        content = "".join(part if isinstance(part, str) else str(part) for part in content)
    text = str(content).strip()
    if text.startswith("```"):
        # Strip a stray ```markdown ... ``` fence if the model adds one.
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if not text.endswith("\n"):
        text += "\n"
    return text


def _fallback_profile_md(source_path: Path, raw_text: str) -> str:
    """Produce a usable profile.md without an LLM by embedding the raw text."""
    body = raw_text.strip() or "(empty resume)"
    return (
        "# Base profile (starter resume source)\n\n"
        f"_Imported from `{source_path.name}` — no LLM key was configured, so the "
        "raw text is included verbatim. Edit the sections below before running "
        "`jobapply run`._\n\n"
        "## Raw resume text\n\n"
        f"{body}\n"
    )


def import_resume_to_profile_md(
    resume_path: Path,
    cfg: AppConfig,
    *,
    llm_factory: Callable[[AppConfig, str, str], BaseChatModel] | None = None,
) -> str:
    """Convert ``resume_path`` to profile.md text, using the configured LLM when possible.

    ``llm_factory`` is injectable for testing. Default: build via ``create_chat_model``.
    """
    raw_text = extract_text_from_resume(resume_path)
    if not raw_text.strip():
        raise ResumeImportError(
            f"Could not extract any text from {resume_path}. "
            "If it's a scanned PDF, try a Markdown or DOCX export instead.",
        )

    provider = cfg.provider
    if provider == "ollama" or get_api_key(cfg, provider):
        if llm_factory is None:
            from jobapply.llm import create_chat_model

            def _default_factory(c: AppConfig, p: str, m: str) -> BaseChatModel:
                return create_chat_model(p, m, cfg=c)

            llm_factory = _default_factory
        model = cfg.resolved_model(provider)
        try:
            llm = llm_factory(cfg, provider, model)
            return llm_rewrite_to_profile_md(llm, raw_text)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            raise ResumeImportError(
                f"LLM rewrite failed ({type(exc).__name__}: {exc}). "
                "Re-run `jobapply init` with the resume path once your provider is reachable, "
                "or skip the import and edit profile.md by hand.",
            ) from exc

    return _fallback_profile_md(resume_path, raw_text)
