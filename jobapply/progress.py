"""Rich progress while streaming LangGraph events."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn


def stream_run(
    app: Any,
    initial_state: dict[str, Any],
    config: dict[str, Any],
    *,
    console: Console | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield chunks from graph.stream while updating a progress bar."""
    c = console or Console()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=c,
        transient=False,
    ) as progress:
        task = progress.add_task("jobapply", total=None)
        last_desc = ""
        for chunk in app.stream(initial_state, config, stream_mode="updates"):
            for node, _payload in chunk.items():
                if node == "__end__":
                    continue
                desc = f"{node}"
                if desc != last_desc:
                    progress.update(task, description=desc)
                    last_desc = desc
            yield chunk
        progress.update(task, description="complete", completed=1, total=1)
