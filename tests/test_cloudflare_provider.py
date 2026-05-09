"""Tests for the Cloudflare Workers AI provider integration.

The provider rides on top of Workers AI's OpenAI-compatible REST endpoint
(``https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1``), so
the goal here is to verify the wiring around it: config plumbing, env-var
fallbacks, base-URL assembly, and the ``create_chat_model`` dispatch.
"""

from __future__ import annotations

import pytest

from jobapply.config import (
    CLOUDFLARE_BASE_URL_TEMPLATE,
    CLOUDFLARE_GATEWAY_BASE_URL_TEMPLATE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODELS,
    PROVIDER_NAMES,
    AppConfig,
    ProviderConfig,
    cloudflare_base_url,
    cloudflare_gateway_base_url,
    get_account_id,
    get_api_key,
    get_base_url,
    get_gateway_id,
    get_max_tokens,
)
from jobapply.config_writer import render_config_toml
from jobapply.llm import create_chat_model

# ---------------------------------------------------------------------------
# Config layer
# ---------------------------------------------------------------------------


def test_cloudflare_is_a_known_provider_with_default_model() -> None:
    assert "cloudflare" in PROVIDER_NAMES
    assert DEFAULT_MODELS["cloudflare"].startswith("@cf/")


def test_cloudflare_base_url_template_has_account_placeholder() -> None:
    # Sanity check on the template so a typo doesn't silently break URL
    # assembly across the codebase.
    assert "{account_id}" in CLOUDFLARE_BASE_URL_TEMPLATE
    assert cloudflare_base_url("abc123") == (
        "https://api.cloudflare.com/client/v4/accounts/abc123/ai/v1"
    )


def test_cloudflare_base_url_strips_whitespace() -> None:
    # Users frequently paste ids with stray newlines from the dashboard.
    assert cloudflare_base_url("  abc123 \n").endswith("/accounts/abc123/ai/v1")


def test_provider_config_accepts_account_id() -> None:
    pc = ProviderConfig(api_key="tok", account_id="acct", model="@cf/m")
    assert pc.account_id == "acct"


def test_get_api_key_reads_cloudflare_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_WORKERS_AI_TOKEN", raising=False)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token-from-env")

    assert get_api_key(AppConfig(), "cloudflare") == "token-from-env"


def test_get_api_key_prefers_config_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "from-env")
    cfg = AppConfig(providers={"cloudflare": ProviderConfig(api_key="from-toml")})
    assert get_api_key(cfg, "cloudflare") == "from-toml"


def test_get_account_id_supports_env_indirection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_CF_ACCT", "deadbeef")
    cfg = AppConfig(providers={"cloudflare": ProviderConfig(account_id="env:MY_CF_ACCT")})
    assert get_account_id(cfg, "cloudflare") == "deadbeef"


def test_get_account_id_falls_back_to_dedicated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "env-acct")
    assert get_account_id(AppConfig(), "cloudflare") == "env-acct"


def test_get_base_url_assembles_from_account_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    cfg = AppConfig(providers={"cloudflare": ProviderConfig(account_id="acct123")})
    assert get_base_url(cfg, "cloudflare") == (
        "https://api.cloudflare.com/client/v4/accounts/acct123/ai/v1"
    )


def test_get_base_url_returns_none_without_account_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    assert get_base_url(AppConfig(), "cloudflare") is None


def test_explicit_base_url_overrides_account_id() -> None:
    """Power users (e.g. AI Gateway) can point at a different host."""
    cfg = AppConfig(
        providers={
            "cloudflare": ProviderConfig(
                account_id="acct123",
                base_url="https://gateway.ai.cloudflare.com/v1/acct/gw/compat",
            )
        }
    )
    assert get_base_url(cfg, "cloudflare") == (
        "https://gateway.ai.cloudflare.com/v1/acct/gw/compat"
    )


# ---------------------------------------------------------------------------
# AI Gateway (Unified API) routing
# ---------------------------------------------------------------------------


def test_gateway_url_template_has_both_placeholders() -> None:
    assert "{account_id}" in CLOUDFLARE_GATEWAY_BASE_URL_TEMPLATE
    assert "{gateway_id}" in CLOUDFLARE_GATEWAY_BASE_URL_TEMPLATE


def test_cloudflare_gateway_base_url_assembly() -> None:
    assert cloudflare_gateway_base_url("acct", "gw") == (
        "https://gateway.ai.cloudflare.com/v1/acct/gw/compat"
    )


