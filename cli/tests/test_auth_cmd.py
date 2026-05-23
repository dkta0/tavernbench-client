"""Tests for the `tavernbench auth` Typer subcommand."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent))

from tavernbench_cli import config as cfg
from tavernbench_cli.main import app


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.toml")
    return tmp_path


def test_auth_saves_key_from_flag(isolated_config: Path) -> None:
    result = CliRunner().invoke(app, ["auth", "--key", "tb_fresh_key"])
    assert result.exit_code == 0
    assert cfg.get_api_key() == "tb_fresh_key"


def test_auth_overwrite_aborts_when_user_declines(isolated_config: Path) -> None:
    cfg.set_api_key("tb_original")
    result = CliRunner().invoke(app, ["auth", "--key", "tb_new"], input="n\n")
    assert result.exit_code == 0
    assert cfg.get_api_key() == "tb_original"


def test_auth_overwrite_replaces_when_user_confirms(isolated_config: Path) -> None:
    cfg.set_api_key("tb_original")
    result = CliRunner().invoke(app, ["auth", "--key", "tb_new"], input="y\n")
    assert result.exit_code == 0
    assert cfg.get_api_key() == "tb_new"
