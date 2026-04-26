"""Typer CLI: init, config, run, resume, list."""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import questionary
import typer
from rich.console import Console
from rich.table import Table

from jobapply.config import (
    DEFAULT_BASE_URLS,
    DEFAULT_MODELS,
    PROVIDER_NAMES,
    AppConfig,
    ProviderConfig,
    apply_latex_api_env,
    find_config_path,
    get_account_id,
    get_api_key,
    get_base_url,
    load_config,
    load_dotenv_if_present,
)
from jobapply.config_writer import render_config_toml
from jobapply.graph_nodes import bootstrap_resume_state
from jobapply.models import JobSearchInput, LedgerStatus
from jobapply.nodes.persist import write_jobs_csv_from_path
from jobapply.nodes.render import probe_md_pdf_backend, probe_tex_pdf_backend
from jobapply.profile import (
    Profile,
    ProfileLoadError,
    load_profile,
    profile_skill_list,
    profile_to_text,
    save_profile,
)
from jobapply.profile_import import (
    SUPPORTED_SUFFIXES,
    ResumeImportError,
    extract_profile_from_resume,
    extract_profile_from_text,
)
from jobapply.profile_validation import (
    ProfileIssue,
    validate_profile,
    validate_profile_path,
)
from jobapply.runner import run_pipeline
from jobapply.utils import profile_hash as profile_hash_fn

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()

DEFAULT_PROFILE_FILENAME = "profile.json"


def _ledger_db_path(cfg: AppConfig, cwd: Path | None = None) -> Path:
    """Resolve the ledger path: explicit config value wins; otherwise default.

    Relative ``cfg.ledger_path`` values are resolved against ``cwd`` so users
    can write ``ledger_path = "ledger.db"`` and have it live next to
    ``jobapply.toml``.
    """
    base = cwd or Path.cwd()
    if cfg.ledger_path:
        path = Path(cfg.ledger_path).expanduser()
        if not path.is_absolute():
            path = base / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return base / ".jobapply" / "ledger.db"


def _print_run_summary(run_dir: Path, n_searched: int) -> None:
    """Tally jobs.json by status and print a friendly summary.

    Prints a clear hint when every job was deduped from the ledger so the user
    knows why the run dir looks empty and how to re-run with ``--force``.
    """
    jobs_path = run_dir / "jobs.json"
    if not jobs_path.is_file():
        if n_searched == 0:
            console.print("[yellow]No jobs returned by search.[/yellow]")
        else:
            console.print(
                "[yellow]Search returned "
                f"{n_searched} jobs, but none were processed.[/yellow] "
                "[dim]Pass --force to ignore the ledger and re-process.[/dim]",
            )
        return
    try:
        data = json.loads(jobs_path.read_text(encoding="utf-8"))
        records = data.get("jobs", [])
    except (OSError, json.JSONDecodeError):
        return
    counts = Counter(str(r.get("status", "")) for r in records)
    if not records:
        return

    table = Table(title=f"Run summary ({len(records)} jobs)", show_header=True)
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    order = [
        LedgerStatus.done.value,
        LedgerStatus.cached.value,
        LedgerStatus.skipped.value,
        LedgerStatus.failed.value,
        LedgerStatus.pending.value,
    ]
    for status in order:
        if counts.get(status):
            table.add_row(status, str(counts[status]))
    for status, n in counts.items():
        if status not in order:
            table.add_row(status, str(n))
    console.print(table)

    cached = counts.get(LedgerStatus.cached.value, 0)
    if cached and counts.get(LedgerStatus.done.value, 0) == 0:
        console.print(
            f"[yellow]All {cached} jobs were already processed in earlier "
            "runs.[/yellow] [dim]Re-run with `--force` to ignore the ledger, "
            "or inspect `.jobapply/ledger.db` for prior artifact paths.[/dim]",
        )

    csv_path = write_jobs_csv_from_path(jobs_path, run_dir=run_dir)
    if csv_path is not None:
        console.print(
            f"[green]Wrote[/green] {csv_path} "
            "[dim](import into Google Sheets via File → Import)[/dim]"
        )


