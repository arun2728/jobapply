"""LangGraph shared state (TypedDict + reducers)."""

from __future__ import annotations

import operator
from typing import Annotated, Any, NotRequired, TypedDict


class GraphState(TypedDict, total=False):
    run_id: str
    run_dir: str
    profile_path: str
    profile_text: str
    profile_hash: str
    provider: str
    model: str
    min_fit: float
    with_networking: bool
    no_pdf: bool
    force: bool
    ledger_db_path: str
    search_input: dict[str, Any]
    jobs_raw: list[dict[str, Any]]
    queue: list[dict[str, Any]]
    results: Annotated[list[dict[str, Any]], operator.add]
    log: Annotated[list[str], operator.add]
    skip_search: NotRequired[bool]
