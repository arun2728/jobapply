"""LangChain chat model factory + structured-output helpers."""

from __future__ import annotations

from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel

from jobapply.config import AppConfig, get_account_id, get_api_key, get_base_url

T = TypeVar("T", bound=BaseModel)


def create_chat_model(
    provider: str,
    model: str,
    cfg: AppConfig | None = None,
) -> BaseChatModel:
    """Build a LangChain chat model. Reads keys/base URLs from `cfg` or env.

    Provider names: ``gemini`` | ``anthropic`` | ``openai`` | ``ollama`` |
    ``cloudflare``. Cloudflare is wired through Workers AI's OpenAI-compatible
    REST endpoint, so it reuses ``ChatOpenAI`` under the hood.
    """
    p = (provider or "gemini").lower().strip()
    cfg = cfg or AppConfig()

    if p == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        key = get_api_key(cfg, "gemini")
        if not key:
            raise RuntimeError(
                "Missing Google API key. Set [providers.gemini].api_key in jobapply.toml "
                "or GOOGLE_API_KEY / GEMINI_API_KEY in env.",
            )
        return ChatGoogleGenerativeAI(model=model, google_api_key=key)

    if p == "anthropic":
        from langchain_anthropic import ChatAnthropic

        key = get_api_key(cfg, "anthropic")
        if not key:
            raise RuntimeError(
                "Missing Anthropic API key. Set [providers.anthropic].api_key in "
                "jobapply.toml or ANTHROPIC_API_KEY in env.",
            )
        base_url = get_base_url(cfg, "anthropic")
        kwargs: dict[str, str] = {"model": model, "api_key": key}
        if base_url:
            kwargs["base_url"] = base_url
        return ChatAnthropic(**kwargs)

    if p == "openai":
        from langchain_openai import ChatOpenAI

        key = get_api_key(cfg, "openai")
        if not key:
            raise RuntimeError(
                "Missing OpenAI API key. Set [providers.openai].api_key in "
                "jobapply.toml or OPENAI_API_KEY in env.",
            )
        base_url = get_base_url(cfg, "openai")
        oai_kwargs: dict[str, str] = {"model": model, "api_key": key}
        if base_url:
            oai_kwargs["base_url"] = base_url
        return ChatOpenAI(**oai_kwargs)

    if p == "ollama":
        from langchain_ollama import ChatOllama

        base_url = get_base_url(cfg, "ollama") or "http://127.0.0.1:11434"
        return ChatOllama(model=model, base_url=base_url)

    if p == "cloudflare":
        # Workers AI exposes an OpenAI-compatible /v1 endpoint per account, so
        # we just point ChatOpenAI at it. The account id is interpolated into
        # the URL at config resolution time (see `config.cloudflare_base_url`).
        from langchain_openai import ChatOpenAI

        key = get_api_key(cfg, "cloudflare")
        if not key:
            raise RuntimeError(
                "Missing Cloudflare API token. Set [providers.cloudflare].api_key in "
                "jobapply.toml or CLOUDFLARE_API_TOKEN in env. Create a token with the "
                "'Workers AI' permission at "
                "https://dash.cloudflare.com/profile/api-tokens.",
            )
        base_url = get_base_url(cfg, "cloudflare")
        if not base_url:
            account_id = get_account_id(cfg, "cloudflare")
            raise RuntimeError(
                "Missing Cloudflare account id. Set [providers.cloudflare].account_id "
                "in jobapply.toml or CLOUDFLARE_ACCOUNT_ID in env. "
                f"(account_id={account_id!r})",
            )
        return ChatOpenAI(model=model, api_key=key, base_url=base_url)

    raise ValueError(f"Unknown provider: {provider}")


def structured(model: BaseChatModel, schema: type[T]) -> BaseChatModel:
    return model.with_structured_output(schema)  # type: ignore[return-value]
