"""Best-effort recovery of a job description from its public URL.

Used by ``jobapply tailor`` when a saved per-job ``job.json`` was
written before we started fetching LinkedIn descriptions (or for any
job whose ``description`` field is empty for unrelated reasons —
e.g. a JobSpy hit that returned metadata only).

The flow is intentionally tolerant: we try a handful of well-known
selectors for the major job boards, fall back to a generic
``<article>`` / ``<main>`` extraction, and return ``None`` if we
can't find anything substantial. Callers are expected to treat
``None`` as "couldn't recover, ask the user to paste the JD" — never
as a fatal error.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

# Mirrors ``jobspy/linkedin/constant.py`` — the same UA + accept
# headers JobSpy uses when scraping LinkedIn's public job-view
# endpoint. Without these LinkedIn frequently 302s to /signup.
_LINKEDIN_HEADERS: dict[str, str] = {
    "authority": "www.linkedin.com",
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "upgrade-insecure-requests": "1",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

#: Generic UA for non-LinkedIn fetches. Most public job boards serve
#: anonymous traffic without much fuss; a normal-looking UA is enough
#: to dodge the most aggressive bot-walls.
_GENERIC_HEADERS: dict[str, str] = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": _LINKEDIN_HEADERS["user-agent"],
}

#: Min description length to consider the backfill "successful".
#: Smaller strings are usually navigation breadcrumbs / placeholder
#: text rather than a real JD.
_MIN_DESCRIPTION_CHARS = 200

#: Per-board selector hints. The first match wins. Ordered roughly
#: by reliability — the LinkedIn ``show-more-less-html__markup``
#: class is exactly what JobSpy itself parses.
_SELECTORS: dict[str, tuple[str, ...]] = {
    "linkedin.com": ("div.show-more-less-html__markup", "div.description__text"),
    "indeed.com": ("#jobDescriptionText", "div.jobsearch-jobDescriptionText"),
    "glassdoor.com": (
        "div.jobDescriptionContent",
        "div.JobDetails_jobDescription__uW_fK",
    ),
    "ziprecruiter.com": ("div.job_description", "div.jobDescriptionSection"),
    "google.com": ("div.YgLbBe", "div.HBvzbc"),
}

# Fallback selectors we try if no host-specific hint matches. Order
# from "most likely to be the JD" to "wide net".
_FALLBACK_SELECTORS: tuple[str, ...] = (
    "article",
    "main",
    "div[class*='description']",
    "div[class*='Description']",
    "section[class*='description']",
)


class JdBackfillError(RuntimeError):
    """Raised when the URL itself is unusable (bad scheme, unparsable).

    Network/HTML-parsing failures *don't* raise — they just return
    ``None`` so the caller can show a friendly suggestion instead.
    """


def _normalize_linkedin_url(url: str) -> str:
    """Coerce any LinkedIn job URL into the canonical ``/jobs/view/<id>`` form.

    Search results sometimes hand us URLs like
    ``/jobs/view/data-engineer-at-pwc-4408659493`` which work but are
    slower than the bare numeric form.
    """
    parsed = urlparse(url)
    if not parsed.netloc.endswith("linkedin.com"):
        return url
    # Extract the trailing numeric job id (LinkedIn job ids are 8-12
    # digits today; we cap at 20 just in case they grow).
    m = re.search(r"(\d{6,20})(?:[/?#]|$)", parsed.path)
    if not m:
        return url
    return f"https://www.linkedin.com/jobs/view/{m.group(1)}"


def _pick_headers(url: str) -> dict[str, str]:
    host = urlparse(url).netloc.lower()
    if "linkedin.com" in host:
        return _LINKEDIN_HEADERS
    return _GENERIC_HEADERS


def _extract_text(html: str, url: str) -> str | None:
    """Pull a JD-shaped chunk of text out of ``html``.

    We import ``bs4`` lazily so importing this module never costs
    anything for tests / users that don't actually backfill.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover - bs4 ships transitively via JobSpy
        return None

    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(url).netloc.lower()
    selector_groups: list[tuple[str, ...]] = []
    for board, sels in _SELECTORS.items():
        if board in host:
            selector_groups.append(sels)
            break
    selector_groups.append(_FALLBACK_SELECTORS)

    for group in selector_groups:
        for sel in group:
            for node in soup.select(sel):
                text = node.get_text(separator="\n", strip=True)
                if len(text) >= _MIN_DESCRIPTION_CHARS:
                    return text
    return None


def fetch_description_from_url(
    url: str,
    *,
    timeout: float = 10.0,
    client: httpx.Client | None = None,
) -> str | None:
    """Try to scrape a job description from ``url``.

    Returns the extracted text on success or ``None`` when the page
    couldn't be loaded / didn't contain anything that looks like a
    JD. The ``client`` parameter is for tests — production callers
    can pass ``None`` and we'll spin up a one-shot ``httpx.Client``.
    """
    if not url or not url.strip():
        return None
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise JdBackfillError(f"Cannot backfill description from non-HTTP URL: {url!r}")

    target = _normalize_linkedin_url(url.strip())
    headers = _pick_headers(target)

    own_client = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        try:
            resp = http.get(target, headers=headers)
        except httpx.HTTPError:
            return None
        if resp.status_code >= 400:
            return None
        # LinkedIn's anti-bot likes to bounce us to /signup or /authwall.
        final_url = str(resp.url)
        if "linkedin.com" in target and (
            "linkedin.com/signup" in final_url or "linkedin.com/authwall" in final_url
        ):
            return None
        return _extract_text(resp.text, target)
    finally:
        if own_client:
            http.close()
