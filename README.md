# JobApply

Open-source CLI to **search jobs** ([JobSpy](https://github.com/speedyapply/python-jobspy): Indeed, LinkedIn, Google Jobs, etc.), then run a **LangGraph** pipeline that scores fit, **tailors your resume** and **writes a cover letter** from a structured `profile.json` using **Gemini**, **Anthropic**, **OpenAI** (and any OpenAI-compatible gateway), **Ollama**, or **Cloudflare Workers AI** (structured outputs via LangChain).

Outputs per run:

- `output/run-<timestamp>/jobs.json` — master index + embedded tailored content
- `output/run-<timestamp>/jobs.csv` — Google-Sheets-friendly summary (one row per job, sorted by status + fit score)
- `output/run-<timestamp>/jobs/<slug>/` — `job.json`, `resume.md`, `resume.tex`, `resume.pdf`, `cover_letter.md`, `cover_letter.tex`, `cover_letter.pdf`

PDFs are always produced. Markdown PDFs go through a three-tier fallback (`pandoc` → `weasyprint` → `fpdf2`); install pandoc or `pango` for nicer output. The styled LaTeX PDFs (`resume.pdf`, `cover_letter.pdf` rendered from the bundled LaTeX templates) are compiled via a remote [`latex-on-http`](https://github.com/YtoTech/latex-on-http) service by default, so no local TeX install is required — `tectonic` / `pdflatex` are still used as fallbacks if the API is disabled or unreachable.

**Deduping & resume**

- Workspace-local ledger at `./.jobapply/ledger.db` (gitignored) skips jobs already completed for the same `profile.json` hash. Override with `ledger_path = "..."` in `jobapply.toml` if you want a shared/global ledger.
- Re-runs that hit the ledger emit a `cached` `JobRecord` into `jobs.json` so the run dir is never empty. Pass `--force` to ignore the ledger and re-process everything.
- Each run stores `meta.json` (search snapshot). `jobapply resume run-...` skips network search and rebuilds the work queue from `meta.json` + ledger (by default removes `checkpoint.sqlite` so processing restarts cleanly after failures).

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Interactive setup. A resume is mandatory: pass --resume PATH or paste it in.
jobapply init --resume ~/Downloads/resume.pdf   # .md / .txt / .docx / .pdf
# Or paste resume text directly when you don't have a file:
# jobapply init --paste

jobapply run --titles "Backend Engineer,ML Engineer" --skills "Python,Kubernetes" --location "Remote" --yes
```

`jobapply init` writes `jobapply.toml` and a structured `profile.json` extracted from your resume by the configured LLM. Open `profile.json` to fine-tune any field (name/email/links, experience bullets, skills, education entries with GPA & coursework, projects, etc.) — every key in the [`Profile` schema](jobapply/profile.py) maps 1:1 to what the resume tailor sees. Use `jobapply config` later to change provider/credentials, or `jobapply config --show` to print the resolved config.

> Heads-up: `jobapply init` always calls your configured LLM to populate `profile.json`. Make sure your provider's API key works (or run an Ollama server locally) before invoking it. There is no Markdown fallback — the JSON is the source of truth.

### `profile.json` schema

The full Pydantic schema lives in [`jobapply/profile.py`](jobapply/profile.py). At a glance:

```jsonc
{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "phone": "+1 555 123 4567",
  "location": "San Francisco, CA",

  "portfolio": "https://jane.dev",
  "github": "janedev",                  // bare handle or full URL
  "linkedin": "https://linkedin.com/in/janedev",
  "medium": "",
  "twitter": "",
  "other_links": [
    { "label": "Dev.to", "url": "https://dev.to/janedev" }
  ],

  "summary": "Engineer with 5 yoe in distributed systems.",
  "skills": ["Python", "Kubernetes", "Model Context Protocol (MCP)"],

  "experience": [
    {
      "company": "Acme",
      "role": "Senior Engineer",
      "location": "Remote",
      "start_date": "2024",
      "end_date": "Present",
      "bullets": ["Cut p99 latency 4×", "Led migration to gRPC"]
    }
  ],

  "projects": [
    {
      "name": "openai-tools",
      "description": "Tiny CLI for OpenAI function calling.",
      "url": "https://github.com/janedev/openai-tools",
      "tech": ["Python", "Click"],
      "bullets": ["1.2k stars", "Used by Acme internally"]
    }
  ],

  "education": [
    {
      "school": "MIT",
      "degree": "B.S. CS",
      "start_date": "2018",
      "end_date": "2022",
      "gpa": "3.85/4.0",
      "coursework": ["Operating Systems", "Machine Learning"],
      "honors": "Dean's list"
    }
  ]
}
```

Empty list / empty string fields are allowed; the CLI prints required-vs-recommended warnings (`name`, `email`, `experience`, `education` are required) but never blocks the run.

### Configuration

`jobapply.toml` holds the active provider, model defaults, and per-provider connection details. Every secret accepts an indirection: `api_key = "env:OPENAI_API_KEY"` reads the value from the environment at runtime instead of storing it in the file. See [`jobapply.toml.example`](jobapply.toml.example) for a fully documented template covering all five providers.

| Provider | Required keys | Notes |
|----------|---------------|-------|
| `gemini` | `api_key` (or `GOOGLE_API_KEY` / `GEMINI_API_KEY` env) | |
| `anthropic` | `api_key` (or `ANTHROPIC_API_KEY` env) | optional `base_url` |
| `openai` | `api_key` (or `OPENAI_API_KEY` env) | `base_url` for OpenAI-compatible gateways (Azure, Together, Groq, …) |
| `ollama` | none | local; configure `base_url` (default `http://127.0.0.1:11434`) |
| `cloudflare` | `api_key` (Workers AI token, or `CLOUDFLARE_API_TOKEN` env) **and** `account_id` (or `CLOUDFLARE_ACCOUNT_ID` env) | Two routing modes — see below |

#### Cloudflare routing modes

`jobapply` supports both Cloudflare entry points; pick one by deciding whether to set `gateway_id` (or `CLOUDFLARE_AI_GATEWAY_ID`).

| Mode | When to use | `model` format | Example |
|------|-------------|----------------|---------|
| Direct Workers AI (`gateway_id` **unset**) | Calling Cloudflare's natively hosted models | `@cf/<vendor>/<name>` — see [Workers AI models](https://developers.cloudflare.com/workers-ai/models/) | `@cf/openai/gpt-oss-120b` |
| AI Gateway Unified API (`gateway_id` **set**) | Calling third-party models via BYOK keys you've configured in the gateway's [Stored Keys](https://developers.cloudflare.com/ai-gateway/configuration/bring-your-own-keys/) | `<provider>/<model>` — see the [Unified API docs](https://developers.cloudflare.com/ai-gateway/usage/chat-completion/) | `openai/gpt-5`, `anthropic/claude-3-5-sonnet`, `workers-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast` |

> If you hit `AiError: No such model: ... openai/gpt-5` on the direct endpoint, you're in mode 1 — either switch the model to a `@cf/...` id, or create an AI Gateway, store your OpenAI key under "Stored Keys", and set `gateway_id` to switch to mode 2.

`jobapply.toml` is gitignored by default. If you prefer env-only secrets, copy `.env.example` to `.env` and leave `api_key` lines commented out (or use `env:VAR_NAME`).

### PDF rendering

Resumes and cover letters are always exported as PDFs through two independent pipelines. The CLI prints which backend each one will use at run start:

```text
Markdown PDF backend: weasyprint (good)
LaTeX PDF backend:    latex-on-http (https://latex.ytotech.com/builds/sync)
```

#### Markdown → PDF (always available)

Markdown copies of the resume and cover letter (`resume.md`, `cover_letter.md`) are rendered with a three-tier fallback. Tiers 2 and 3 ship with the package, so PDFs work out of the box.

| Tier | Backend | Quality | Install |
|------|---------|---------|---------|
| 1 | [Pandoc](https://pandoc.org/) (+ a TeX engine) | best | `brew install pandoc` (+ MacTeX/Tectonic) |
| 2 | [WeasyPrint](https://weasyprint.org/) | good HTML/CSS | `brew install pango` (Python deps installed automatically) |
| 3 | [`fpdf2`](https://py-pdf.github.io/fpdf2/) | basic, pure Python | bundled — always works |

#### LaTeX → PDF (no local TeX needed)

The styled MTeck-themed LaTeX templates (`resume.tex`, `cover_letter.tex`) are compiled to PDF via a [`latex-on-http`](https://github.com/YtoTech/latex-on-http) HTTP API. By default `jobapply` POSTs the `.tex` content to the public instance at `latex.ytotech.com` and writes the returned PDF — **no Tectonic, MacTeX, or `pdflatex` install required**. Local engines are still tried as fallbacks.

| Tier | Backend | Notes |
|------|---------|-------|
| 1 | [`latex-on-http`](https://github.com/YtoTech/latex-on-http) (remote) | Default. Configurable in `[latex_api]`; supports self-hosting (see below). |
| 2 | [Tectonic](https://tectonic-typesetting.github.io/) | Used when API is disabled / unreachable. Auto-fetches missing TeX packages. |
| 3 | `pdflatex` | Last-resort fallback (full TeX Live install). |

Configure the LaTeX-PDF backend in `jobapply.toml`:

```toml
[latex_api]
enabled  = true
url      = "https://latex.ytotech.com/builds/sync"
compiler = "pdflatex"   # pdflatex | xelatex | lualatex | latexmk
timeout  = 120.0
```

Each setting can also be overridden at runtime via env vars: `JOBAPPLY_LATEX_API_URL`, `JOBAPPLY_LATEX_API_DISABLE`, `JOBAPPLY_LATEX_API_COMPILER`, `JOBAPPLY_LATEX_API_TIMEOUT` (env wins over TOML so shell overrides are non-destructive).

**Self-host (recommended for privacy / reliability).** Your tailored `.tex` contains personal info; if you'd rather not send it to a third-party server, run the same image yourself:

```bash
docker run -d -p 8080:8080 yotools/latex-on-http
# then in jobapply.toml:
# [latex_api]
# url = "http://localhost:8080/builds/sync"
```

To skip PDF generation entirely, pass `--no-pdf` to `jobapply run` / `jobapply resume`.

### Spreadsheet export

After every run, `jobapply` writes `output/run-<id>/jobs.csv` with one row per job — title, company, status, fit score, missing keywords, apply URL, and absolute paths to every generated artifact (resume MD/PDF/TeX, cover letter MD/PDF/TeX). Rows are sorted **done → cached → skipped → failed** with the highest-fit jobs at the top, so importing into Google Sheets via **File → Import → Upload** surfaces the most actionable jobs immediately. URL and path columns work directly with `=HYPERLINK(D2, "open")` formulas.

## Commands

| Command | Description |
|---------|-------------|
| `jobapply init` | Interactive setup: provider + connection details + structured `profile.json`. **A resume is required**: pass `--resume <path>` (`.md` / `.txt` / `.docx` / `.pdf`, including LinkedIn PDF export) or `--paste` (read text from stdin / multiline prompt). The configured LLM extracts the resume into the [`Profile` schema](jobapply/profile.py) via structured output, so make sure your provider key is reachable before running it. `--non-interactive` skips provider prompts but still requires `--resume` or `--paste`. |
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

Your `profile.json` content remains yours.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
