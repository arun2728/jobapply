"""Invoke compiled graph with thread_id = run_id."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console

from jobapply.graph import compile_app
from jobapply.progress import stream_run


def run_pipeline(
    initial_state: dict[str, Any],
    *,
    run_dir: Path,
    run_id: str,
    show_progress: bool = True,
    console: Console | None = None,
) -> dict[str, Any]:
    ck = run_dir / "checkpoint.sqlite"
    app, conn = compile_app(ck)
    config: dict[str, Any] = {"configurable": {"thread_id": run_id}}
    try:
        if show_progress:
            for _ in stream_run(app, initial_state, config, console=console):
                pass
        else:
            app.invoke(initial_state, config)
        snap = app.get_state(config)
        vals = getattr(snap, "values", None) if snap is not None else None
        if isinstance(vals, dict):
            return vals
        return {}
    finally:
        conn.close()
