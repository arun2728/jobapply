"""Typer CLI: init, config, run, search, tailor, resume, list."""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import questionary
import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from jobapply.agents.fit_scorer import score_fit
from jobapply.agents.search import iter_search_jobs
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
from jobapply.models import (
    FitScore,
    JobRecord,
    JobSearchInput,
    JobsIndex,
    LedgerStatus,
    RawJob,
)
from jobapply.nodes.persist import write_jobs_csv, write_jobs_csv_from_path
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
from jobapply.tailor_one import (
    JD_SUPPORTED_SUFFIXES,
    JobDescriptionReadError,
    TailorEmailRequest,
    tailor_for_job_description,
)
from jobapply import __version__
from jobapply.llm import create_chat_model
from jobapply.utils import atomic_write_json, profile_hash as profile_hash_fn

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()

DEFAULT_PROFILE_FILENAME = "profile.json"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"jobapply {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show the jobapply version and exit.",
    ),
) -> None:
    """JobApply — search every job board and tailor your resume with AI."""


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
        elif provider == "openrouter":
            prompt = (
                "OpenRouter API key (https://openrouter.ai/keys; "
                "or env:VAR_NAME, blank to skip)"
            )
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
    if provider in {"ollama", "openai", "openrouter"} or (
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
    elif provider == "openrouter":
        # OpenRouter routes by `vendor/model` ids; surface that so users
        # don't paste a bare OpenAI model id by mistake.
        model_prompt += " (use vendor/model, e.g. openai/gpt-4o-mini)"
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
    """Walk the user through provider + connection settings.

    Lets the user configure one or more providers in the same flow so they
    can flip between them at runtime via ``--provider``. The active
    provider written to ``provider = "..."`` is the one used when no
    ``--provider`` flag is passed.
    """
    base = existing or AppConfig()

    # Default-check providers that already have any settings persisted plus
    # the currently-active one so re-running `jobapply config` mirrors the
    # state on disk.
    pre_checked = {name for name in PROVIDER_NAMES if base.providers.get(name)}
    pre_checked.add(base.provider)
    choices = [
        questionary.Choice(name, value=name, checked=name in pre_checked)
        for name in PROVIDER_NAMES
    ]
    selected = questionary.checkbox(
        "Which providers do you want to configure? "
        "(space to toggle, enter to confirm)",
        choices=choices,
        validate=lambda picked: bool(picked) or "Pick at least one provider.",
    ).ask()
    if not selected:
        raise typer.Exit(1)

    providers: dict[str, ProviderConfig] = dict(base.providers)
    for provider in selected:
        console.print(f"\n[bold]Configuring[/bold] {provider}")
        current = base.provider_config(provider)
        providers[provider] = _ask_provider_settings(provider, current)

    # Default provider must be one of the picked ones; preserve the
    # previous default when it's still in the selection.
    default_provider = base.provider if base.provider in selected else selected[0]
    if len(selected) > 1:
        chosen_default = questionary.select(
            "Default provider (used when --provider isn't passed at runtime)",
            choices=list(selected),
            default=default_provider,
        ).ask()
        if not chosen_default:
            raise typer.Exit(1)
        default_provider = chosen_default

    output_dir = (
        questionary.text(
            "Output directory",
            default=base.output_dir,
        ).ask()
        or base.output_dir
    )

    # Migrate legacy `profile.md` configs to the new JSON filename so the
    # next `init` writes profile.json AND the toml points at it. Custom
    # paths that aren't the literal default are preserved — power users who
    # set `profile_path = "candidates/jane.json"` keep their override.
    profile_path = base.profile_path
    if not profile_path or profile_path.strip().lower() == "profile.md":
        profile_path = DEFAULT_PROFILE_FILENAME

    return AppConfig(
        provider=default_provider,
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
        latex_api=base.latex_api,
    )


def _persist_config(cfg: AppConfig, path: Path) -> None:
    path.write_text(render_config_toml(cfg), encoding="utf-8")
    console.print(f"[green]Wrote[/green] {path}")


def _ordered_provider_choices(cfg: AppConfig) -> list[str]:
    """Providers offered at the runtime picker.

    Surfaces every provider the user actually configured first (preserving
    the order from ``jobapply.toml``) and falls back to the active
    provider when nothing else has been configured. We deliberately don't
    include unknown providers from :data:`PROVIDER_NAMES` — that would
    push the user toward a provider they have no credentials for.
    """
    configured = list(cfg.providers.keys())
    if cfg.provider not in configured:
        configured.append(cfg.provider)
    seen: set[str] = set()
    ordered: list[str] = []
    for name in configured:
        if name and name not in seen:
            ordered.append(name)
            seen.add(name)
    return ordered


def _resolve_provider_and_model(
    cfg: AppConfig,
    *,
    provider: str | None,
    model: str | None,
    yes: bool,
) -> tuple[str, str]:
    """Pick the provider + model for this run.

    ``--provider`` / ``--model`` always win. When neither is passed and
    the user is in interactive mode, prompt with the providers they
    configured in ``jobapply.toml`` (default = the active one) and let
    them override the resolved model.
    """
    if provider:
        prov = provider.lower().strip()
    elif yes:
        prov = (cfg.provider or "").lower().strip()
    else:
        choices = _ordered_provider_choices(cfg)
        default_provider = cfg.provider if cfg.provider in choices else choices[0]
        if len(choices) == 1:
            prov = choices[0]
        else:
            answer = questionary.select(
                "Provider for this run",
                choices=choices,
                default=default_provider,
            ).ask()
            if not answer:
                raise typer.Exit(1)
            prov = answer.lower().strip()

    if model:
        mdl = model
    else:
        default_model = cfg.resolved_model(prov)
        if yes or not default_model:
            mdl = default_model
        else:
            answer = questionary.text(
                f"Model for {prov} (Enter to keep default)",
                default=default_model,
            ).ask()
            if answer is None:
                raise typer.Exit(1)
            mdl = answer.strip() or default_model

    if not mdl:
        console.print(f"[red]No model configured for provider {prov}.[/red]")
        raise typer.Exit(1)
    return prov, mdl


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
    provider: str | None = typer.Option(
        None,
        "--provider",
        help=(
            "Pick one of the providers configured in jobapply.toml "
            "(gemini | anthropic | openai | ollama | cloudflare | openrouter). "
            "Defaults to the active `provider` field."
        ),
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help=(
            "Override the model id for this run. Defaults to the chosen "
            "provider's `[providers.<name>].model` value."
        ),
    ),
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
    prov, mdl = _resolve_provider_and_model(
        cfg, provider=provider, model=model, yes=yes
    )

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
    if p in {"openai", "ollama", "openrouter"}:
        get_base_url(cfg, p)


def _record_from_raw_job(
    job: RawJob,
    *,
    fit: FitScore | None = None,
    error: str | None = None,
) -> JobRecord:
    """Wrap a :class:`RawJob` from the search agent into a :class:`JobRecord`.

    The search-only flow doesn't run the tailor / cover-letter / render
    nodes, so the resulting record is pure metadata + an optional
    :class:`FitScore`. We mark it ``pending`` because that's what the
    rest of the pipeline expects for "not yet processed by the tailor"
    — and it keeps ``write_jobs_csv``'s sort logic predictable
    (`pending` rows still sort by `-fit.score`, so scored jobs surface
    highest-fit-first).
    """
    return JobRecord(
        job_id=job.job_id,
        title=job.title,
        company=job.company,
        location=job.location,
        # Truncate to keep jobs.json + CSV manageable; the CSV truncates
        # again to 1000 chars before writing the row anyway.
        description=(job.description or "")[:5000],
        job_url=job.job_url,
        apply_url=job.apply_url,
        site=job.site,
        status=LedgerStatus.pending,
        fit=fit,
        error=error,
        processed_at=datetime.now(UTC),
    )


def _flush_search_state(run_dir: Path, idx: JobsIndex) -> None:
    """Atomically rewrite ``jobs.json`` + ``jobs.csv`` for the current index.

    Called after every fetched/scored job so users get incremental
    visibility — open the CSV mid-run and you'll see the latest hits
    sorted by descending fit score (when scoring is enabled). Writes
    are tiny (a few hundred KB at the worst) so doing this per-job is
    cheap relative to a single LLM call.
    """
    atomic_write_json(run_dir / "jobs.json", idx.model_dump(mode="json"))
    write_jobs_csv(run_dir, idx)


def _print_top_matches(records: list[JobRecord], *, limit: int = 5) -> None:
    """Render a small Rich table of the highest-scoring jobs.

    Silently no-ops when nothing has a fit score — keeps the search
    summary clean for the unscored flow.
    """
    scored = [r for r in records if r.fit is not None]
    if not scored:
        return
    top = sorted(scored, key=lambda r: -(r.fit.score if r.fit else 0.0))[:limit]
    table = Table(title=f"Top {len(top)} matches", show_header=True)
    table.add_column("Score", justify="right", style="bold")
    table.add_column("Title")
    table.add_column("Company")
    table.add_column("Location")
    table.add_column("Link", overflow="fold")
    for r in top:
        score_text = f"{r.fit.score:.2f}" if r.fit else ""
        link = r.apply_url or r.job_url or ""
        table.add_row(score_text, r.title or "", r.company or "", r.location or "", link)
    console.print(table)


@app.command("search")
def search_cmd(
    titles: str | None = typer.Option(
        None, "--titles", "-t", help="Comma-separated job titles."
    ),
    skills: str | None = typer.Option(
        None,
        "--skills",
        "-s",
        help=(
            "Comma-separated skills. Boost the search query and (when --score "
            "is set) bias the fit-scorer toward what you care about."
        ),
    ),
    location: str | None = typer.Option(None, "--location", "-l"),
    remote: bool = typer.Option(False, "--remote"),
    results: int | None = typer.Option(
        None,
        "--results",
        "-n",
        help="Override jobapply.toml `results_wanted`.",
    ),
    sites: str | None = typer.Option(
        None,
        "--sites",
        help=(
            "Comma-separated JobSpy sites (indeed, linkedin, google, "
            "ziprecruiter, glassdoor). Defaults to jobapply.toml `sites`."
        ),
    ),
    score: bool = typer.Option(
        False,
        "--score",
        help=(
            "Score each fetched job against profile.json. Requires the "
            "active provider's credentials and a populated profile."
        ),
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        help=(
            "Pick one of the providers configured in jobapply.toml "
            "(gemini | anthropic | openai | ollama | cloudflare | openrouter). "
            "Only used with --score."
        ),
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help=(
            "Override the model id for scoring. Defaults to the chosen "
            "provider's `[providers.<name>].model` value. Only used with --score."
        ),
    ),
    profile_path: str | None = typer.Option(
        None,
        "--profile",
        help=(
            "Override jobapply.toml `profile_path` (must be a profile.json "
            "file). Only used with --score."
        ),
    ),
    output_dir: str | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Override jobapply.toml `output_dir`. Artifacts land in <output>/search-<ts>/.",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Non-interactive defaults (skip prompts)."
    ),
) -> None:
    """Fetch jobs (and optionally score them) into a CSV — no resume tailoring.

    The lightweight cousin of ``jobapply run``: fans out to every
    configured site via JobSpy, dedupes, and writes
    ``output/search-<ts>/jobs.{json,csv}``. Pass ``--score`` to also run
    the LLM fit scorer over each job — that's the only branch that
    needs your provider credentials and ``profile.json``. Use
    ``--provider``/``--model`` to override the active LLM for this
    invocation.
    """
    load_dotenv_if_present()
    root = Path.cwd()
    cfg = load_config(root)

    if not yes:
        titles = titles or questionary.text("Job titles (comma-separated)").ask()
        skills = skills or questionary.text(
            "Primary skills (comma-separated)", default=""
        ).ask()
        if location is None:
            location = questionary.text("Location (or blank)", default="").ask()
    if not titles:
        console.print("[red]titles required[/red]")
        raise typer.Exit(1)

    title_list = [x.strip() for x in titles.split(",") if x.strip()]
    skill_list = [x.strip() for x in (skills or "").split(",") if x.strip()]
    site_list = (
        [x.strip() for x in sites.split(",") if x.strip()] if sites else cfg.sites
    )
    effective_results = results if results is not None else cfg.results_wanted
    effective_output = output_dir or cfg.output_dir

    profile_text = ""
    profile_path_str = ""
    prov = ""
    mdl = ""
    if score:
        prov, mdl = _resolve_provider_and_model(
            cfg, provider=provider, model=model, yes=yes
        )
        _validate_keys(cfg, prov)
        effective_profile = profile_path or cfg.profile_path
        prof = Path(effective_profile)
        if not prof.is_absolute():
            prof = root / prof
        try:
            profile = load_profile(prof)
        except ProfileLoadError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc
        profile_text = profile_to_text(profile)
        profile_path_str = str(prof.resolve())
        _report_profile_issues(
            validate_profile(profile),
            profile_path=prof,
            context="before this search",
        )
    elif provider or model or profile_path:
        # Be loud about the no-op so users don't think their flag took
        # effect when it actually didn't.
        console.print(
            "[yellow]--provider / --model / --profile are ignored without "
            "--score.[/yellow]"
        )

    run_id = f"search-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    run_dir = root / effective_output / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    search_input = JobSearchInput(
        titles=title_list,
        skills=skill_list,
        location=location or None,
        remote=remote,
        results_wanted=effective_results,
        hours_old=cfg.hours_old,
        site_names=site_list,
    )

    score_summary = (
        f"  provider={prov}  model={mdl}" if score else "  [dim](no scoring)[/dim]"
    )
    console.print(
        f"[bold]Search[/bold] {run_id} → {run_dir}\n"
        f"[dim]results_wanted={effective_results}  sites={','.join(site_list)}"
        f"  score={score}[/dim]{score_summary}"
    )

    # Build an empty index up-front and seed the on-disk artifacts so
    # users can `tail`/refresh the CSV the moment the first job lands.
    idx = JobsIndex(
        run_id=run_id,
        search=search_input,
        profile_path=profile_path_str,
        provider=prov,
        model=mdl,
        jobs=[],
    )
    jobs_path = run_dir / "jobs.json"
    csv_path = run_dir / "jobs.csv"
    meta_path = run_dir / "meta.json"

    def _write_meta(*, fetched: int) -> None:
        # meta.json is informational; rewriting it on each flush gives
        # users a quick glance at progress (`fetched` ticks up live).
        atomic_write_json(
            meta_path,
            {
                "run_id": run_id,
                "search_input": search_input.model_dump(mode="json"),
                "scored": score,
                "provider": prov,
                "model": mdl,
                "profile_path": profile_path_str,
                "fetched": fetched,
            },
        )

    _flush_search_state(run_dir, idx)
    _write_meta(fetched=0)
    console.print(
        f"[dim]Streaming results to[/dim] {jobs_path} "
        f"[dim]and[/dim] {csv_path}"
    )

    records: list[JobRecord] = idx.jobs  # alias the live list
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TextColumn("[bold]{task.completed}[/bold] jobs"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Searching job boards", total=None)
        for j in iter_search_jobs(search_input):
            records.append(_record_from_raw_job(j))
            _flush_search_state(run_dir, idx)
            _write_meta(fetched=len(records))
            progress.update(task, advance=1)
    console.print(f"[green]Fetched[/green] {len(records)} jobs")

    if score and records:
        try:
            llm = create_chat_model(prov, mdl, cfg=cfg)
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task("Scoring jobs", total=len(records))
            for i, raw_record in enumerate(list(records)):
                # Re-build the RawJob handle from the persisted record so
                # the scorer sees the same fields callers do. We pull the
                # full description from the source list (already truncated
                # to 5000 chars by `_record_from_raw_job`).
                job = RawJob(
                    job_id=raw_record.job_id,
                    title=raw_record.title,
                    company=raw_record.company,
                    location=raw_record.location,
                    description=raw_record.description,
                    job_url=raw_record.job_url,
                    apply_url=raw_record.apply_url,
                    site=raw_record.site,
                )
                fit: FitScore | None = None
                err: str | None = None
                try:
                    fit = score_fit(
                        llm,
                        profile_text=profile_text,
                        job=job,
                        skills=skill_list,
                    )
                except Exception as exc:  # noqa: BLE001
                    # One bad job shouldn't kill the whole batch; record
                    # the failure on this row and keep going.
                    err = f"score failed: {exc}"
                records[i] = _record_from_raw_job(job, fit=fit, error=err)
                _flush_search_state(run_dir, idx)
                desc_label = (job.title or job.company or job.job_id)[:48]
                progress.update(task, advance=1, description=f"Scoring {desc_label}")

    console.print(
        f"[green]Wrote[/green] {jobs_path}\n"
        f"[green]Wrote[/green] {csv_path} "
        "[dim](import into Google Sheets via File → Import)[/dim]"
    )

    if score:
        scored_ok = sum(1 for r in records if r.fit is not None)
        scored_failed = sum(1 for r in records if r.error)
        console.print(
            f"[dim]Scored {scored_ok}/{len(records)} jobs"
            + (f" ({scored_failed} failed)" if scored_failed else "")
            + ".[/dim]"
        )
        _print_top_matches(records)
    console.print("[green]Finished search.[/green]")


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


def _validate_jd_path(raw: str) -> Path | None:
    """Parse a JD path argument the way ``_validate_resume_path`` does.

    Strips quotes, expands ``~``, resolves the absolute path, and
    rejects unreadable / wrong-extension files with a friendly message
    so the CLI doesn't drop a stack trace on the user.
    """
    text = raw.strip().strip('"').strip("'")
    if not text:
        return None
    expanded = Path(text).expanduser().resolve()
    if not expanded.is_file():
        console.print(f"[red]Not a file:[/red] {expanded}")
        return None
    if expanded.suffix.lower() not in JD_SUPPORTED_SUFFIXES:
        console.print(
            f"[red]Unsupported job description format[/red] '{expanded.suffix}'. "
            f"Use one of: {', '.join(JD_SUPPORTED_SUFFIXES)}.",
        )
        return None
    return expanded


def _print_tailor_summary(
    *,
    job_dir: Path,
    artifacts: dict[str, Path | None],
    email_to: str | None,
) -> None:
    """Pretty-print the artifacts produced by ``jobapply tailor``."""
    table = Table(title=f"Tailored artifacts → {job_dir}", show_header=True)
    table.add_column("Artifact", style="bold")
    table.add_column("Path")
    rows: list[tuple[str, Path | None]] = [
        ("resume.md", artifacts.get("resume_md")),
        ("resume.pdf", artifacts.get("resume_pdf")),
        ("resume.tex", artifacts.get("resume_tex")),
        ("resume (LaTeX PDF)", artifacts.get("resume_latex_pdf")),
        ("cover_letter.md", artifacts.get("cover_md")),
        ("cover_letter.pdf", artifacts.get("cover_pdf")),
        ("cover_letter.tex", artifacts.get("cover_tex")),
        ("cover_letter (LaTeX PDF)", artifacts.get("cover_latex_pdf")),
        ("email.txt", artifacts.get("email_path")),
    ]
    for label, path in rows:
        if path is not None:
            table.add_row(label, str(path))
    console.print(table)
    if email_to:
        console.print(
            f"[dim]Email drafted for {email_to} — copy "
            f"{artifacts.get('email_path')} into your mail client.[/dim]"
        )


@app.command()
def tailor(
    job_description: str | None = typer.Option(
        None,
        "--job",
        "-j",
        help=(
            "Path to the job description "
            f"({', '.join(JD_SUPPORTED_SUFFIXES)}). The configured LLM tailors "
            "your resume + cover letter to it."
        ),
    ),
    profile_path: str | None = typer.Option(
        None,
        "--profile",
        help="Override jobapply.toml `profile_path` (must point at profile.json).",
    ),
    output_dir: str | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Override jobapply.toml `output_dir`. Artifacts land in <output>/tailor-<ts>/.",
    ),
    title_override: str | None = typer.Option(
        None,
        "--title",
        help="Skip JD title detection and force this title (slug + agents use it).",
    ),
    company_override: str | None = typer.Option(
        None,
        "--company",
        help="Skip JD company detection and force this company.",
    ),
    location_override: str | None = typer.Option(
        None,
        "--location",
        "-l",
        help="Optional location override (purely informational).",
    ),
    skills: str | None = typer.Option(
        None,
        "--skills",
        "-s",
        help="Comma-separated skills to bias the tailor towards (in addition to the JD).",
    ),
    provider: str | None = typer.Option(
        None,
        "--provider",
        help=(
            "Pick one of the providers configured in jobapply.toml "
            "(gemini | anthropic | openai | ollama | cloudflare | openrouter). "
            "Defaults to the active `provider` field."
        ),
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help=(
            "Override the model id for this tailor run. Defaults to the "
            "chosen provider's `[providers.<name>].model` value."
        ),
    ),
    no_pdf: bool = typer.Option(False, "--no-pdf", help="Skip PDF rendering."),
    with_email: bool = typer.Option(
        False,
        "--with-email",
        help="Also draft a ready-to-paste application email (requires --email-to or prompt).",
    ),
    email_to: str | None = typer.Option(
        None,
        "--email-to",
        help="Recipient email address for the drafted application email.",
    ),
    email_context: str | None = typer.Option(
        None,
        "--email-context",
        help=(
            "Optional extra context for the drafted email "
            "(e.g. referrals, availability, prior contact)."
        ),
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive defaults."),
) -> None:
    """Tailor your resume + cover letter for a single job description.

    Pass a JD file with ``--job <path>`` and the configured LLM produces a
    tailored ``resume.md`` / ``resume.pdf`` (plus a styled LaTeX PDF) and
    matching ``cover_letter.*`` files under ``<output_dir>/tailor-<ts>/``.

    Add ``--with-email`` to also produce a ready-to-paste application
    email — the recipient address is required (``--email-to`` or
    interactive prompt). ``--email-context`` lets you weave in
    referrals, availability, or any prior contact you've had with the
    recruiter so the draft sounds personal rather than generic.
    """
    load_dotenv_if_present()
    root = Path.cwd()
    cfg = load_config(root)
    apply_latex_api_env(cfg)

    if not job_description and not yes:
        job_description = questionary.text(
            "Path to the job description "
            f"({'/'.join(JD_SUPPORTED_SUFFIXES)})",
            default="",
        ).ask()
    if not job_description:
        console.print(
            "[red]A job description path is required.[/red] "
            "Pass --job <path> or rerun without --yes for the prompt.",
        )
        raise typer.Exit(1)
    jd_path = _validate_jd_path(job_description)
    if jd_path is None:
        raise typer.Exit(1)

    if with_email and not email_to and not yes:
        email_to = questionary.text(
            "Recipient email address for the application email",
            default="",
        ).ask()
    if with_email and not (email_to or "").strip():
        console.print(
            "[red]--with-email requires --email-to[/red] "
            "(or rerun without --yes so we can prompt for it).",
        )
        raise typer.Exit(1)
    if with_email and email_context is None and not yes:
        ctx_answer = questionary.text(
            "Any extra context for the email? (referrals, availability, etc.; blank to skip)",
            default="",
        ).ask()
        email_context = ctx_answer if ctx_answer is not None else ""

    prov, mdl = _resolve_provider_and_model(
        cfg, provider=provider, model=model, yes=yes
    )
    _validate_keys(cfg, prov)

    effective_profile = profile_path or cfg.profile_path
    effective_output = output_dir or cfg.output_dir
    prof = Path(effective_profile)
    if not prof.is_absolute():
        prof = root / prof
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
        context="before this tailor run",
    )

    skill_list = [x.strip() for x in (skills or "").split(",") if x.strip()]
    output_root = root / effective_output / f"tailor-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    output_root.mkdir(parents=True, exist_ok=True)

    backend = probe_md_pdf_backend() or "none"
    tex_backend = probe_tex_pdf_backend() or "none"
    console.print(
        f"[bold]Tailor[/bold] {jd_path.name} → {output_root}\n"
        f"[dim]profile={prof}  provider={prov}  model={mdl}[/dim]\n"
        f"[dim]Markdown PDF backend:[/dim] {backend}  "
        f"[dim]LaTeX PDF backend:[/dim] {tex_backend}",
    )

    try:
        llm = create_chat_model(prov, mdl, cfg=cfg)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    email_request: TailorEmailRequest | None = None
    if with_email:
        email_request = TailorEmailRequest(
            recipient=(email_to or "").strip(),
            additional_info=(email_context or "").strip(),
        )

    try:
        outputs = tailor_for_job_description(
            llm,
            jd_path=jd_path,
            profile_text=profile_text,
            profile_skills=canonical_skills,
            output_root=output_root,
            target_skills=skill_list,
            title_override=title_override,
            company_override=company_override,
            location_override=location_override,
            no_pdf=no_pdf,
            email=email_request,
        )
    except JobDescriptionReadError as exc:
        console.print(f"[red]Job description error:[/red] {exc}")
        raise typer.Exit(1) from exc

    artifacts: dict[str, Path | None] = {
        "resume_md": outputs.resume_md,
        "resume_pdf": outputs.resume_pdf,
        "resume_tex": outputs.resume_tex,
        "resume_latex_pdf": outputs.resume_latex_pdf,
        "cover_md": outputs.cover_md,
        "cover_pdf": outputs.cover_pdf,
        "cover_tex": outputs.cover_tex,
        "cover_latex_pdf": outputs.cover_latex_pdf,
        "email_path": outputs.email_path,
    }
    _print_tailor_summary(
        job_dir=outputs.job_dir,
        artifacts=artifacts,
        email_to=outputs.email.to if outputs.email else None,
    )
    console.print(
        f"[green]Tailored[/green] '{outputs.job.title}' at {outputs.job.company}."
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
