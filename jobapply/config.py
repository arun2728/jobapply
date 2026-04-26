"""Load jobapply.toml + environment. Provider connection details live in the config."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

ProviderName = Literal["gemini", "anthropic", "openai", "ollama"]
PROVIDER_NAMES: tuple[ProviderName, ...] = ("gemini", "anthropic", "openai", "ollama")

DEFAULT_MODELS: dict[str, str] = {
    "gemini": "gemini-2.0-flash",
    "anthropic": "claude-3-5-haiku-latest",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.1",
}

DEFAULT_BASE_URLS: dict[str, str] = {
    "ollama": "http://127.0.0.1:11434",
    "openai": "https://api.openai.com/v1",
}

# Public latex-on-http instance (https://github.com/YtoTech/latex-on-http).
# Self-host via Docker if you'd rather not send résumé content to a third party.
DEFAULT_LATEX_API_URL = "https://latex.ytotech.com/builds/sync"
DEFAULT_LATEX_API_TIMEOUT = 120.0


class ProviderConfig(BaseModel):
    """Per-provider connection settings."""

    api_key: str | None = Field(None, description="Plaintext or env:VAR_NAME reference.")
    base_url: str | None = Field(None, description="Override base URL (Ollama, OpenAI-compatible).")
    model: str | None = Field(None, description="Default model id for this provider.")


class LatexApiConfig(BaseModel):
    """Settings for the LaTeX → PDF compile service.

    The pipeline POSTs ``.tex`` content to a `latex-on-http`_ compatible
    endpoint and writes the returned PDF bytes to disk. This avoids needing
    a TeX installation on the runner. Local engines (``tectonic``,
    ``pdflatex``) are still used as fallbacks when this is disabled or
    unreachable.

    .. _latex-on-http: https://github.com/YtoTech/latex-on-http
    """

    enabled: bool = Field(
        True,
        description="Try the remote LaTeX API before falling back to local engines.",
    )
    url: str = Field(
        DEFAULT_LATEX_API_URL,
        description="Compile endpoint (latex-on-http synchronous build URL).",
    )
    compiler: str = Field(
        "pdflatex",
        description="Engine the API should use: pdflatex | xelatex | lualatex | latexmk.",
    )
    timeout: float = Field(
        DEFAULT_LATEX_API_TIMEOUT,
        ge=1.0,
        description="HTTP request timeout in seconds.",
    )


class AppConfig(BaseModel):
    """Top-level config persisted in jobapply.toml."""

    provider: ProviderName = Field("gemini", description="Active provider.")
    model: str | None = Field(
        None,
        description="Override active provider's default model. Optional.",
    )
    min_fit: float = Field(0.35, ge=0.0, le=1.0)
    results_wanted: int = Field(30, ge=1, le=500)
    hours_old: int = Field(720, ge=0)
    concurrency: int = Field(1, ge=1, le=32)
    sites: list[str] = Field(default_factory=lambda: ["indeed", "linkedin", "google"])
    profile_path: str = "profile.md"
    output_dir: str = "output"
    ledger_path: str | None = None
    providers: dict[str, ProviderConfig] = Field(
        default_factory=dict,
        description="Per-provider blocks: api_key, base_url, model.",
    )
    latex_api: LatexApiConfig = Field(
        default_factory=LatexApiConfig,
        description="Remote LaTeX compile service used by `tex_to_pdf`.",
    )

    def provider_config(self, name: str | None = None) -> ProviderConfig:
        key = (name or self.provider).lower().strip()
        return self.providers.get(key, ProviderConfig())

    def resolved_model(self, name: str | None = None) -> str:
        prov = (name or self.provider).lower().strip()
        cfg = self.provider_config(prov)
        if cfg.model:
            return cfg.model
        if name is None and self.model:
            return self.model
        return DEFAULT_MODELS.get(prov, "")


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def find_config_path(cwd: Path | None = None) -> Path:
    base = cwd or Path.cwd()
    p1 = base / "jobapply.toml"
    if p1.is_file():
        return p1
    p2 = base / ".jobapply.toml"
    if p2.is_file():
        return p2
    return p1


def load_config(cwd: Path | None = None) -> AppConfig:
    """Read jobapply.toml (or .jobapply.toml) with defaults."""
    base = cwd or Path.cwd()
    data = _load_toml(base / "jobapply.toml")
    if not data:
        data = _load_toml(base / ".jobapply.toml")
    return AppConfig.model_validate(data)


def _resolve_secret(value: str | None) -> str | None:
    """Allow `env:VAR_NAME` indirection so users can keep secrets out of TOML."""
    if not value:
        return None
    if value.startswith("env:"):
        return os.environ.get(value[4:].strip()) or None
    return value


def get_api_key(cfg: AppConfig, provider: str) -> str | None:
    """Config first, then env. Supports env:VAR_NAME indirection."""
    p = provider.lower().strip()
    pc = cfg.provider_config(p)
    resolved = _resolve_secret(pc.api_key)
    if resolved:
        return resolved
    if p == "gemini":
        return os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if p == "anthropic":
        return os.environ.get("ANTHROPIC_API_KEY")
    if p == "openai":
        return os.environ.get("OPENAI_API_KEY")
    if p == "ollama":
        return os.environ.get("OLLAMA_API_KEY")
    return None


def get_base_url(cfg: AppConfig, provider: str) -> str | None:
    p = provider.lower().strip()
    pc = cfg.provider_config(p)
    if pc.base_url:
        return pc.base_url
    if p == "ollama":
        return os.environ.get("OLLAMA_BASE_URL") or DEFAULT_BASE_URLS["ollama"]
    if p == "openai":
        return os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URLS["openai"]
    return None


# Back-compat shims used elsewhere in the codebase.
def google_api_key() -> str | None:
    return os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")


def anthropic_api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY")


def openai_api_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY")


def ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", DEFAULT_BASE_URLS["ollama"])


# Env-var names consumed by `jobapply.nodes.render.tex_to_pdf`. Keeping the
# rendering layer env-only avoids a hard dependency on the config module from
# inside `nodes/`; the CLI bridges TOML config → env at startup.
LATEX_API_ENV_URL = "JOBAPPLY_LATEX_API_URL"
LATEX_API_ENV_DISABLE = "JOBAPPLY_LATEX_API_DISABLE"
LATEX_API_ENV_COMPILER = "JOBAPPLY_LATEX_API_COMPILER"
LATEX_API_ENV_TIMEOUT = "JOBAPPLY_LATEX_API_TIMEOUT"


def apply_latex_api_env(cfg: AppConfig) -> None:
    """Push ``cfg.latex_api`` values into env vars so render.py picks them up.

    Pre-existing env vars take precedence so users can override the TOML
    config from the shell without editing the file.
    """
    pairs = {
        LATEX_API_ENV_URL: cfg.latex_api.url,
        LATEX_API_ENV_DISABLE: "1" if not cfg.latex_api.enabled else "0",
        LATEX_API_ENV_COMPILER: cfg.latex_api.compiler,
        LATEX_API_ENV_TIMEOUT: str(cfg.latex_api.timeout),
    }
    for key, value in pairs.items():
        if key not in os.environ:
            os.environ[key] = value


def load_dotenv_if_present(cwd: Path | None = None) -> None:
    """Best-effort .env load without requiring python-dotenv."""
    root = cwd or Path.cwd()
    env_path = root / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v
