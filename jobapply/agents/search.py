"""JobSpy search with retries."""

from __future__ import annotations

from typing import Any, cast

from tenacity import retry, stop_after_attempt, wait_exponential

from jobapply.models import JobSearchInput, RawJob
from jobapply.utils import stable_job_id


def _row_to_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "to_dict"):
        return dict(row.to_dict())
    if isinstance(row, dict):
        return dict(row)
    return dict(row._asdict()) if hasattr(row, "_asdict") else dict(row)


@retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(3))
def _scrape_once(
    *,
    site_name: list[str],
    search_term: str,
    location: str | None,
    results_wanted: int,
    hours_old: int,
    is_remote: bool,
) -> list[dict[str, Any]]:
    from jobspy import scrape_jobs

    raw = scrape_jobs(
        site_name=site_name,
        search_term=search_term,
        location=location or "",
        results_wanted=results_wanted,
        hours_old=hours_old,
        is_remote=is_remote,
    )
    if hasattr(raw, "to_dict"):
        records = raw.to_dict("records")
        return cast(list[dict[str, Any]], records)
    return cast(list[dict[str, Any]], list(raw))


def search_jobs(inp: JobSearchInput) -> list[RawJob]:
    """Run JobSpy for each title; merge and dedupe by stable job_id."""
    site_name = inp.site_names or ["indeed", "linkedin", "google"]
    skills_q = " ".join(inp.skills) if inp.skills else ""
    seen: set[str] = set()
    out: list[RawJob] = []
    per_title = max(5, min(inp.results_wanted, 200 // max(1, len(inp.titles))))

    for title in inp.titles:
        term = f"{title.strip()} {skills_q}".strip()
        rows = _scrape_once(
            site_name=site_name,
            search_term=term,
            location=inp.location,
            results_wanted=per_title,
            hours_old=inp.hours_old,
            is_remote=inp.remote,
        )
        for row in rows:
            d = _row_to_dict(row)
            title_s = str(d.get("title") or "")
            company = str(d.get("company") or "")
            location_s = str(d.get("location") or "")
            site = str(d.get("site") or "")
            job_url = d.get("job_url") or d.get("url")
            apply_url = d.get("job_url_apply") or d.get("apply_url") or job_url
            jid = stable_job_id(
                site=site,
                company=company,
                title=title_s,
                location=location_s,
                apply_url=str(apply_url) if apply_url else None,
                job_url=str(job_url) if job_url else None,
            )
            if jid in seen:
                continue
            seen.add(jid)
            out.append(
                RawJob(
                    job_id=jid,
                    title=title_s,
                    company=company,
                    location=location_s,
                    description=str(d.get("description") or ""),
                    job_url=str(job_url) if job_url else None,
                    apply_url=str(apply_url) if apply_url else None,
                    site=site,
                    date_posted=str(d.get("date")) if d.get("date") else None,
                    raw=d,
                )
            )
        if len(out) >= inp.results_wanted:
            break
    return out[: inp.results_wanted]
