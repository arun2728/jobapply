"""run_dir/meta.json — snapshot for resume (search results + inputs)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from jobapply.utils import atomic_write_json


def write_meta(run_dir: Path, payload: dict[str, Any]) -> None:
    atomic_write_json(run_dir / "meta.json", payload)


def read_meta(run_dir: Path) -> dict[str, Any]:
    p = run_dir / "meta.json"
    if not p.is_file():
        return {}
    return cast(dict[str, Any], json.loads(p.read_text(encoding="utf-8")))
