# JobApply

Open-source CLI to **search jobs** ([JobSpy](https://github.com/speedyapply/python-jobspy): Indeed, LinkedIn, Google Jobs, etc.), then run a **LangGraph** pipeline that scores fit, **tailors your resume** and **writes a cover letter** from `profile.md` using **Gemini**, **Anthropic**, **OpenAI** (and any OpenAI-compatible gateway), or **Ollama** (structured outputs via LangChain).

Outputs per run:

- `output/run-<timestamp>/jobs.json` — master index + embedded tailored content
- `output/run-<timestamp>/jobs/<slug>/` — `job.json`, `resume.md`, `resume.tex`, `cover_letter.md`, PDFs when `pandoc` / `tectonic` are available

**Deduping & resume**

- Global ledger at `~/.jobapply/ledger.db` skips jobs already completed for the same `profile.md` hash.
- Each run stores `meta.json` (search snapshot). `jobapply resume run-...` skips network search and rebuilds the work queue from `meta.json` + ledger (by default removes `checkpoint.sqlite` so processing restarts cleanly after failures).

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

jobapply init           # interactive: pick provider, paste keys, choose model
# edit profile.md

jobapply run --titles "Backend Engineer,ML Engineer" --skills "Python,Kubernetes" --location "Remote" --yes
```

`jobapply init` writes (or updates) `jobapply.toml` and starter `profile.md`. Use `jobapply config` later to change provider/credentials, or `jobapply config --show` to print the resolved config.

### Configuration

`jobapply.toml` holds the active provider, model defaults, and per-provider connection details. Every secret accepts an indirection: `api_key = "env:OPENAI_API_KEY"` reads the value from the environment at runtime instead of storing it in the file. See [`jobapply.toml.example`](jobapply.toml.example) for a fully documented template covering all four providers.

| Provider | Required keys | Notes |
|----------|---------------|-------|
| `gemini` | `api_key` (or `GOOGLE_API_KEY` / `GEMINI_API_KEY` env) | |
| `anthropic` | `api_key` (or `ANTHROPIC_API_KEY` env) | optional `base_url` |
| `openai` | `api_key` (or `OPENAI_API_KEY` env) | `base_url` for OpenAI-compatible gateways (Azure, Together, Groq, …) |
| `ollama` | none | local; configure `base_url` (default `http://127.0.0.1:11434`) |

`jobapply.toml` is gitignored by default. If you prefer env-only secrets, copy `.env.example` to `.env` and leave `api_key` lines commented out (or use `env:VAR_NAME`).

### Optional tools

- **PDF from Markdown**: [Pandoc](https://pandoc.org/) on `PATH`
- **LaTeX PDF**: [Tectonic](https://tectonic-typesetting.github.io/) or `pdflatex` on `PATH`
- Use `--no-pdf` to skip PDF generation

## Commands

| Command | Description |
|---------|-------------|
| `jobapply init` | Interactive setup: provider + connection details + starter `profile.md` (`--non-interactive` for a blank template) |
| `jobapply config` | Re-run the provider prompts; `--show` prints the resolved config |
| `jobapply run` | Full pipeline (prompts unless `--yes`) |
| `jobapply resume <run-name>` | Continue from `meta.json` (default: reset checkpoint) |
| `jobapply list` | List `output/run-*` folders |

## Architecture

- **LangGraph** `StateGraph`: `search` → `dedupe` → `process_one` (loop until queue empty)
- **SqliteSaver** checkpoint: `output/<run>/checkpoint.sqlite`
- **Agents**: fit scorer, resume tailor, cover letter, optional networking — all `with_structured_output(Pydantic)`
- **Inspiration**: multi-agent patterns from community writeups; production guardrails = structured outputs + ledger + atomic JSON writes

## License

MIT — see [LICENSE](LICENSE).

The bundled LaTeX shell in `jobapply/templates/resume.tex` is minimal MIT; your `profile.md` content is yours.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
