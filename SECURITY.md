# Security Policy

JobApply runs locally on your machine and processes sensitive personal data
(your resume, profile, and the contents of jobs you search). We take
security and privacy seriously.

## Supported Versions

JobApply is in active early development. Security fixes are applied to the
`main` branch and the latest published release.

| Version | Supported          |
| ------- | ------------------ |
| `main`  | :white_check_mark: |
| `0.1.x` | :white_check_mark: |
| `<0.1`  | :x:                |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security problems.**

Instead, report vulnerabilities privately via GitHub's
[security advisory form](https://github.com/arun2728/jobapply/security/advisories/new).

When reporting, please include:

- A description of the vulnerability and its impact
- Steps to reproduce (a minimal proof-of-concept is ideal)
- Any suggested mitigations or patches you've already explored
- Your name / handle if you'd like credit in the release notes

We aim to acknowledge reports within **72 hours** and to ship a fix or
mitigation within **30 days** for confirmed issues. We will coordinate
disclosure timing with you.

## Data Handling Notes

A few things contributors and users should keep in mind:

- `profile.json`, `profile.md`, and `output/` contain personal data and are
  excluded by `.gitignore`. **Never commit them.**
- `jobapply.toml` may contain API keys and is also gitignored. Prefer
  `env:VAR_NAME` indirections or a local `.env` file (also gitignored).
- The default LaTeX-PDF backend POSTs your tailored `.tex` content to a
  third-party service (`latex.ytotech.com`). For sensitive data, self-host
  `latex-on-http` (see the README "PDF rendering" section) and point
  `[latex_api].url` at your local instance.
- Outbound LLM requests carry your tailored resume / job description text.
  Use a local provider (e.g. Ollama) if you don't want any third party to
  see this content.

## Scope

In scope:

- Code in this repository (`jobapply/` package, CLI, templates).
- Default configuration shipped with the package.
- Documented integration points (LLM providers, LaTeX API, JobSpy).

Out of scope:

- Vulnerabilities in upstream dependencies (please report those upstream;
  we will pin a fixed version once available).
- Issues that require an attacker to already have local code execution on
  the user's machine.