def test_cloudflare_gateway_base_url_strips_whitespace() -> None:
    assert cloudflare_gateway_base_url("  acct\n", " gw ") == (
        "https://gateway.ai.cloudflare.com/v1/acct/gw/compat"
    )


def test_get_gateway_id_supports_env_indirection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_GW", "prod-gateway")
    cfg = AppConfig(providers={"cloudflare": ProviderConfig(gateway_id="env:MY_GW")})
    assert get_gateway_id(cfg, "cloudflare") == "prod-gateway"


def test_get_gateway_id_falls_back_to_dedicated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_AI_GATEWAY_ID", "env-gw")
    assert get_gateway_id(AppConfig(), "cloudflare") == "env-gw"


def test_get_base_url_uses_gateway_when_gateway_id_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When `gateway_id` is configured we should switch off the direct
    Workers AI endpoint and use AI Gateway's compat URL — that's the only
    path that accepts BYOK third-party models like ``openai/gpt-5``."""
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_AI_GATEWAY_ID", raising=False)

    cfg = AppConfig(
        providers={
            "cloudflare": ProviderConfig(
                account_id="acct123",
                gateway_id="my-gw",
            )
        }
    )
    assert get_base_url(cfg, "cloudflare") == (
        "https://gateway.ai.cloudflare.com/v1/acct123/my-gw/compat"
    )


def test_create_chat_model_cloudflare_uses_gateway_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_AI_GATEWAY_ID", raising=False)

    cfg = AppConfig(
        providers={
            "cloudflare": ProviderConfig(
                api_key="cf-token",
                account_id="acct123",
                gateway_id="prod-gw",
            )
        }
    )
    llm = create_chat_model("cloudflare", "openai/gpt-5", cfg)
    base_url = getattr(llm, "openai_api_base", None) or getattr(llm, "base_url", None)
    assert base_url == "https://gateway.ai.cloudflare.com/v1/acct123/prod-gw/compat"
    assert getattr(llm, "model_name", None) == "openai/gpt-5"


def test_render_config_toml_emits_gateway_id_when_set() -> None:
    cfg = AppConfig(
        providers={
            "cloudflare": ProviderConfig(
                api_key="tok",
                account_id="acct",
                gateway_id="prod-gw",
                model="openai/gpt-5",
            )
        }
    )
    text = render_config_toml(cfg)
    assert 'gateway_id = "prod-gw"' in text
    assert 'model = "openai/gpt-5"' in text


def test_render_config_toml_gateway_placeholder_when_unset() -> None:
    cfg = AppConfig()
    text = render_config_toml(cfg)
    assert "# gateway_id =" in text


# ---------------------------------------------------------------------------
# config_writer
# ---------------------------------------------------------------------------


def test_render_config_toml_emits_cloudflare_block() -> None:
    cfg = AppConfig(
        providers={
            "cloudflare": ProviderConfig(
                api_key="tok",
                account_id="acct",
                model="@cf/meta/llama-3.1-8b-instruct",
            )
        }
    )
    text = render_config_toml(cfg)
    assert "[providers.cloudflare]" in text
    assert 'api_key = "tok"' in text
    assert 'account_id = "acct"' in text
    assert 'model = "@cf/meta/llama-3.1-8b-instruct"' in text


def test_render_config_toml_cloudflare_placeholders_when_unset() -> None:
    """An empty Cloudflare block should still print commented hints so
    `jobapply init` produces a self-documenting file."""
    cfg = AppConfig()
    text = render_config_toml(cfg)
    assert "[providers.cloudflare]" in text
    assert '# api_key = "REPLACE_ME"' in text
    assert '# account_id = "REPLACE_ME"' in text


# ---------------------------------------------------------------------------
# llm.create_chat_model
# ---------------------------------------------------------------------------


def test_create_chat_model_cloudflare_builds_chatopenai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Workers AI is OpenAI-compatible, so we re-use ChatOpenAI but point
    its base_url at the per-account /v1 endpoint."""
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)

    cfg = AppConfig(
        providers={
            "cloudflare": ProviderConfig(
                api_key="cf-token",
                account_id="acct123",
            )
        }
    )
    llm = create_chat_model("cloudflare", "@cf/meta/llama-3.1-8b-instruct", cfg)

    # Avoid asserting on the concrete class to keep the test stable across
    # langchain-openai versions; instead inspect the public attributes that
    # form the contract we care about.
    base_url = getattr(llm, "openai_api_base", None) or getattr(llm, "base_url", None)
    assert base_url == "https://api.cloudflare.com/client/v4/accounts/acct123/ai/v1"
    assert getattr(llm, "model_name", None) == "@cf/meta/llama-3.1-8b-instruct"