def _report_profile_issues(
    issues: list[ProfileIssue],
    *,
    profile_path: Path,
    context: str,
) -> bool:
    """Print profile issues; return True when there are required gaps.

    ``context`` is shown before the bullet list (e.g. "after import" or
    "before this run"). The caller decides what to do with the truthy
    return value (during ``init`` we just keep going; ``run``/``resume``
    keep going too but the user has been clearly warned).
    """
    if not issues:
        return False
    required = [i for i in issues if i.is_required]
    recommended = [i for i in issues if not i.is_required]
    header_color = "red" if required else "yellow"
    header_label = f"{len(required)} required" if required else f"{len(recommended)} recommended"
    console.print(
        f"\n[{header_color}]profile.json needs attention[/{header_color}] "
        f"({header_label} — {context}, {profile_path})"
    )
    for issue in required:
        console.print(f"  [red]•[/red] {issue.message}")
    for issue in recommended:
        console.print(f"  [yellow]•[/yellow] {issue.message}")
    console.print(
        "[dim]Edit the file above and re-run when ready. "
        "Required gaps will produce empty resume sections.[/dim]"
    )
    return bool(required)


def _validate_resume_path(raw: str) -> Path | None:
    """Parse user input into a usable resume path or report why it can't be used."""
    text = raw.strip().strip('"').strip("'")
    if not text:
        return None
    expanded = Path(text).expanduser().resolve()
    if not expanded.is_file():
        console.print(f"[red]Not a file:[/red] {expanded}")
        return None
    if expanded.suffix.lower() not in SUPPORTED_SUFFIXES:
        console.print(
            f"[red]Unsupported format[/red] '{expanded.suffix}'. "
            f"Use one of: {', '.join(SUPPORTED_SUFFIXES)}.",
        )
        return None
    return expanded


def _read_pasted_resume() -> str:
    """Read pasted resume text from stdin. Empty string if user bailed.

    Uses :func:`questionary.text` with ``multiline=True`` when stdin is a
    TTY so users get the standard editor affordance; otherwise we drain
    stdin (``cat resume.txt | jobapply init --paste``).
    """
    if not sys.stdin.isatty():
        return sys.stdin.read()
    answer = questionary.text(
        (
            "Paste your resume below. "
            "Press Esc then Enter (or Meta+Enter) when finished, "
            "or leave blank to abort."
        ),
        multiline=True,
        default="",
    ).ask()
    if answer is None:
        raise typer.Exit(1)
    return str(answer)


def _save_imported_profile(profile: Profile, target: Path) -> None:
    """Write ``profile`` to ``target`` and report any validation issues."""
    save_profile(profile, target)
    console.print(f"[green]Wrote[/green] {target}")
    issues = validate_profile(profile)
    _report_profile_issues(issues, profile_path=target, context="after import")


def _import_profile_from_path(
    resume_path: Path,
    cfg: AppConfig,
    target: Path,
    *,
    force: bool,
) -> bool:
    """Convert ``resume_path`` to ``target`` profile.json. Returns True on success."""
    if (
        target.is_file()
        and not force
        and not questionary.confirm(
            f"{target.name} already exists. Overwrite with imported resume?",
            default=False,
        ).ask()
    ):
        console.print(f"[yellow]Skip[/yellow] {target} (kept existing)")
        return False
    console.print(f"[dim]Importing {resume_path.name}…[/dim]")
    try:
        profile = extract_profile_from_resume(resume_path, cfg)
    except ResumeImportError as exc:
        console.print(f"[red]Resume import failed:[/red] {exc}")
        return False
    _save_imported_profile(profile, target)
    return True


