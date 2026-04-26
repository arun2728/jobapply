"""Hashing, slugs, and file helpers."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def stable_job_id(
    *,
    site: str,
    company: str,
    title: str,
    location: str,
    apply_url: str | None,
    job_url: str | None,
) -> str:
    key = "|".join(
        [
            normalize_ws(site),
            normalize_ws(company),
            normalize_ws(title),
            normalize_ws(location),
            normalize_ws(apply_url or ""),
            normalize_ws(job_url or ""),
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def profile_hash(profile_text: str) -> str:
    return hashlib.sha256((profile_text or "").encode("utf-8")).hexdigest()[:32]


def slugify(title: str, company: str, job_id: str) -> str:
    base = f"{title}-{company}-{job_id}"[:80]
    base = re.sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower() or job_id[:12]
    return base[:120]


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
