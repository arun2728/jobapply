# JobApply

Open-source CLI to **search jobs** ([JobSpy](https://github.com/speedyapply/python-jobspy): Indeed, LinkedIn, Google Jobs, etc.), then run a **LangGraph** pipeline that scores fit, **tailors your resume** and **writes a cover letter** from `profile.md` using **Gemini**, **Anthropic**, **OpenAI** (and any OpenAI-compatible gateway), or **Ollama** (structured outputs via LangChain).

Outputs per run:

- `output/run-<timestamp>/jobs.json` — master index + embedded tailored content
- `output/run-<timestamp>/jobs.csv` — Google-Sheets-friendly summary (one row per job, sorted by status + fit score)
- `output/run-<timestamp>/jobs/<slug>/` — `job.json`, `resume.md`, `resume.tex`, `resume.pdf`, `cover_letter.md`, `cover_letter.tex`, `cover_letter.pdf`

PDFs are always produced thanks to a three-tier fallback (`pandoc` → `weasyprint` → `fpdf2`); install pandoc or `pango` for nicer output. `tectonic` / `pdflatex` (when installed) additionally produce the styled LaTeX PDFs (`resume.pdf`, `cover_letter.pdf` from the LaTeX templates).

**Deduping & resume**

- Workspace-local ledger at `./.jobapply/ledger.db` (gitignored) skips jobs already completed for the same `profile.md` hash. Override with `ledger_path = "..."` in `jobapply.toml` if you want a shared/global ledger.
- Re-runs that hit the ledger emit a `cached` `JobRecord` into `jobs.json` so the run dir is never empty. Pass `--force` to ignore the ledger and re-process everything.
- Each run stores `meta.json` (search snapshot). `jobapply resume run-...` skips network search and rebuilds the work queue from `meta.json` + ledger (by default removes `checkpoint.sqlite` so processing restarts cleanly after failures).

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

jobapply init           # interactive: pick provider, paste keys, choose model
# Optional: import an existing resume instead of editing profile.md by hand:
# jobapply init --resume ~/Downloads/resume.pdf   # .md / .txt / .docx / .pdf
# edit profile.md if needed

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

### PDF rendering

Resumes and cover letters are always exported as PDFs. The CLI prints which backend is active at run start:

| Tier | Backend | Quality | Install |
|------|---------|---------|---------|
| 1 | [Pandoc](https://pandoc.org/) (+ a TeX engine) | best | `brew install pandoc` (+ MacTeX/Tectonic) |
| 2 | [WeasyPrint](https://weasyprint.org/) | good HTML/CSS | `brew install pango` (Python deps installed automatically) |
| 3 | [`fpdf2`](https://py-pdf.github.io/fpdf2/) | basic, pure Python | bundled — always works |

Tiers 2 and 3 ship with the package, so PDFs work out of the box even without pandoc or LaTeX. The styled MTeck-themed LaTeX PDFs (`resume.pdf` / `cover_letter.pdf` from `*.tex`) require [Tectonic](https://tectonic-typesetting.github.io/) or `pdflatex` on `PATH`. Use `--no-pdf` to skip PDF generation entirely.

### Spreadsheet export

After every run, `jobapply` writes `output/run-<id>/jobs.csv` with one row per job — title, company, status, fit score, missing keywords, apply URL, and absolute paths to every generated artifact (resume MD/PDF/TeX, cover letter MD/PDF/TeX). Rows are sorted **done → cached → skipped → failed** with the highest-fit jobs at the top, so importing into Google Sheets via **File → Import → Upload** surfaces the most actionable jobs immediately. URL and path columns work directly with `=HYPERLINK(D2, "open")` formulas.

## Commands

| Command | Description |
|---------|-------------|
| `jobapply init` | Interactive setup: provider + connection details + starter `profile.md`. Pass `--resume <path>` (`.md` / `.txt` / `.docx` / `.pdf`, including LinkedIn PDF export) to auto-generate `profile.md` from an existing resume — the configured LLM cleans it up; without a key it falls back to embedding the raw text. `--non-interactive` writes a blank template. |
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

Bundled LaTeX templates:

- `jobapply/templates/resume.tex` — adapted from Michael Lustfield's MTeck resume, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/legalcode.txt).
- `jobapply/templates/cover_letter.tex` — adapted from Jayesh Sanwal's entry-level cover-letter template (CC BY 4.0).

Your `profile.md` content remains yours.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
