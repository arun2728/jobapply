# Changelog

All notable changes to JobApply are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Product Hunt launch kit, marketing assets, and a VHS tape script for the
  terminal demo (`assets/`).
- `CODE_OF_CONDUCT.md`, `SECURITY.md`, GitHub issue templates, and a pull
  request template.
- README hero image, gallery screenshots, and badges.

### Changed
- Tightened `.gitignore` so personal artifacts (`Profile_Updated.md`,
  `LinkedInProfile*`, `*-test.pdf`, etc.) cannot be accidentally committed.

## [0.1.0] - Unreleased

- Initial public release: JobSpy search, LangGraph pipeline, ledger dedupe,
  SQLite checkpoints, structured `profile.json`, Gemini / Anthropic / OpenAI
  / Ollama / Cloudflare Workers AI providers, Markdown + LaTeX PDF export
  (with remote `latex-on-http` default), CSV export sorted by fit score,
  and `jobapply resume` to continue from a previous run's `meta.json`.
