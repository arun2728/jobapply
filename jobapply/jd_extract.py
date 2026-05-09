"""Heuristic extractors for application-related hints in a JD body.

Recruiters frequently embed instructions like "send your resume to
``recruiter@acme.com``" and "mention subject line as 'Job
Application — Skillset'" directly in the description. We pull those
out at fetch time so:

* ``jobapply tailor --with-email`` can pre-fill ``--email-to`` and
  ``--email-context`` with the recipient + subject the recruiter
  asked for, instead of requiring the user to copy-paste them.
* ``jobs.csv`` can surface the recipient address as its own column
  for triage in Google Sheets.

Everything here is regex-driven on purpose — it has to run on every
fetched job (no LLM cost) and stay deterministic. We're forgiving
about format (smart quotes, dashes, "Subject:" prefixes, multi-line
instructions) and conservative about precision: when nothing
matches we return empty rather than guessing.
"""

from __future__ import annotations

import re

from jobapply.models import ApplicationHints

# RFC-loose email regex. We deliberately don't try to validate the
# domain — recruiters routinely list addresses on private domains
# that wouldn't pass a strict check, and a false negative here
# wastes much more time than a false positive (the user just sees
# the wrong address and overrides it on the CLI).
_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)+",
)

# Trailing punctuation we strip from a captured email address.
# Markdown-ified JDs sometimes leave us with ``recruiter@acme.com.``
# or ``recruiter@acme.com)`` and we want the bare address.
_EMAIL_TRAILING = ".,;:)]>}'\"!?"

#: Phrases that strongly suggest the *next* email is the recipient.
#: Order matters only loosely — we score every email by its closest
#: trigger and pick the highest-scoring one.
_RECIPIENT_TRIGGERS: tuple[str, ...] = (
    "send your resume to",
    "send your cv to",
    "send your resumes to",
    "send the resume to",
    "send resume to",
    "send your application to",
    "send applications to",
    "share your resume at",
    "share your resume to",
    "share your cv at",
    "share your cv to",
    "share your profile at",
    "drop your resume at",
    "drop your cv at",
    "email your resume to",
    "email your cv to",
    "email me at",
    "email us at",
    "email at",
    "reach out to",
    "reach me at",
    "contact at",
    "apply at",
    "apply to",
    "interested candidates can write to",
    "interested candidates please share",
    "interested candidates can mail",
    "kindly mail your",
    "please share your resume at",
    "please share your cv at",
    "please send your resume to",
    "please send your cv to",
)

#: Patterns that capture a recruiter-supplied subject line. The
#: capture group must yield the subject text itself; we strip
#: surrounding quotes and trailing punctuation downstream.
_SUBJECT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:please\s+)?(?:mention|use|put|keep|set|write|include)\s+"
        r"(?:the\s+)?subject(?:\s+line)?\s+(?:as|should\s+be|reading|to\s+read|to\s+say|:)\s+"
        r"['\"\u2018\u2019\u201c\u201d]?(?P<subject>[^'\"\n\u2018\u2019\u201c\u201d]+?)"
        r"['\"\u2018\u2019\u201c\u201d]?(?:[\.\n]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"with\s+(?:the\s+)?subject(?:\s+line)?\s+"
        r"['\"\u2018\u2019\u201c\u201d]?(?P<subject>[^'\"\n\u2018\u2019\u201c\u201d]+?)"
        r"['\"\u2018\u2019\u201c\u201d]?(?:[\.\n]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"subject\s*[:=]\s*"
        r"['\"\u2018\u2019\u201c\u201d]?(?P<subject>[^'\"\n\u2018\u2019\u201c\u201d]+?)"
        r"['\"\u2018\u2019\u201c\u201d]?(?:[\.\n]|$)",
        re.IGNORECASE,
    ),
)

#: Sentence-ish trigger words. When a sentence in the JD contains
#: any of these we consider it part of the application instructions
#: and surface it back to the user — that's how we capture things
#: like "Please mention your notice period" alongside the email.
_INSTRUCTION_KEYWORDS: tuple[str, ...] = (
    "send your resume",
    "send your cv",
    "share your resume",
    "share your cv",
    "send the resume",
    "send your application",
    "mention subject",
    "mention the subject",
    "subject line",
    "with subject",
    "interested candidates",
    "please mention",
    "kindly mention",
    "please share",
    "please send",
    "kindly send",
    "drop your resume",
    "email your resume",
    "email your cv",
)

