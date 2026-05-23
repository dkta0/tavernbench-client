"""
Config helpers for the TavernBench CLI.

Config file: ~/.config/tavernbench/config.toml

[auth]
api_key = "tb_..."

All CLI subcommands and the MCP server read from here.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONFIG_DIR = Path(os.environ.get("TAVERNBENCH_CONFIG_DIR", Path.home() / ".config" / "tavernbench"))
CONFIG_FILE = CONFIG_DIR / "config.toml"


# ---------------------------------------------------------------------------
# Minimal TOML read/write (stdlib tomllib on 3.11+, fallback on older)
# ---------------------------------------------------------------------------

def _read_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    if sys.version_info >= (3, 11):
        import tomllib
        with open(path, "rb") as f:
            return tomllib.load(f)
    else:
        # Manual parse — only needs to handle our own simple config.
        data: dict = {}
        section: dict = data
        section_name: str | None = None
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    section_name = line[1:-1].strip()
                    if section_name not in data:
                        data[section_name] = {}
                    section = data[section_name]
                elif "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    # Strip surrounding quotes from strings
                    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
                        value = value[1:-1]
                    elif len(value) >= 2 and value[0] == "'" and value[-1] == "'":
                        value = value[1:-1]
                    section[key] = value
        return data


def _write_toml(path: Path, data: dict) -> None:
    """Write a simple two-level dict as TOML."""
    lines: list[str] = []
    # Top-level scalar keys first (rarely used in our config but correct)
    for key, value in data.items():
        if not isinstance(value, dict):
            lines.append(f'{key} = "{value}"')
    # Sections
    for section, contents in data.items():
        if not isinstance(contents, dict):
            continue
        lines.append(f"\n[{section}]")
        for key, value in contents.items():
            lines.append(f'{key} = "{value}"')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).strip() + "\n")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load() -> dict:
    """Return the full config dict. Empty dict if no config file exists."""
    return _read_toml(CONFIG_FILE)


def save(data: dict) -> None:
    """Overwrite the config file with *data*."""
    _write_toml(CONFIG_FILE, data)


def get_api_key() -> str | None:
    """Return the stored API key, or None if not configured."""
    cfg = load()
    return cfg.get("auth", {}).get("api_key") or None


def set_api_key(key: str) -> None:
    """Persist *key* under [auth] api_key. Merges with existing config."""
    cfg = load()
    if "auth" not in cfg:
        cfg["auth"] = {}
    cfg["auth"]["api_key"] = key
    save(cfg)


def require_api_key() -> str:
    """Return the API key or exit with an error message."""
    key = get_api_key()
    if not key:
        print("Error: no API key configured. Run `tavernbench auth` first.", file=sys.stderr)
        sys.exit(1)
    return key
