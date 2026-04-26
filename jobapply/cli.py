"""Typer CLI: init, config, run, resume, list."""

from __future__ import annotations

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
    find_config_path,
    get_api_key,
    get_base_url,
    load_config,
    load_dotenv_if_present,
)
from jobapply.config_writer import render_config_toml
from jobapply.graph_nodes import bootstrap_resume_state
from jobapply.models import JobSearchInput
from jobapply.runner import run_pipeline
from jobapply.utils import profile_hash as profile_hash_fn

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


def _ledger_db_path(cfg: AppConfig) -> Path:
    if cfg.ledger_path:
        return Path(cfg.ledger_path)
    return Path.home() / ".jobapply" / "ledger.db"


def _default_profile_text() -> str:
    pkg_profile = Path(__file__).resolve().parent.parent / "profile.md"
    if pkg_profile.is_file():
        return pkg_profile.read_text(encoding="utf-8")
    return "# Your Name\n\nReplace this with your real profile.\n"


def _write_profile(target: Path, force: bool) -> None:
    if target.is_file() and not force:
        console.print(f"[yellow]Skip[/yellow] existing {target}")
        return
    target.write_text(_default_profile_text(), encoding="utf-8")
    console.print(f"[green]Wrote[/green] {target}")


def _ask_provider_settings(provider: str, current: ProviderConfig) -> ProviderConfig:
    """Prompt for api_key / base_url / model. Empty input keeps the current value."""
    default_model = current.model or DEFAULT_MODELS.get(provider, "")
    default_base = current.base_url or DEFAULT_BASE_URLS.get(provider, "")

    api_key: str | None = current.api_key
    if provider != "ollama":
        prompt = f"{provider} API key (or env:VAR_NAME, blank to skip)"
        entered = questionary.password(prompt, default=current.api_key or "").ask()
        if entered is None:
            raise typer.Exit(1)
        api_key = entered.strip() or None

    base_url: str | None = current.base_url
    if provider in {"ollama", "openai"} or current.base_url is not None:
        entered_url = questionary.text(
            f"{provider} base URL (blank for default)",
            default=default_base,
        ).ask()
        if entered_url is None:
            raise typer.Exit(1)
        base_url = entered_url.strip() or None

    model = questionary.text(f"{provider} model", default=default_model).ask()
    if model is None:
        raise typer.Exit(1)
    return ProviderConfig(api_key=api_key, base_url=base_url, model=model.strip() or None)


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

    profile_path = (
        questionary.text(
            "Path to your starter profile",
            default=base.profile_path,
        ).ask()
        or base.profile_path
    )
    output_dir = (
        questionary.text(
            "Output directory",
            default=base.output_dir,
        ).ask()
        or base.output_dir
    )

    providers = dict(base.providers)
    providers[provider] = new_pc
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


@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Overwrite existing profile/jobapply.toml"),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Skip prompts and write a default jobapply.toml template.",
    ),
) -> None:
    """Interactively set up provider credentials and starter profile."""
    load_dotenv_if_present()
    root = Path.cwd()
    profile_target = root / "profile.md"
    cfg_path = find_config_path(root)

    if non_interactive:
        _write_profile(profile_target, force=force)
        if cfg_path.is_file() and not force:
            console.print(f"[yellow]Skip[/yellow] existing {cfg_path}")
        else:
            _persist_config(AppConfig(), cfg_path)
        console.print(
            "[dim]Edit jobapply.toml to add your provider keys, or rerun "
            "`jobapply init` for the interactive flow.[/dim]",
        )
        return

    console.print("[bold]Welcome to jobapply.[/bold] Let's configure your provider.\n")
    existing = load_config(root) if cfg_path.is_file() else None
    if existing and not force:
        if not questionary.confirm(
            f"{cfg_path.name} already exists. Update it now?",
            default=True,
        ).ask():
            console.print("[dim]Keeping existing config.[/dim]")
        else:
            cfg = _interactive_config(existing)
            _persist_config(cfg, cfg_path)
    else:
        cfg = _interactive_config(existing)
        _persist_config(cfg, cfg_path)

    _write_profile(profile_target, force=force)
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
    output_dir: str = typer.Option("output", "--output-dir", "-o"),
) -> None:
    """List recent output runs (directories under output/)."""
    root = Path.cwd() / output_dir
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
    results: int = typer.Option(30, "--results", "-n"),
    provider: str | None = typer.Option(None, "--provider"),
    model: str | None = typer.Option(None, "--model"),
    min_fit: float = typer.Option(0.35, "--min-fit"),
    profile_path: str = typer.Option("profile.md", "--profile"),
    output_dir: str = typer.Option("output", "--output-dir", "-o"),
    with_networking: bool = typer.Option(False, "--with-networking"),
    no_pdf: bool = typer.Option(False, "--no-pdf"),
    force: bool = typer.Option(
        False,
        "--force",
        help="Ignore ledger dedupe (still writes new run)",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive defaults"),
) -> None:
    """Search jobs and tailor resume + cover letter for each result."""
    load_dotenv_if_present()
    root = Path.cwd()
    cfg = load_config(root)
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
    prof = Path(profile_path)
    if not prof.is_file():
        console.print(f"[red]Missing profile:[/red] {prof} (run `jobapply init`)")
        raise typer.Exit(1)
    profile_text = prof.read_text(encoding="utf-8")
    ph = profile_hash_fn(profile_text)
    run_id = f"run-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    run_dir = root / output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = _ledger_db_path(cfg)
    search_input = JobSearchInput(
        titles=title_list,
        skills=skill_list,
        location=location or None,
        remote=remote,
        results_wanted=results,
        hours_old=cfg.hours_old,
        site_names=cfg.sites,
    ).model_dump(mode="json")
    initial = {
        "run_id": run_id,
        "run_dir": str(run_dir.resolve()),
        "profile_path": str(prof.resolve()),
        "profile_text": profile_text,
        "profile_hash": ph,
        "provider": prov,
        "model": mdl,
        "min_fit": min_fit,
        "with_networking": with_networking,
        "no_pdf": no_pdf,
        "force": force,
        "ledger_db_path": str(ledger_path.resolve()),
        "search_input": search_input,
        "jobs_raw": [],
        "queue": [],
    }
    _validate_keys(cfg, prov)
    console.print(f"[bold]Run[/bold] {run_id} → {run_dir}")
    run_pipeline(initial, run_dir=run_dir, run_id=run_id, show_progress=True, console=console)
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
    if p in {"openai", "ollama"}:
        get_base_url(cfg, p)


@app.command()
def resume(
    run_name: str = typer.Argument(..., help="Run folder name, e.g. run-20260101-120000"),
    output_dir: str = typer.Option("output", "--output-dir", "-o"),
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
    run_dir = root / output_dir / run_name
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
    console.print(f"[bold]Resume[/bold] {run_id} → {run_dir}")
    run_pipeline(initial, run_dir=run_dir, run_id=run_id, show_progress=True, console=console)
    console.print("[green]Finished resume.[/green]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
