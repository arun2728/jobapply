"""Markdown / LaTeX rendering and optional PDF via pandoc / tectonic."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader

from jobapply.models import (
    ContactInfo,
    CoverLetter,
    EducationItem,
    ExperienceRole,
    ProjectItem,
    TailoredResume,
)


def _templates_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates"


def latex_escape(s: str) -> str:
    rep = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    out = []
    for ch in s or "":
        out.append(rep.get(ch, ch))
    return "".join(out)


def _url_escape(url: str) -> str:
    """Escape characters that break ``\\href{...}`` (% and #)."""
    return url.replace("%", r"\%").replace("#", r"\#")


# ----------------------------- contact info -------------------------------- #

# Domain patterns used to extract the username when a full URL is supplied.
_GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/([^/?#]+)", re.IGNORECASE)
_LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/(?:in/)?([^/?#]+)",
    re.IGNORECASE,
)
_MEDIUM_RE = re.compile(
    r"(?:https?://)?(?:www\.)?medium\.com/(?:@)?([^/?#]+)",
    re.IGNORECASE,
)
_TWITTER_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/([^/?#]+)",
    re.IGNORECASE,
)


def _strip_handle(value: str) -> str:
    return value.strip().lstrip("@/").rstrip("/")


def _normalize_phone(value: str) -> tuple[str, str]:
    label = value.strip()
    digits = re.sub(r"[^\d+]", "", label)
    href = f"tel:{digits or label}"
    return href, label


def _normalize_email(value: str) -> tuple[str, str]:
    label = value.strip()
    return f"mailto:{label}", label


def _normalize_via_regex(
    value: str,
    pattern: re.Pattern[str],
    base_url: str,
    label_prefix: str,
    *,
    keep_at_in_label: bool = False,
) -> tuple[str, str]:
    """Match ``pattern`` against ``value`` to extract a username, or treat
    ``value`` as a bare handle. Return ``(href, label)``.
    """
    match = pattern.search(value)
    user = match.group(1) if match else _strip_handle(value)
    user = user.strip("/")
    href = f"{base_url}{user}"
    label = f"{label_prefix}/@{user}" if keep_at_in_label else f"{label_prefix}/{user}"
    return href, label


def _normalize_portfolio(value: str) -> tuple[str, str]:
    raw = value.strip()
    href = raw if raw.startswith(("http://", "https://")) else f"https://{raw}"
    parsed = urlparse(href)
    host = parsed.netloc.removeprefix("www.")
    label = host or raw or href
    return href, label


# fontawesome5 commands. Falls back gracefully if a viewer lacks the glyph.
_ICON: dict[str, str] = {
    "phone": r"\faPhone",
    "email": r"\faEnvelope",
    "portfolio": r"\faGlobe",
    "github": r"\faGithub",
    "linkedin": r"\faLinkedin",
    "medium": r"\faMedium",
    "twitter": r"\faTwitter",
    "location": r"\faMapMarker",
}


def _icon_block(href: str, icon: str, label: str, raise_height: str = "-0.15") -> str:
    """Render a single ``\\href{...}{\\raisebox{...} <icon>\\ <label>}`` entry."""
    safe_url = _url_escape(href)
    safe_label = latex_escape(label)
    return f"\\href{{{safe_url}}}" f"{{\\raisebox{{{raise_height}\\height}} {icon}\\ {safe_label}}}"


def _location_block(value: str) -> str:
    """Plain-text location with an icon, no hyperlink."""
    return f"\\raisebox{{-0.15\\height}} {_ICON['location']}\\ " f"{latex_escape(value.strip())}"


def build_contact_subtitle(c: ContactInfo) -> str:
    """Build the multi-icon subtitle row used inside ``\\documentTitle{}{...}``."""
    parts: list[str] = []
    if c.phone:
        href, label = _normalize_phone(c.phone)
        parts.append(_icon_block(href, _ICON["phone"], label, raise_height="-0.05"))
    if c.email:
        href, label = _normalize_email(c.email)
        parts.append(_icon_block(href, _ICON["email"], label))
    if c.portfolio:
        href, label = _normalize_portfolio(c.portfolio)
        parts.append(_icon_block(href, _ICON["portfolio"], label))
    if c.github:
        href, label = _normalize_via_regex(
            c.github,
            _GITHUB_RE,
            base_url="https://github.com/",
            label_prefix="github",
        )
        parts.append(_icon_block(href, _ICON["github"], label))
    if c.linkedin:
        href, label = _normalize_via_regex(
            c.linkedin,
            _LINKEDIN_RE,
            base_url="https://linkedin.com/in/",
            label_prefix="linkedin",
        )
        parts.append(_icon_block(href, _ICON["linkedin"], label))
    if c.medium:
        href, label = _normalize_via_regex(
            c.medium,
            _MEDIUM_RE,
            base_url="https://medium.com/@",
            label_prefix="medium",
            keep_at_in_label=True,
        )
        parts.append(_icon_block(href, _ICON["medium"], label))
    if c.twitter:
        href, label = _normalize_via_regex(
            c.twitter,
            _TWITTER_RE,
            base_url="https://twitter.com/",
            label_prefix="twitter",
        )
        parts.append(_icon_block(href, _ICON["twitter"], label))
    if c.location:
        parts.append(_location_block(c.location))
    return " ~ | ~ ".join(parts)


def build_contact_markdown(c: ContactInfo) -> str:
    """Compact markdown contact line: pipe-separated hyperlinks."""
    parts: list[str] = []
    if c.phone:
        href, label = _normalize_phone(c.phone)
        parts.append(f"[{label}]({href})")
    if c.email:
        href, label = _normalize_email(c.email)
        parts.append(f"[{label}]({href})")
    if c.portfolio:
        href, label = _normalize_portfolio(c.portfolio)
        parts.append(f"[{label}]({href})")
    if c.github:
        href, label = _normalize_via_regex(c.github, _GITHUB_RE, "https://github.com/", "github")
        parts.append(f"[{label}]({href})")
    if c.linkedin:
        href, label = _normalize_via_regex(
            c.linkedin, _LINKEDIN_RE, "https://linkedin.com/in/", "linkedin"
        )
        parts.append(f"[{label}]({href})")
    if c.medium:
        href, label = _normalize_via_regex(
            c.medium,
            _MEDIUM_RE,
            "https://medium.com/@",
            "medium",
            keep_at_in_label=True,
        )
        parts.append(f"[{label}]({href})")
    if c.twitter:
        href, label = _normalize_via_regex(
            c.twitter, _TWITTER_RE, "https://twitter.com/", "twitter"
        )
        parts.append(f"[{label}]({href})")
    if c.location:
        parts.append(c.location.strip())
    return " | ".join(parts)


def _summary_latex(summary: str) -> str:
    if not summary.strip():
        return ""
    return (
        "\\section{Summary}\n" f"\\hspace{{10pt}}{latex_escape(summary.strip())}\n\\vspace{{2pt}}\n"
    )


def _skills_latex(skills: list[str]) -> str:
    """Two-column bulleted skills, matching the MTeck multicols layout."""
    if not skills:
        return ""
    items = "\n".join(rf"  \item {latex_escape(s)}" for s in skills)
    return (
        "\\section{Skills}\n"
        "\\begin{multicols}{2}\n"
        "\\begin{itemize}[itemsep=-2px, parsep=1pt, leftmargin=20pt]\n"
        f"{items}\n"
        "\\end{itemize}\n"
        "\\end{multicols}\n"
    )


def _resume_list(bullets: list[str]) -> str:
    if not bullets:
        return ""
    body = "\n".join(rf"  \item {latex_escape(b)}" for b in bullets)
    return f"\\begin{{resume_list}}\n{body}\n\\end{{resume_list}}\n"


def _experience_latex(exp: list[ExperienceRole]) -> str:
    if not exp:
        return ""
    parts: list[str] = ["\\section{Experience}"]
    for role in exp:
        parts.append(rf"\headingBf{{{latex_escape(role.company)}}}{{{latex_escape(role.dates)}}}")
        parts.append(rf"\headingIt{{{latex_escape(role.role)}}}{{}}")
        parts.append(_resume_list(role.bullets))
    return "\n".join(parts) + "\n"


def _projects_latex(projects: list[ProjectItem]) -> str:
    if not projects:
        return ""
    parts: list[str] = ["\\section{Projects}"]
    for p in projects:
        parts.append(rf"\headingBf{{{latex_escape(p.name)}}}{{}}")
        parts.append(_resume_list(p.bullets))
    return "\n".join(parts) + "\n"


def _education_latex(education: list[EducationItem]) -> str:
    if not education:
        return ""
    parts: list[str] = ["\\section{Education}"]
    for e in education:
        parts.append(rf"\headingBf{{{latex_escape(e.school)}}}{{{latex_escape(e.dates)}}}")
        right = latex_escape(e.details)
        parts.append(rf"\headingIt{{{latex_escape(e.degree)}}}{{{right}}}")
    return "\n".join(parts) + "\n"


def render_resume_markdown(tr: TailoredResume) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_templates_dir())),
        autoescape=False,
    )
    tpl = env.get_template("resume.md.j2")
    contact_md = build_contact_markdown(tr.contact) if tr.contact.has_any() else ""
    return str(tpl.render(tr=tr, contact_md=contact_md))


def render_cover_markdown(cl: CoverLetter) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_templates_dir())),
        autoescape=False,
    )
    tpl = env.get_template("cover_letter.md.j2")
    return str(tpl.render(cl=cl))


