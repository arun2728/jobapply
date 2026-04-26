"""Tests for workspace-local ledger path resolution."""

from __future__ import annotations

from pathlib import Path

from jobapply.cli import _ledger_db_path
from jobapply.config import AppConfig
from jobapply.ledger import default_ledger_path


def test_default_ledger_lives_in_workspace_dot_jobapply(tmp_path: Path) -> None:
    expected = tmp_path / ".jobapply" / "ledger.db"
    assert default_ledger_path(tmp_path) == expected
    assert (tmp_path / ".jobapply").is_dir()


def test_cli_default_uses_cwd_dot_jobapply(tmp_path: Path) -> None:
    cfg = AppConfig()
    assert _ledger_db_path(cfg, cwd=tmp_path) == tmp_path / ".jobapply" / "ledger.db"


def test_cli_relative_ledger_path_resolved_to_cwd(tmp_path: Path) -> None:
    cfg = AppConfig(ledger_path="my-ledger.db")
    resolved = _ledger_db_path(cfg, cwd=tmp_path)
    assert resolved == tmp_path / "my-ledger.db"


def test_cli_absolute_ledger_path_preserved(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere" / "ledger.db"
    cfg = AppConfig(ledger_path=str(target))
    resolved = _ledger_db_path(cfg, cwd=tmp_path)
    assert resolved == target
    assert target.parent.is_dir()


def test_cli_ledger_path_expands_user(tmp_path: Path, monkeypatch) -> None:
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    cfg = AppConfig(ledger_path="~/jobs/ledger.db")
    resolved = _ledger_db_path(cfg, cwd=tmp_path)
    assert resolved == fake_home / "jobs" / "ledger.db"
