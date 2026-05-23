"""
tavernbench install <client>

Registers the TavernBench MCP server with the target client's config.

Supported clients:
  claude-code   ~/.claude/mcp.json
  cursor        ~/.cursor/mcp.json  (or .cursor/mcp.json in workspace if --local)
  codex         ~/.codex/config.json (openai/codex)
"""
from __future__ import annotations

import json
import os
import pwd
import sys
from pathlib import Path
from typing import Optional

# ── Real home resolution ──────────────────────────────────────────────────────

def _real_home() -> Path:
    """Return the user's real home from /etc/passwd, ignoring $HOME."""
    return Path(pwd.getpwuid(os.getuid()).pw_dir)

# ── MCP server descriptor ────────────────────────────────────────────────────

MCP_SERVER_NAME = "tavernbench"
MCP_SERVER_DESCRIPTION = "TavernBench arena — play and benchmark AI agents in a text RPG"


def _mcp_command() -> list[str]:
    """Return the command array the MCP client should invoke."""
    # Prefer the installed CLI entry point; fall back to python -m invocation.
    tb_bin = shutil_which("tavernbench")
    if tb_bin:
        return [tb_bin, "mcp", "serve"]
    # If running from the repo (dev install)
    repo_root = Path(__file__).resolve().parents[2]
    return [sys.executable, "-m", "tavernbench_cli.main", "mcp", "serve"]


def _mcp_entry() -> dict:
    cmd = _mcp_command()
    return {
        "type": "stdio",
        "command": cmd[0],
        "args": cmd[1:],
        "description": MCP_SERVER_DESCRIPTION,
    }


# ── helpers ───────────────────────────────────────────────────────────────────

def shutil_which(name: str) -> Optional[str]:
    import shutil
    return shutil.which(name)


def _read_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _confirm_write(path: Path, dry_run: bool) -> bool:
    if dry_run:
        print(f"[dry-run] would write: {path}")
        return False
    return True


# ── per-client installers ─────────────────────────────────────────────────────

def install_claude_code(local: bool = False, dry_run: bool = False) -> None:
    """
    Write to ~/.claude/mcp.json.

    Schema expected by Claude Code:
      {
        "mcpServers": {
          "<name>": {
            "type": "stdio",
            "command": "<cmd>",
            "args": [...]
          }
        }
      }
    """
    if local:
        config_path = Path.cwd() / ".claude" / "mcp.json"
    else:
        config_path = _real_home() / ".claude" / "mcp.json"

    data = _read_json(config_path)
    if "mcpServers" not in data:
        data["mcpServers"] = {}

    if MCP_SERVER_NAME in data["mcpServers"] and not _already_registered_check(
        data["mcpServers"][MCP_SERVER_NAME]
    ):
        print(
            f"  ! {config_path} already has '{MCP_SERVER_NAME}' entry (non-tavernbench). "
            "Pass --force to overwrite."
        )
        return

    data["mcpServers"][MCP_SERVER_NAME] = _mcp_entry()

    if _confirm_write(config_path, dry_run):
        _write_json(config_path, data)
        print(f"  ✓ Registered '{MCP_SERVER_NAME}' MCP server → {config_path}")
        print(f"    Restart Claude Code to pick up the new server.")


def install_cursor(local: bool = False, dry_run: bool = False) -> None:
    """
    Write to ~/.cursor/mcp.json (global) or .cursor/mcp.json (local/project).

    Schema expected by Cursor:
      {
        "mcpServers": {
          "<name>": {
            "command": "<cmd>",
            "args": [...]
          }
        }
      }
    """
    if local:
        config_path = Path.cwd() / ".cursor" / "mcp.json"
    else:
        config_path = _real_home() / ".cursor" / "mcp.json"

    data = _read_json(config_path)
    if "mcpServers" not in data:
        data["mcpServers"] = {}

    entry = _mcp_entry()
    # Cursor schema omits "type": "stdio" (implied), so drop it
    cursor_entry = {k: v for k, v in entry.items() if k != "type"}
    data["mcpServers"][MCP_SERVER_NAME] = cursor_entry

    if _confirm_write(config_path, dry_run):
        _write_json(config_path, data)
        print(f"  ✓ Registered '{MCP_SERVER_NAME}' MCP server → {config_path}")
        print(f"    Restart Cursor to pick up the new server.")


def install_codex(local: bool = False, dry_run: bool = False) -> None:
    """
    Write to ~/.codex/config.json.

    OpenAI Codex CLI schema for MCP servers:
      {
        "mcpServers": {
          "<name>": {
            "type": "stdio",
            "command": "<cmd>",
            "args": [...]
          }
        }
      }
    """
    if local:
        config_path = Path.cwd() / ".codex" / "config.json"
    else:
        config_path = _real_home() / ".codex" / "config.json"

    data = _read_json(config_path)
    if "mcpServers" not in data:
        data["mcpServers"] = {}

    data["mcpServers"][MCP_SERVER_NAME] = _mcp_entry()

    if _confirm_write(config_path, dry_run):
        _write_json(config_path, data)
        print(f"  ✓ Registered '{MCP_SERVER_NAME}' MCP server → {config_path}")
        print(f"    The server will be available on next codex invocation.")


def _already_registered_check(existing_entry: dict) -> bool:
    """Return True if the existing entry looks like it was written by us."""
    desc = existing_entry.get("description", "")
    cmd_str = str(existing_entry.get("command", ""))
    args_str = str(existing_entry.get("args", []))
    return "tavernbench" in desc.lower() or "tavernbench" in cmd_str or "tavernbench" in args_str


# ── public entry point ────────────────────────────────────────────────────────

SUPPORTED_CLIENTS = {
    "claude-code": install_claude_code,
    "cursor": install_cursor,
    "codex": install_codex,
}


def run(client: str, local: bool = False, dry_run: bool = False) -> None:
    """
    Register the TavernBench MCP server with `client`.

    client  — one of: claude-code, cursor, codex
    local   — write to workspace-local config (.cursor/mcp.json, etc.)
    dry_run — print what would be written without changing anything
    """
    client = client.lower().strip()
    if client not in SUPPORTED_CLIENTS:
        print(
            f"Unknown client '{client}'. Supported: {', '.join(SUPPORTED_CLIENTS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"==> Registering TavernBench MCP server for {client}...")
    SUPPORTED_CLIENTS[client](local=local, dry_run=dry_run)
