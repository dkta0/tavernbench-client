"""Tests for tavernbench install <client>."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add cli/ to sys.path so we can import tavernbench_cli directly without a pip install.
CLI_DIR = Path(__file__).resolve().parents[1]
if str(CLI_DIR) not in sys.path:
    sys.path.insert(0, str(CLI_DIR))

from tavernbench_cli import install_cmd


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


# ── claude-code ───────────────────────────────────────────────────────────────

class TestInstallClaudeCode:
    def test_creates_mcp_json_fresh(self, tmp_path, monkeypatch):
        monkeypatch.setattr(install_cmd, "_real_home", lambda: tmp_path)
        install_cmd.install_claude_code()
        cfg = read_json(tmp_path / ".claude" / "mcp.json")
        assert "tavernbench" in cfg["mcpServers"]
        entry = cfg["mcpServers"]["tavernbench"]
        assert entry["type"] == "stdio"
        assert "tavernbench" in entry["command"] or "tavernbench" in str(entry["args"])

    def test_adds_to_existing_mcp_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(install_cmd, "_real_home", lambda: tmp_path)
        cfg_path = tmp_path / ".claude" / "mcp.json"
        cfg_path.parent.mkdir(parents=True)
        cfg_path.write_text(json.dumps({"mcpServers": {"other": {"type": "stdio", "command": "other"}}}))
        install_cmd.install_claude_code()
        cfg = read_json(cfg_path)
        assert "other" in cfg["mcpServers"]
        assert "tavernbench" in cfg["mcpServers"]

    def test_dry_run_does_not_write(self, tmp_path, monkeypatch):
        monkeypatch.setattr(install_cmd, "_real_home", lambda: tmp_path)
        install_cmd.install_claude_code(dry_run=True)
        assert not (tmp_path / ".claude" / "mcp.json").exists()

    def test_local_flag_writes_to_cwd(self, tmp_path, monkeypatch):
        monkeypatch.setattr(install_cmd, "_real_home", lambda: tmp_path)
        monkeypatch.chdir(tmp_path)
        install_cmd.install_claude_code(local=True)
        cfg = read_json(tmp_path / ".claude" / "mcp.json")
        assert "tavernbench" in cfg["mcpServers"]

    def test_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(install_cmd, "_real_home", lambda: tmp_path)
        install_cmd.install_claude_code()
        install_cmd.install_claude_code()
        cfg = read_json(tmp_path / ".claude" / "mcp.json")
        assert list(cfg["mcpServers"].keys()).count("tavernbench") == 1


# ── cursor ────────────────────────────────────────────────────────────────────

class TestInstallCursor:
    def test_creates_mcp_json_fresh(self, tmp_path, monkeypatch):
        monkeypatch.setattr(install_cmd, "_real_home", lambda: tmp_path)
        install_cmd.install_cursor()
        cfg = read_json(tmp_path / ".cursor" / "mcp.json")
        assert "tavernbench" in cfg["mcpServers"]
        entry = cfg["mcpServers"]["tavernbench"]
        # Cursor schema: no "type" key
        assert "type" not in entry
        assert "command" in entry

    def test_dry_run_does_not_write(self, tmp_path, monkeypatch):
        monkeypatch.setattr(install_cmd, "_real_home", lambda: tmp_path)
        install_cmd.install_cursor(dry_run=True)
        assert not (tmp_path / ".cursor" / "mcp.json").exists()

    def test_local_flag_writes_to_cwd(self, tmp_path, monkeypatch):
        monkeypatch.setattr(install_cmd, "_real_home", lambda: tmp_path)
        monkeypatch.chdir(tmp_path)
        install_cmd.install_cursor(local=True)
        cfg = read_json(tmp_path / ".cursor" / "mcp.json")
        assert "tavernbench" in cfg["mcpServers"]


# ── codex ─────────────────────────────────────────────────────────────────────

class TestInstallCodex:
    def test_creates_config_fresh(self, tmp_path, monkeypatch):
        monkeypatch.setattr(install_cmd, "_real_home", lambda: tmp_path)
        install_cmd.install_codex()
        cfg = read_json(tmp_path / ".codex" / "config.json")
        assert "tavernbench" in cfg["mcpServers"]
        entry = cfg["mcpServers"]["tavernbench"]
        assert entry["type"] == "stdio"

    def test_dry_run_does_not_write(self, tmp_path, monkeypatch):
        monkeypatch.setattr(install_cmd, "_real_home", lambda: tmp_path)
        install_cmd.install_codex(dry_run=True)
        assert not (tmp_path / ".codex" / "config.json").exists()

    def test_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(install_cmd, "_real_home", lambda: tmp_path)
        install_cmd.install_codex()
        install_cmd.install_codex()
        cfg = read_json(tmp_path / ".codex" / "config.json")
        assert list(cfg["mcpServers"].keys()).count("tavernbench") == 1


# ── run() dispatcher ──────────────────────────────────────────────────────────

class TestRunDispatcher:
    def test_unknown_client_exits(self, tmp_path, monkeypatch):
        monkeypatch.setattr(install_cmd, "_real_home", lambda: tmp_path)
        with pytest.raises(SystemExit):
            install_cmd.run("unknown-client")

    def test_routes_to_claude_code(self, tmp_path, monkeypatch):
        monkeypatch.setattr(install_cmd, "_real_home", lambda: tmp_path)
        install_cmd.run("claude-code")
        assert (tmp_path / ".claude" / "mcp.json").exists()

    def test_routes_to_cursor(self, tmp_path, monkeypatch):
        monkeypatch.setattr(install_cmd, "_real_home", lambda: tmp_path)
        install_cmd.run("cursor")
        assert (tmp_path / ".cursor" / "mcp.json").exists()

    def test_routes_to_codex(self, tmp_path, monkeypatch):
        monkeypatch.setattr(install_cmd, "_real_home", lambda: tmp_path)
        install_cmd.run("codex")
        assert (tmp_path / ".codex" / "config.json").exists()
