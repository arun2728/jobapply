"""Atomic jobs.json updates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jobapply.models import JobRecord, JobsIndex
from jobapply.utils import atomic_write_json


def load_or_init_index(path: Path, template: JobsIndex) -> JobsIndex:
    if not path.is_file():
        atomic_write_json(path, template.model_dump(mode="json"))
        return template
    data = json.loads(path.read_text(encoding="utf-8"))
    return JobsIndex.model_validate(data)


def upsert_job_record(run_dir: Path, template: JobsIndex, record: JobRecord) -> None:
    path = run_dir / "jobs.json"
    idx = load_or_init_index(path, template)
    by_id = {j.job_id: j for j in idx.jobs}
    by_id[record.job_id] = record
    idx.jobs = sorted(by_id.values(), key=lambda j: j.job_id)
    atomic_write_json(path, idx.model_dump(mode="json"))


def write_job_json(job_dir: Path, payload: dict[str, Any]) -> None:
    p = job_dir / "job.json"
    atomic_write_json(p, payload)