def _import_profile_from_paste(
    resume_text: str,
    cfg: AppConfig,
    target: Path,
    *,
    force: bool,
) -> bool:
    """Convert pasted ``resume_text`` to ``target`` profile.json."""
    if (
        target.is_file()
        and not force
        and not questionary.confirm(
            f"{target.name} already exists. Overwrite with imported resume?",
            default=False,
        ).ask()
    ):
        console.print(f"[yellow]Skip[/yellow] {target} (kept existing)")
        return False
    console.print("[dim]Importing pasted resume text…[/dim]")
    try:
        profile = extract_profile_from_text(resume_text, cfg)
    except ResumeImportError as exc:
        console.print(f"[red]Resume import failed:[/red] {exc}")
        return False
    _save_imported_profile(profile, target)
    return True


def _ask_provider_settings(provider: str, current: ProviderConfig) -> ProviderConfig:
    """Prompt for api_key / base_url / model. Empty input keeps the current value."""
    default_model = current.model or DEFAULT_MODELS.get(provider, "")
    default_base = current.base_url or DEFAULT_BASE_URLS.get(provider, "")

    api_key: str | None = current.api_key
    if provider != "ollama":
        # Cloudflare's "API key" field is actually their API token. Hint it
        # in the prompt so users know which credential to paste.
        if provider == "cloudflare":
            prompt = "Cloudflare API token (Workers AI scope; or env:VAR_NAME, blank to skip)"
        else:
            prompt = f"{provider} API key (or env:VAR_NAME, blank to skip)"
        entered = questionary.password(prompt, default=current.api_key or "").ask()
        if entered is None:
            raise typer.Exit(1)
        api_key = entered.strip() or None

    account_id: str | None = current.account_id
    gateway_id: str | None = current.gateway_id
    if provider == "cloudflare":
        entered_account = questionary.text(
            "Cloudflare account id (find it on the Workers & Pages overview page)",
            default=current.account_id or "",
        ).ask()
        if entered_account is None:
            raise typer.Exit(1)
        account_id = entered_account.strip() or None

        # Optional. Setting this routes through AI Gateway's compat endpoint,
        # which is required for BYOK models like `openai/gpt-5`.
        entered_gateway = questionary.text(
            (
                "Cloudflare AI Gateway slug (optional — leave blank for direct "
                "Workers AI; set this to use BYOK models like openai/gpt-5)"
            ),
            default=current.gateway_id or "",
        ).ask()
        if entered_gateway is None:
            raise typer.Exit(1)
        gateway_id = entered_gateway.strip() or None

    base_url: str | None = current.base_url
    # Cloudflare's base URL is derived from account_id (+ optional gateway_id),
    # so don't prompt for it.
    if provider in {"ollama", "openai"} or (
        current.base_url is not None and provider != "cloudflare"
    ):
        entered_url = questionary.text(
            f"{provider} base URL (blank for default)",
            default=default_base,
        ).ask()
        if entered_url is None:
            raise typer.Exit(1)
        base_url = entered_url.strip() or None

    model_prompt = f"{provider} model"
    if provider == "cloudflare" and gateway_id:
        # Hint the right naming scheme for the gateway path.
        model_prompt += " (use provider/model, e.g. openai/gpt-5)"
    model = questionary.text(model_prompt, default=default_model).ask()
    if model is None:
        raise typer.Exit(1)
    return ProviderConfig(
        api_key=api_key,
        base_url=base_url,
        model=model.strip() or None,
        account_id=account_id,
        gateway_id=gateway_id,
    )


def _interactive_config(existing: AppConfig | None) -> AppConfig:
    """Walk the user through provider + connection settings."""
    base = existing or AppConfig()
    provider = questionary.select(
        "LLM provider",
        choices=list(PROVIDER_NAMES),
        default=base.provider,
    ).ask()
    if not provider:
        raise typer.Exit(1)

    current = base.provider_config(provider)
    new_pc = _ask_provider_settings(provider, current)

    output_dir = (
        questionary.text(
            "Output directory",
            default=base.output_dir,
        ).ask()
        or base.output_dir
    )

    providers = dict(base.providers)
    providers[provider] = new_pc

    # Migrate legacy `profile.md` configs to the new JSON filename so the
    # next `init` writes profile.json AND the toml points at it. Custom
    # paths that aren't the literal default are preserved — power users who
    # set `profile_path = "candidates/jane.json"` keep their override.
    profile_path = base.profile_path
    if not profile_path or profile_path.strip().lower() == "profile.md":
        profile_path = DEFAULT_PROFILE_FILENAME

    return AppConfig(
        provider=provider,
        model=base.model,
        min_fit=base.min_fit,
        results_wanted=base.results_wanted,
        hours_old=base.hours_old,
        concurrency=base.concurrency,
        sites=base.sites,
        profile_path=profile_path,
        output_dir=output_dir,
        ledger_path=base.ledger_path,
        providers=providers,
    )


