"""Tests for tavernbench_cli.config."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the package under test is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from tavernbench_cli import config as cfg


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    """Redirect CONFIG_DIR/CONFIG_FILE into a tmp dir for each test."""
    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.toml")
    return tmp_path


def test_load_empty(isolated_config: Path) -> None:
    assert cfg.load() == {}


def test_set_and_get_api_key(isolated_config: Path) -> None:
    cfg.set_api_key("tb_test_key_12345")
    assert cfg.get_api_key() == "tb_test_key_12345"


def test_config_toml_contents(isolated_config: Path) -> None:
    cfg.set_api_key("tb_abc")
    contents = (isolated_config / "config.toml").read_text()
    assert "[auth]" in contents
    assert "api_key" in contents
    assert "tb_abc" in contents


def test_overwrite_key(isolated_config: Path) -> None:
    cfg.set_api_key("old_key")
    cfg.set_api_key("new_key")
    assert cfg.get_api_key() == "new_key"


def test_no_key_returns_none(isolated_config: Path) -> None:
    assert cfg.get_api_key() is None


def test_require_api_key_exits_when_missing(isolated_config: Path) -> None:
    with pytest.raises(SystemExit):
        cfg.require_api_key()


def test_require_api_key_returns_key(isolated_config: Path) -> None:
    cfg.set_api_key("tb_xyz")
    assert cfg.require_api_key() == "tb_xyz"
