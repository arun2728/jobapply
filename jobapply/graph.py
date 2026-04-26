"""LangGraph workflow: search → dedupe → process jobs sequentially (checkpointed)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from jobapply.graph_nodes import dedupe_node, process_one_node, search_node
from jobapply.graph_state import GraphState


def route_start(state: GraphState) -> str:
    return "dedupe" if state.get("skip_search") else "search"


def route_after_dedupe(state: GraphState) -> str:
    return "process_one" if state.get("queue") else "end"


def route_after_process(state: GraphState) -> str:
    return "process_one" if state.get("queue") else "end"


def build_workflow() -> StateGraph:
    g = StateGraph(GraphState)
    g.add_node("search", search_node)
    g.add_node("dedupe", dedupe_node)
    g.add_node("process_one", process_one_node)
    g.add_conditional_edges(START, route_start, {"search": "search", "dedupe": "dedupe"})
    g.add_edge("search", "dedupe")
    g.add_conditional_edges(
        "dedupe",
        route_after_dedupe,
        {"process_one": "process_one", "end": END},
    )
    g.add_conditional_edges(
        "process_one",
        route_after_process,
        {"process_one": "process_one", "end": END},
    )
    return g


def compile_app(checkpoint_sqlite: Path) -> tuple[Any, sqlite3.Connection]:
    """Return (compiled graph, sqlite connection) — caller should close conn when done."""
    checkpoint_sqlite.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(checkpoint_sqlite), check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    app = build_workflow().compile(checkpointer=checkpointer)
    return app, conn