def _persist_config(cfg: AppConfig, path: Path) -> None:
    path.write_text(render_config_toml(cfg), encoding="utf-8")
    console.print(f"[green]Wrote[/green] {path}")


def _run_resume_import(
    cfg: AppConfig,
    profile_target: Path,
    *,
    resume_path: str | None,
    paste_flag: bool,
    force: bool,
    non_interactive: bool,
) -> bool:
    """Drive the resume → profile.json import.

    Honors three input shapes, in priority order:

    1. ``--resume`` (file path).
    2. ``--paste`` (drain stdin OR open the multiline editor).
    3. Interactive prompts: ask for a path; if blank, fall back to a paste
       prompt. One of the two MUST resolve to non-empty input.

    Returns True iff a profile.json was successfully written. Raises
    :class:`typer.Exit` if the user cancels in interactive mode without
    providing a usable resume — ``init`` is not allowed to finish without
    one.
    """
    if resume_path:
        chosen = _validate_resume_path(resume_path)
        if chosen is None:
            console.print(
                "[red]--resume points at an unusable path.[/red] "
                "Re-run `jobapply init` with a valid file.",
            )
            raise typer.Exit(1)
        return _import_profile_from_path(chosen, cfg, profile_target, force=force)

    if paste_flag:
        text = _read_pasted_resume()
        if not text.strip():
            console.print(
                "[red]No resume text received via --paste.[/red] "
                "Pipe text on stdin or rerun without --paste.",
            )
            raise typer.Exit(1)
        return _import_profile_from_paste(text, cfg, profile_target, force=force)

    if non_interactive:
        console.print(
            "[red]A resume is required.[/red] Pass --resume PATH or --paste "
            "(or rerun without --non-interactive for the prompts).",
        )
        raise typer.Exit(1)

    # Interactive: ask for a file first, fall back to paste if blank.
    while True:
        answer = questionary.text(
            "Path to your resume "
            f"({'/'.join(SUPPORTED_SUFFIXES)}; press Enter to paste text instead)",
            default="",
        ).ask()
        if answer is None:
            raise typer.Exit(1)
        if answer.strip():
            chosen = _validate_resume_path(answer)
            if chosen is None:
                # The validator already explained why; re-prompt.
                continue
            return _import_profile_from_path(chosen, cfg, profile_target, force=force)

        text = _read_pasted_resume()
        if text.strip():
            return _import_profile_from_paste(text, cfg, profile_target, force=force)

        console.print(
            "[red]A resume is required.[/red] Provide a file path or paste "
            "your resume text. (Ctrl+C to abort.)",
        )


