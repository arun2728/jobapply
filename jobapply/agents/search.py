"""JobSpy search with retries."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

from tenacity import retry, stop_after_attempt, wait_exponential

from jobapply.jd_extract import extract_application_hints
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
    linkedin_fetch_description: bool = True,
) -> list[dict[str, Any]]:
    from jobspy import scrape_jobs

    # ``linkedin_fetch_description`` makes JobSpy issue an extra GET per
    # LinkedIn hit to scrape the full JD off the public job-view page.
    # JobSpy defaults this to False (fast, but `description` is blank
    # for every LinkedIn row), which silently breaks `jobapply tailor`
    # later — so we default to True and let the caller opt out.
    raw = scrape_jobs(
        site_name=site_name,
        search_term=search_term,
        location=location or "",
        results_wanted=results_wanted,
        hours_old=hours_old,
        is_remote=is_remote,
        linkedin_fetch_description=linkedin_fetch_description,
    )
    if hasattr(raw, "to_dict"):
        records = raw.to_dict("records")
        return cast(list[dict[str, Any]], records)
    return cast(list[dict[str, Any]], list(raw))


def iter_search_jobs(inp: JobSearchInput) -> Iterator[RawJob]:
    """Stream JobSpy hits as they arrive, deduped by stable job_id.

    Yields one :class:`RawJob` at a time in title-major order so callers
    can persist results incrementally (e.g. ``jobapply search`` flushes
    ``jobs.json``/``jobs.csv`` after each yielded job for live feedback
    instead of waiting for the whole batch to finish). The generator
    stops as soon as ``inp.results_wanted`` unique jobs have been
    yielded.
    """
    site_name = inp.site_names or ["indeed", "linkedin", "google"]
    skills_q = " ".join(inp.skills) if inp.skills else ""
    seen: set[str] = set()
    yielded = 0
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
            linkedin_fetch_description=inp.linkedin_fetch_description,
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
            description = str(d.get("description") or "")
            # Pull recipient email + subject-line / instruction hints
            # out of the JD body so downstream `--with-email` can
            # pre-fill `--email-to` / `--email-context` instead of
            # making the user copy-paste from the description.
            hints = extract_application_hints(description)
            yield RawJob(
                job_id=jid,
                title=title_s,
                company=company,
                location=location_s,
                description=description,
                job_url=str(job_url) if job_url else None,
                apply_url=str(apply_url) if apply_url else None,
                site=site,
                date_posted=str(d.get("date")) if d.get("date") else None,
                application=hints if hints.has_any else None,
                raw=d,
            )
            yielded += 1
            if yielded >= inp.results_wanted:
                return


def search_jobs(inp: JobSearchInput) -> list[RawJob]:
    """Run JobSpy for each title; merge and dedupe by stable job_id.

    Thin wrapper around :func:`iter_search_jobs` that materializes the
    full list upfront. Use the generator directly when you want to
    react to results as they arrive.
    """
    return list(iter_search_jobs(inp))