#: Cap so we don't paste a novel into ``--email-context``. Most
#: recruiter blurbs are 1-2 sentences; anything beyond ~6 lines is
#: usually nav text we picked up by accident.
_MAX_INSTRUCTIONS = 6


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_emails(text: str) -> list[str]:
    """Return every email-shaped substring in ``text`` (deduped, ordered).

    We strip trailing punctuation and lowercase the address so
    comparisons elsewhere are stable. Order is preserved so the
    "first email mentioned" stays first — useful for callers that
    want a quick fallback when no trigger phrase matched.
    """
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in _EMAIL_RE.findall(text):
        cleaned = raw.strip().rstrip(_EMAIL_TRAILING).lower()
        if not cleaned or "@" not in cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def _pick_primary_email(text: str, emails: list[str]) -> str | None:
    """Score each candidate email by proximity to a recipient trigger.

    Higher score = trigger phrase appeared closer (and earlier) than
    the email. Falls back to the first email when no trigger matches
    so single-recipient JDs always have a primary.
    """
    if not emails:
        return None
    if len(emails) == 1:
        return emails[0]

    lower = text.lower()
    best_score = -1
    best_email: str | None = None
    for addr in emails:
        idx = lower.find(addr)
        if idx < 0:
            continue
        # Window of 200 chars *before* the email — that's the
        # sweet spot for "Please send your resume to <X>" where
        # the trigger is right before the address.
        window_start = max(0, idx - 200)
        window = lower[window_start:idx]
        score = 0
        for trigger in _RECIPIENT_TRIGGERS:
            tidx = window.rfind(trigger)
            if tidx < 0:
                continue
            # The closer the trigger is to the email, the better.
            distance = len(window) - tidx
            score = max(score, 200 - distance)
        if score > best_score:
            best_score = score
            best_email = addr
    return best_email or emails[0]


def extract_subject_line(text: str) -> str | None:
    """Extract a recruiter-supplied email subject line, if any.

    Tries each pattern in order and returns the first match. We
    strip quotes, leading "Re:" /"Fwd:", and trailing punctuation
    so the result is paste-ready for an email client.
    """
    if not text:
        return None
    for pattern in _SUBJECT_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        subject = m.group("subject")
        if not subject:
            continue
        # Strip wrapping quotes / smart quotes the regex deliberately
        # treats as optional, plus trailing punctuation.
        subject = subject.strip().strip("'\"\u2018\u2019\u201c\u201d").strip()
        subject = subject.rstrip(".,;:")
        if subject:
            return subject
    return None


def extract_instructions(text: str) -> list[str]:
    """Return short, dedupe'd sentences that look like apply-instructions.

    We segment on newline / sentence boundaries and keep only
    sentences containing at least one of ``_INSTRUCTION_KEYWORDS``.
    Capped at ``_MAX_INSTRUCTIONS`` to keep ``--email-context``
    short and on-topic.
    """
    if not text:
        return []
    # Split on either explicit newlines or sentence enders. We
    # don't import nltk here on purpose — the heuristic is fine.
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    seen: set[str] = set()
    out: list[str] = []
    for raw in parts:
        sentence = _normalize_whitespace(raw)
        if not sentence:
            continue
        lower = sentence.lower()
        if not any(kw in lower for kw in _INSTRUCTION_KEYWORDS):
            continue
        # Keep it tight — long sentences are usually paragraph
        # blobs the regex split couldn't break apart.
        if len(sentence) > 280:
            sentence = sentence[:277].rstrip() + "..."
        if sentence in seen:
            continue
        seen.add(sentence)
        out.append(sentence)
        if len(out) >= _MAX_INSTRUCTIONS:
            break
    return out


def extract_application_hints(text: str) -> ApplicationHints:
    """One-shot wrapper that returns a fully-populated ``ApplicationHints``.

    Empty input → empty hints (every field defaulted). Callers can
    treat the result as truthy/falsey via ``ApplicationHints.has_any``.
    """
    if not text or not text.strip():
        return ApplicationHints()
    emails = extract_emails(text)
    return ApplicationHints(
        emails=emails,
        primary_email=_pick_primary_email(text, emails),
        subject_line=extract_subject_line(text),
        instructions=extract_instructions(text),
    )


def hints_to_email_context(hints: ApplicationHints) -> str:
    """Format ``ApplicationHints`` as an ``--email-context`` string.

    The output is what we'd pass to the email-drafter LLM as
    ``additional_info`` so the generated email respects the
    recruiter's instructions. Returns ``""`` when there's nothing
    useful to say.
    """
    parts: list[str] = []
    if hints.subject_line:
        parts.append(f"Use the email subject line: '{hints.subject_line}'.")
    for note in hints.instructions:
        parts.append(note)
    return " ".join(parts).strip()