@app.command()
def init(
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing profile.json/jobapply.toml without confirmation.",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help=(
            "Skip interactive provider prompts and write a default jobapply.toml. "
            "Still requires --resume or --paste so a profile.json is produced."
        ),
    ),
    resume_path: str | None = typer.Option(
        None,
        "--resume",
        "-r",
        help=(
            "Path to your resume "
            f"({', '.join(SUPPORTED_SUFFIXES)}). "
            "The configured LLM extracts profile.json from it."
        ),
    ),
    paste: bool = typer.Option(
        False,
        "--paste",
        help=(
            "Read resume text from stdin (or open a multiline prompt) instead "
            "of reading a file. Useful when you don't have a file handy."
        ),
    ),
) -> None:
    """Configure your provider and import your resume into ``profile.json``.

    A resume is mandatory: pass ``--resume PATH``, ``--paste`` (with text on
    stdin or via the interactive editor), or answer the interactive prompts.
    The configured LLM is invoked once to populate the JSON schema, so make
    sure your provider credentials work before you run ``init``.
    """
    load_dotenv_if_present()
    root = Path.cwd()
    cfg_path = find_config_path(root)

    cfg: AppConfig
    if non_interactive:
        if cfg_path.is_file() and not force:
            console.print(f"[yellow]Skip[/yellow] existing {cfg_path}")
            cfg = load_config(root)
        else:
            cfg = AppConfig()
            _persist_config(cfg, cfg_path)
    else:
        console.print("[bold]Welcome to jobapply.[/bold] Let's configure your provider.\n")
        existing = load_config(root) if cfg_path.is_file() else None
        if existing and not force:
            if questionary.confirm(
                f"{cfg_path.name} already exists. Update it now?",
                default=True,
            ).ask():
                cfg = _interactive_config(existing)
                _persist_config(cfg, cfg_path)
            else:
                console.print("[dim]Keeping existing config.[/dim]")
                cfg = existing
        else:
            cfg = _interactive_config(existing)
            _persist_config(cfg, cfg_path)

    profile_target = Path(cfg.profile_path or DEFAULT_PROFILE_FILENAME)
    if not profile_target.is_absolute():
        profile_target = root / profile_target

    imported = _run_resume_import(
        cfg,
        profile_target,
        resume_path=resume_path,
        paste_flag=paste,
        force=force,
        non_interactive=non_interactive,
    )

    if not imported:
        console.print(
            "[red]profile.json was not written.[/red] Re-run `jobapply init` "
            "with a valid resume so future `jobapply run` commands have data "
            "to work with.",
        )
        raise typer.Exit(1)

    if non_interactive:
        console.print(
            "[dim]Edit jobapply.toml to add your provider keys, or rerun "
            "`jobapply init` for the interactive flow.[/dim]",
        )
    else:
        console.print(
            "\n[bold green]Setup complete.[/bold green] "
            "Run `jobapply run --titles ...` to start.\n"
            "[dim]Tip: add `jobapply.toml` to .gitignore if you stored secrets in it.[/dim]",
        )


@app.command("config")
def config_cmd(
    show: bool = typer.Option(False, "--show", help="Print the resolved config and exit."),
) -> None:
    """Update or inspect provider settings stored in jobapply.toml."""
    load_dotenv_if_present()
    root = Path.cwd()
    cfg_path = find_config_path(root)

    if show:
        cfg = load_config(root) if cfg_path.is_file() else AppConfig()
        # Print raw to avoid Rich treating `[providers.x]` as markup tags.
        typer.echo(render_config_toml(cfg))
        return

    existing = load_config(root) if cfg_path.is_file() else None
    cfg = _interactive_config(existing)
    _persist_config(cfg, cfg_path)


