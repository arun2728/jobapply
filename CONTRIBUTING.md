# Contributing

Thanks for helping improve JobApply.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Checks

```bash
ruff check jobapply tests
black --check jobapply tests
mypy jobapply
pytest
```

## Pull requests

- Keep changes focused; update `CHANGELOG.md` for user-visible changes.
- Do not commit API keys or personal `profile.md` contents.