def test_create_chat_model_cloudflare_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_WORKERS_AI_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)

    cfg = AppConfig(
        providers={"cloudflare": ProviderConfig(account_id="acct123")},
    )
    with pytest.raises(RuntimeError, match="Cloudflare API token"):
        create_chat_model("cloudflare", "@cf/meta/llama-3.1-8b-instruct", cfg)


def test_create_chat_model_cloudflare_requires_account_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    cfg = AppConfig(
        providers={"cloudflare": ProviderConfig(api_key="cf-token")},
    )
    with pytest.raises(RuntimeError, match="Cloudflare account id"):
        create_chat_model("cloudflare", "@cf/meta/llama-3.1-8b-instruct", cfg)


# ---------------------------------------------------------------------------
# max_tokens — Workers AI's compat endpoint defaults to 256 tokens, which
# truncates structured-output JSON. The factory must apply a sane fallback.
# ---------------------------------------------------------------------------


def test_default_max_tokens_for_cloudflare_is_set() -> None:
    """Sanity-check the constant the factory falls back to."""
    assert DEFAULT_MAX_TOKENS["cloudflare"] >= 1024


def test_get_max_tokens_returns_default_for_cloudflare() -> None:
    """Without an explicit override we return the bundled default so
    Workers AI's 256-token cap doesn't truncate structured outputs."""
    cfg = AppConfig(providers={"cloudflare": ProviderConfig(api_key="t", account_id="a")})
    assert get_max_tokens(cfg, "cloudflare") == DEFAULT_MAX_TOKENS["cloudflare"]


def test_get_max_tokens_honors_user_override() -> None:
    cfg = AppConfig(
        providers={
            "cloudflare": ProviderConfig(
                api_key="t",
                account_id="a",
                max_tokens=8192,
            )
        }
    )
    assert get_max_tokens(cfg, "cloudflare") == 8192


def test_get_max_tokens_returns_none_for_providers_without_default() -> None:
    """Providers like ``openai`` / ``anthropic`` have generous SDK defaults
    of their own — we should NOT silently impose a cap on them."""
    cfg = AppConfig(providers={"openai": ProviderConfig(api_key="t")})
    assert get_max_tokens(cfg, "openai") is None
    assert get_max_tokens(cfg, "anthropic") is None


def test_create_chat_model_cloudflare_passes_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ChatOpenAI instance built for cloudflare must carry the
    completion-token cap (or whatever the user configured)."""
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    cfg = AppConfig(
        providers={
            "cloudflare": ProviderConfig(api_key="cf-token", account_id="acct123"),
        }
    )
    llm = create_chat_model("cloudflare", "@cf/openai/gpt-oss-120b", cfg)
    cap = getattr(llm, "max_tokens", None)
    assert cap == DEFAULT_MAX_TOKENS["cloudflare"]


def test_create_chat_model_cloudflare_user_max_tokens_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    cfg = AppConfig(
        providers={
            "cloudflare": ProviderConfig(
                api_key="cf-token",
                account_id="acct123",
                max_tokens=12000,
            ),
        }
    )
    llm = create_chat_model("cloudflare", "@cf/openai/gpt-oss-120b", cfg)
    assert getattr(llm, "max_tokens", None) == 12000


def test_render_config_toml_cloudflare_max_tokens_hint_when_unset() -> None:
    """When the user hasn't set max_tokens we still surface the knob in
    the rendered TOML so they can find it without reading the docs."""
    cfg = AppConfig(
        providers={
            "cloudflare": ProviderConfig(api_key="t", account_id="a", model="@cf/x/y"),
        }
    )
    text = render_config_toml(cfg)
    assert "# max_tokens" in text


def test_render_config_toml_cloudflare_emits_explicit_max_tokens() -> None:
    cfg = AppConfig(
        providers={
            "cloudflare": ProviderConfig(
                api_key="t",
                account_id="a",
                model="@cf/x/y",
                max_tokens=8192,
            ),
        }
    )
    text = render_config_toml(cfg)
    assert "max_tokens = 8192" in text