@app.command("list")
def list_runs(
    output_dir: str | None = typer.Option(None, "--output-dir", "-o"),
) -> None:
    """List recent output runs (directories under output/)."""
    cfg = load_config(Path.cwd())
    root = Path.cwd() / (output_dir or cfg.output_dir)
    if not root.is_dir():
        console.print("[yellow]No output directory yet.[/yellow]")
        raise typer.Exit(0)
    rows = sorted(root.glob("run-*"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
    table = Table(title="Runs")
    table.add_column("Run")
    table.add_column("Has meta")
    table.add_column("Has jobs.json")
    for p in rows:
        table.add_row(
            p.name,
            "yes" if (p / "meta.json").is_file() else "no",
            "yes" if (p / "jobs.json").is_file() else "no",
        )
    console.print(table)


@app.command()
def run(
    titles: str | None = typer.Option(None, "--titles", "-t", help="Comma-separated job titles"),
    skills: str | None = typer.Option(None, "--skills", "-s", help="Comma-separated skills"),
    location: str | None = typer.Option(None, "--location", "-l"),
    remote: bool = typer.Option(False, "--remote"),
    results: int | None = typer.Option(
        None,
        "--results",
        "-n",
        help="Override jobapply.toml `results_wanted`.",
    ),
    provider: str | None = typer.Option(None, "--provider"),
    model: str | None = typer.Option(None, "--model"),
    min_fit: float | None = typer.Option(
        None,
        "--min-fit",
        help="Override jobapply.toml `min_fit`.",
    ),
    profile_path: str | None = typer.Option(
        None,
        "--profile",
        help="Override jobapply.toml `profile_path` (must be a profile.json file).",
    ),
    output_dir: str | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Override jobapply.toml `output_dir`.",
    ),
    with_networking: bool = typer.Option(False, "--with-networking"),
    no_pdf: bool = typer.Option(False, "--no-pdf"),
    force: bool = typer.Option(
        False,
        "--force",
        help="Ignore ledger dedupe (still writes new run)",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive defaults"),
) -> None:
    """Search jobs and tailor resume + cover letter for each result.

    CLI flags override values from ``jobapply.toml``; absent flags fall back to
    the config so settings like ``results_wanted`` actually take effect.
    """
    load_dotenv_if_present()
    root = Path.cwd()
    cfg = load_config(root)
    apply_latex_api_env(cfg)
    if not yes:
        titles = titles or questionary.text("Job titles (comma-separated)").ask()
        skills = skills or questionary.text("Primary skills (comma-separated)", default="").ask()
        if location is None:
            location = questionary.text("Location (or blank)", default="").ask()
    if not titles:
        console.print("[red]titles required[/red]")
        raise typer.Exit(1)
    title_list = [x.strip() for x in titles.split(",") if x.strip()]
    skill_list = [x.strip() for x in (skills or "").split(",") if x.strip()]
    prov = (provider or cfg.provider).lower().strip()
    mdl = model or cfg.resolved_model(prov)
    if not mdl:
        console.print(f"[red]No model configured for provider {prov}.[/red]")
        raise typer.Exit(1)

    effective_results = results if results is not None else cfg.results_wanted
    effective_min_fit = min_fit if min_fit is not None else cfg.min_fit
    effective_profile = profile_path or cfg.profile_path
    effective_output = output_dir or cfg.output_dir

    prof = Path(effective_profile)
    try:
        profile = load_profile(prof)
    except ProfileLoadError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    profile_text = profile_to_text(profile)
    canonical_skills = profile_skill_list(profile)
    _report_profile_issues(
        validate_profile(profile),
        profile_path=prof,
        context="before this run",
    )
    ph = profile_hash_fn(profile_text)
    run_id = f"run-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    run_dir = root / effective_output / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = _ledger_db_path(cfg)
    search_input = JobSearchInput(
        titles=title_list,
        skills=skill_list,
        location=location or None,
        remote=remote,
        results_wanted=effective_results,
        hours_old=cfg.hours_old,
        site_names=cfg.sites,
    ).model_dump(mode="json")
    initial = {
        "run_id": run_id,
        "run_dir": str(run_dir.resolve()),
        "profile_path": str(prof.resolve()),
        "profile_text": profile_text,
        "profile_hash": ph,
        "profile_skills": canonical_skills,
        "provider": prov,
        "model": mdl,
        "min_fit": effective_min_fit,
        "with_networking": with_networking,
        "no_pdf": no_pdf,
        "force": force,
        "ledger_db_path": str(ledger_path.resolve()),
        "search_input": search_input,
        "jobs_raw": [],
        "queue": [],
    }
    _validate_keys(cfg, prov)
    backend = probe_md_pdf_backend() or "none"
    backend_note = {
        "pandoc": "[green]pandoc[/green] (high quality)",
        "weasyprint": "[green]weasyprint[/green] (good)",
        "fpdf2": (
            "[yellow]fpdf2[/yellow] (basic — install [bold]pandoc[/bold] "
            "or [bold]brew install pango[/bold] for nicer output)"
        ),
        "none": "[red]none available[/red]",
    }[backend]
    tex_backend = probe_tex_pdf_backend() or "none"
    tex_backend_note = {
        "latex-on-http": f"[green]latex-on-http[/green] ([dim]{cfg.latex_api.url}[/dim])",
        "tectonic": "[green]tectonic[/green] (local)",
        "pdflatex": "[green]pdflatex[/green] (local)",
        "none": (
            "[red]none available[/red] — enable [bold]latex_api[/bold] "
            "in jobapply.toml or install tectonic/pdflatex"
        ),
    }[tex_backend]
    console.print(
        f"[bold]Run[/bold] {run_id} → {run_dir}\n"
        f"[dim]results_wanted={effective_results}  min_fit={effective_min_fit}  "
        f"sites={','.join(cfg.sites)}[/dim]\n"
        f"[dim]Markdown PDF backend:[/dim] {backend_note}\n"
        f"[dim]LaTeX PDF backend:[/dim] {tex_backend_note}",
    )
    final_state = run_pipeline(
        initial, run_dir=run_dir, run_id=run_id, show_progress=True, console=console
    )
    n_searched = len(final_state.get("jobs_raw") or [])
    _print_run_summary(run_dir, n_searched)
    console.print("[green]Finished.[/green]")


def _validate_keys(cfg: AppConfig, provider: str) -> None:
    p = provider.lower().strip()
    if p == "ollama":
        return
    if not get_api_key(cfg, p):
        console.print(
            f"[yellow]Warning:[/yellow] no API key found for provider={p}. "
            "Set it via `jobapply config` or an env var.",
        )
    if p == "cloudflare" and not get_account_id(cfg, p):
        console.print(
            "[yellow]Warning:[/yellow] no Cloudflare account id found. "
            "Set [providers.cloudflare].account_id in jobapply.toml or "
            "CLOUDFLARE_ACCOUNT_ID in env.",
        )
    if p in {"openai", "ollama"}:
        get_base_url(cfg, p)


@app.command()
def resume(
    run_name: str = typer.Argument(..., help="Run folder name, e.g. run-20260101-120000"),
    output_dir: str | None = typer.Option(None, "--output-dir", "-o"),
    reset_checkpoint: bool = typer.Option(
        True,
        "--reset-checkpoint/--keep-checkpoint",
        help="Rebuild queue from meta.json (recommended after failures).",
    ),
    no_pdf: bool | None = typer.Option(None, "--no-pdf"),
    with_networking: bool | None = typer.Option(None, "--with-networking"),
) -> None:
    """Resume a run using meta.json (skips search). Rebuilds queue via ledger dedupe."""
    load_dotenv_if_present()
    root = Path.cwd()
    cfg = load_config(root)
    apply_latex_api_env(cfg)
    run_dir = root / (output_dir or cfg.output_dir) / run_name
    if not run_dir.is_dir():
        console.print(f"[red]Unknown run:[/red] {run_dir}")
        raise typer.Exit(1)
    ck = run_dir / "checkpoint.sqlite"
    if reset_checkpoint and ck.is_file():
        ck.unlink()
        console.print("[dim]Removed old checkpoint.sqlite[/dim]")
    ledger_path = _ledger_db_path(cfg)
    initial = bootstrap_resume_state(run_dir, ledger_path)
    if no_pdf is not None:
        initial["no_pdf"] = no_pdf
    if with_networking is not None:
        initial["with_networking"] = with_networking
    run_id = initial["run_id"]
    _validate_keys(cfg, str(initial["provider"]))
    profile_str = str(initial.get("profile_path") or "")
    if profile_str:
        _report_profile_issues(
            validate_profile_path(Path(profile_str)),
            profile_path=Path(profile_str),
            context="before this resume",
        )
    console.print(f"[bold]Resume[/bold] {run_id} → {run_dir}")
    final_state = run_pipeline(
        initial, run_dir=run_dir, run_id=run_id, show_progress=True, console=console
    )
    n_searched = len(final_state.get("jobs_raw") or [])
    _print_run_summary(run_dir, n_searched)
    console.print("[green]Finished resume.[/green]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
