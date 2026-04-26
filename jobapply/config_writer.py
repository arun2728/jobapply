"""Render `jobapply.toml` from an :class:`AppConfig` with helpful comments.

We hand-roll a tiny TOML emitter so the file stays human-friendly (sections,
comments, default placeholders) instead of using a one-shot dumper that drops
context.  The output is a strict subset of TOML that ``tomllib`` can re-read.
"""

from __future__ import annotations

from typing import Any

from jobapply.config import (
    DEFAULT_BASE_URLS,
    DEFAULT_MODELS,
    PROVIDER_NAMES,
    AppConfig,
    ProviderConfig,
)


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_bool(b: bool) -> str:
    return "true" if b else "false"


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return _toml_bool(v)
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    return _toml_str(str(v))


def _kv(key: str, value: Any) -> str:
    return f"{key} = {_toml_value(value)}\n"


def _provider_block(name: str, pc: ProviderConfig) -> str:
    lines: list[str] = [f"\n[providers.{name}]\n"]
    default_model = DEFAULT_MODELS.get(name, "")
    default_base = DEFAULT_BASE_URLS.get(name)

    if name == "ollama":
        lines.append("# Ollama is local; api_key usually empty. Adjust base_url if remote.\n")
    else:
        lines.append(
            '# Tip: use api_key = "env:VAR_NAME" to pull the value from an env var\n'
            "# at runtime instead of storing the secret in this file.\n",
        )

    if pc.api_key is not None:
        lines.append(_kv("api_key", pc.api_key))
    else:
        placeholder = "" if name == "ollama" else "REPLACE_ME"
        lines.append(f'# api_key = "{placeholder}"\n')

    if pc.base_url is not None:
        lines.append(_kv("base_url", pc.base_url))
    elif default_base:
        lines.append(f'# base_url = "{default_base}"\n')

    model = pc.model or default_model
    if model:
        lines.append(_kv("model", model))
    return "".join(lines)


def render_config_toml(cfg: AppConfig) -> str:
    """Serialize an :class:`AppConfig` back to a commented TOML document."""
    out: list[str] = [
        "# jobapply configuration. Provider keys may live here or in env vars.\n",
        "# Add `jobapply.toml` to .gitignore if you store secrets in this file.\n\n",
        _kv("provider", cfg.provider),
    ]
    if cfg.model:
        out.append(_kv("model", cfg.model))
    out.append(_kv("min_fit", cfg.min_fit))
    out.append(_kv("results_wanted", cfg.results_wanted))
    out.append(_kv("hours_old", cfg.hours_old))
    out.append(_kv("concurrency", cfg.concurrency))
    out.append(_kv("sites", cfg.sites))
    out.append(_kv("profile_path", cfg.profile_path))
    out.append(_kv("output_dir", cfg.output_dir))
    if cfg.ledger_path:
        out.append(_kv("ledger_path", cfg.ledger_path))

    for name in PROVIDER_NAMES:
        pc = cfg.providers.get(name, ProviderConfig())
        out.append(_provider_block(name, pc))
    return "".join(out)
