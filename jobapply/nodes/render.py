"""Markdown / LaTeX rendering and optional PDF via pandoc / tectonic."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from jobapply.models import CoverLetter, ExperienceRole, ProjectItem, TailoredResume


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


def _skills_latex(skills: list[str]) -> str:
    if not skills:
        return ""
    items = "\n".join(rf"\item {latex_escape(s)}" for s in skills)
    return "\\section*{Skills}\n\\begin{itemize}\n" + items + "\n\\end{itemize}\n"


def _experience_latex(exp: list[ExperienceRole]) -> str:
    lines: list[str] = []
    for role in exp:
        lines.append(
            rf"\subsection*{{\textbf{{{latex_escape(role.company)}}} — {latex_escape(role.role)}}}"
        )
        if role.dates:
            lines.append(rf"\textit{{{latex_escape(role.dates)}}}\par\smallskip")
        lines.append("\\begin{itemize}")
        for b in role.bullets:
            lines.append(rf"\item {latex_escape(b)}")
        lines.append("\\end{itemize}\n")
    return "\\section*{Experience}\n" + "\n".join(lines) if exp else ""


def _projects_latex(projects: list[ProjectItem]) -> str:
    if not projects:
        return ""
    parts: list[str] = ["\\section*{Projects}"]
    for p in projects:
        parts.append(rf"\subsection*{{{latex_escape(p.name)}}}")
        parts.append("\\begin{itemize}")
        for b in p.bullets:
            parts.append(rf"\item {latex_escape(b)}")
        parts.append("\\end{itemize}")
    return "\n".join(parts) + "\n"


def render_resume_markdown(tr: TailoredResume) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_templates_dir())),
        autoescape=False,
    )
    tpl = env.get_template("resume.md.j2")
    return str(tpl.render(tr=tr))


def render_cover_markdown(cl: CoverLetter) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_templates_dir())),
        autoescape=False,
    )
    tpl = env.get_template("cover_letter.md.j2")
    return str(tpl.render(cl=cl))


def fill_resume_tex(tr: TailoredResume) -> str:
    tex_path = _templates_dir() / "resume.tex"
    template = tex_path.read_text(encoding="utf-8")
    body = (
        f"\\section*{{Summary}}\n{latex_escape(tr.summary)}\n\n"
        f"{_skills_latex(tr.skills)}\n"
        f"{_experience_latex(tr.experience)}\n"
        f"{_projects_latex(tr.projects)}"
    )
    title = latex_escape(tr.document_title or "Resume")
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