def fill_resume_tex(tr: TailoredResume) -> str:
    """Render :class:`TailoredResume` into the MTeck-styled LaTeX shell."""
    tex_path = _templates_dir() / "resume.tex"
    template = tex_path.read_text(encoding="utf-8")
    body = "\n".join(
        section
        for section in (
            _summary_latex(tr.summary),
            _skills_latex(tr.skills),
            _experience_latex(tr.experience),
            _projects_latex(tr.projects),
            _education_latex(tr.education),
        )
        if section
    )
    title = latex_escape(tr.document_title or "Resume")
    if tr.contact.has_any():
        subtitle = build_contact_subtitle(tr.contact)
    else:
        subtitle = latex_escape(tr.contact_line or "")
    out = template.replace("%%JOBAPPLY_TITLE%%", title)
    out = out.replace("%%JOBAPPLY_SUBTITLE%%", subtitle)
    out = out.replace("%%JOBAPPLY_BODY%%", body)
    return out


def md_to_pdf(md_path: Path, pdf_path: Path) -> bool:
    try:
        import pypandoc

        pypandoc.convert_file(
            str(md_path),
            "pdf",
            outputfile=str(pdf_path),
            extra_args=["--standalone", "-V", "geometry:margin=1in"],
        )
        return pdf_path.is_file()
    except Exception:
        return False


def tex_to_pdf(tex_path: Path, out_dir: Path) -> Path | None:
    """Compile with tectonic if available, else pdflatex."""
    tectonic = shutil.which("tectonic")
    if tectonic:
        proc = subprocess.run(
            [tectonic, "--outdir", str(out_dir), str(tex_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode == 0:
            return out_dir / (tex_path.stem + ".pdf")
        return None
    pdflatex = shutil.which("pdflatex")
    if pdflatex:
        proc = subprocess.run(
            [pdflatex, "-interaction=nonstopmode", f"-output-directory={out_dir}", str(tex_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode == 0:
            return out_dir / (tex_path.stem + ".pdf")
        return None
    return None


def slug_from_paths(job_slug: str, run_dir: Path) -> Path:
    p = run_dir / "jobs" / job_slug
    p.mkdir(parents=True, exist_ok=True)
    return p
