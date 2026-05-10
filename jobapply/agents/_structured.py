"""Robust ``with_structured_output`` wrapper.

OpenAI's *strict* JSON-schema mode is only a real server-side guarantee
when you talk to OpenAI directly. The OpenAI-compatible endpoints we
also support — Cloudflare Workers AI, OpenRouter free tiers, Ollama —
accept the ``response_format=json_schema`` argument but the underlying
open-weights model still emits the occasional malformed shape:

* the requested object wrapped in a single-element list
  (``[{"header": ..., "opening": ...}]``)
* a totally unrelated value (``[2026.05, 10]`` for "today's date")
* nested types where the schema asked for a string (``header: {from: ...}``)

When that happens, ``langchain_openai`` lets the resulting Pydantic
``ValidationError`` bubble up unchanged, which kills whichever tailor
task the user just kicked off. This helper catches the error and:

1. attempts a structural rescue (unwrap single-element list) before
   spending another LLM call, and
2. if that doesn't recover, retries the original prompt with a
   corrective system message that includes the failing input verbatim
   plus the validation diagnostic so the model can self-repair.

The helper is intentionally generic so every agent that uses
``with_structured_output`` can drop it in: see ``cover_letter.py`` and
``resume_tailor.py`` for call sites.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


def invoke_structured(
    llm: BaseChatModel,
    schema: type[T],
    messages: list[BaseMessage],
    *,
    max_retries: int = 2,
) -> T:
    """Call ``llm.with_structured_output(schema)`` with light recovery.

    ``max_retries`` only counts *additional* attempts beyond the first
    call, so the total LLM budget is ``max_retries + 1``. When the
    helper exhausts every option it re-raises the most recent
    ``ValidationError`` so the caller sees the real diagnostic.
    """
    structured = llm.with_structured_output(schema)
    msgs: list[BaseMessage] = list(messages)
    last_err: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            result = structured.invoke(msgs)
        except ValidationError as e:
            last_err = e
            recovered = _try_recover(e, schema)
            if recovered is not None:
                return recovered
            if attempt < max_retries:
                msgs = list(messages) + [_corrective_message(schema, e)]
                continue
            break
        else:
            if isinstance(result, schema):
                return result
            # Some compatible endpoints hand us back a plain dict.
            try:
                return schema.model_validate(result)
            except ValidationError as e:  # pragma: no cover - defensive
                last_err = e
                if attempt < max_retries:
                    msgs = list(messages) + [_corrective_message(schema, e)]
                    continue
                break

    assert last_err is not None
    raise last_err


def _try_recover(err: ValidationError, schema: type[T]) -> T | None:
    """Attempt to salvage common LLM shape mistakes without another call.

    The cheapest mistake to fix is the LLM wrapping the requested
    object in a single-element list — every Pydantic error reported on
    that input includes the offending value, so we just ``model_validate``
    the unwrapped element and call it a day.
    """
    for item in err.errors():
        candidate = item.get("input")
        for unwrapped in _unwrap_candidates(candidate):
            try:
                return schema.model_validate(unwrapped)
            except ValidationError:
                continue
    return None


def _unwrap_candidates(value: Any) -> list[Any]:
    """Return possible "unwrapped" shapes worth re-validating."""
    candidates: list[Any] = []
    if isinstance(value, list) and len(value) == 1:
        candidates.append(value[0])
    if isinstance(value, dict):
        candidates.append(value)
    return candidates


def _corrective_message(schema: type[BaseModel], err: ValidationError) -> SystemMessage:
    """Build a system message that nudges the model toward the schema.

    We deliberately quote the failing input back at the model — it's
    cheap context and makes the "you said X, that's wrong" feedback
    loop much more concrete than just restating the schema.
    """
    fields = sorted(schema.model_fields.keys())
    bad_input = _summarize_bad_input(err)
    return SystemMessage(
        content=(
            f"Your previous response did not satisfy the {schema.__name__} "
            f"schema. Return a SINGLE JSON object (NOT a list) whose "
            f"top-level keys are exactly: {fields}. Each value must match "
            f"its declared type — string fields must be plain strings, not "
            f"nested objects. Do not add extra keys. The previous attempt "
            f"failed because: {err.error_count()} validation error(s); "
            f"received: {bad_input}. Try again."
        )
    )


def _summarize_bad_input(err: ValidationError) -> str:
    """Render the offending input compactly for the corrective hint."""
    try:
        first = err.errors()[0]
    except IndexError:
        return "(unknown)"
    raw = first.get("input")
    try:
        rendered = json.dumps(raw, default=str)
    except (TypeError, ValueError):
        rendered = str(raw)
    if len(rendered) > 400:
        rendered = rendered[:400] + "…"
    return rendered
