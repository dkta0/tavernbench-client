"""
tavernbench doctor [--fix]

Health checks:
  1. API key configured
  2. Server reachable (HTTP ping)
  3. MCP server registered with detected client(s)

With --fix: creates ~/.config/tavernbench symlink so Path.home()-based paths
reach the real home directory even when $HOME is overridden (e.g. a profile
sandbox sets HOME to a non-standard directory).

Bug fixed here: Path.home() (and os.path.expanduser) resolve against $HOME,
but the *real* home is the passwd entry for the current user. When $HOME is
overridden (e.g. to ~/.hermes/profiles/coder/home), symlinks or config files
get written to the wrong place.  We use pwd.getpwuid(os.getuid()).pw_dir to
get the authoritative real home, independent of $HOME.
"""
from __future__ import annotations

import os
import pwd
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Real home resolution — the core fix
# ---------------------------------------------------------------------------

def real_home() -> Path:
    """Return the user's real home directory from the passwd database.

    This is intentionally different from Path.home() / os.path.expanduser('~'),
    which both honour the $HOME environment variable.  When $HOME is overridden
    (profile sandboxes, sudo, etc.) those functions return the wrong directory.
    """
    return Path(pwd.getpwuid(os.getuid()).pw_dir)


def profile_home() -> Path:
    """Return whatever $HOME is currently set to (may equal real_home)."""
    return Path.home()


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_api_key() -> tuple[bool, str]:
    """Return (ok, message)."""
    try:
        from . import config as _cfg
        key = _cfg.get_api_key()
    except Exception as exc:
        return False, f"config read error: {exc}"
    if key:
        masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
        return True, f"API key configured ({masked})"
    return False, "no API key — run `tavernbench auth`"


def check_server(host: str = "tavernbench.dkta.dev") -> tuple[bool, str]:
    """Try an HTTP GET to the server health endpoint."""
    import urllib.request
    import urllib.error
    url = f"https://{host}/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            if resp.status == 200:
                return True, f"server reachable ({host})"
            return False, f"server returned HTTP {resp.status}"
    except urllib.error.URLError as exc:
        return False, f"server unreachable: {exc.reason}"
    except Exception as exc:
        return False, f"server check failed: {exc}"


def check_mcp_registered() -> tuple[bool, str]:
    """Check whether any supported MCP client config contains tavernbench."""
    rh = real_home()
    candidates = {
        "claude-code": rh / ".claude" / "mcp.json",
        "cursor":      rh / ".cursor" / "mcp.json",
        "codex":       rh / ".codex" / "config.json",
    }
    found = []
    for client, path in candidates.items():
        if path.exists() and "tavernbench" in path.read_text(errors="replace"):
            found.append(client)
    if found:
        return True, f"MCP registered in: {', '.join(found)}"
    return False, "MCP server not registered — run `tavernbench install <client>`"


# ---------------------------------------------------------------------------
# --fix: ensure config is reachable from both real and profile home
# ---------------------------------------------------------------------------

def fix_home_symlink() -> tuple[bool, str]:
    """If $HOME != real home, create a symlink so config is reachable from both.

    Specifically: if real_home()/.config/tavernbench doesn't exist but
    profile_home()/.config/tavernbench does, symlink the profile dir into
    the real home so both paths resolve to the same config.

    Returns (changed, message).
    """
    rh = real_home()
    ph = profile_home()

    if rh == ph:
        return False, "HOME matches real home — no symlink needed"

    real_cfg = rh / ".config" / "tavernbench"
    profile_cfg = ph / ".config" / "tavernbench"

    # Nothing to link if profile config doesn't exist yet
    if not profile_cfg.exists():
        # Ensure the real dir exists so future writes go to the right place
        real_cfg.mkdir(parents=True, exist_ok=True)
        return True, f"created real config dir: {real_cfg}"

    if real_cfg.exists() or real_cfg.is_symlink():
        if real_cfg.is_symlink() and real_cfg.resolve() == profile_cfg.resolve():
            return False, f"symlink already in place: {real_cfg} → {profile_cfg}"
        return False, f"{real_cfg} already exists — not overwriting"

    real_cfg.parent.mkdir(parents=True, exist_ok=True)
    real_cfg.symlink_to(profile_cfg)
    return True, f"symlinked {real_cfg} → {profile_cfg}"


# ---------------------------------------------------------------------------
# Main entry point for the CLI
# ---------------------------------------------------------------------------

def run(fix: bool = False) -> int:
    """Run all health checks; optionally apply fixes. Returns exit code."""
    checks = [
        ("API key",    check_api_key),
        ("Server",     check_server),
        ("MCP client", check_mcp_registered),
    ]

    all_ok = True
    for label, fn in checks:
        ok, msg = fn()
        status = "✓" if ok else "✗"
        print(f"  {status} {label}: {msg}")
        if not ok:
            all_ok = False

    if fix:
        print()
        changed, msg = fix_home_symlink()
        verb = "fixed" if changed else "info"
        print(f"  [{verb}] home symlink: {msg}")

    print()
    if all_ok:
        print("All checks passed.")
        return 0
    else:
        print("Some checks failed. Re-run with --fix to attempt auto-repair, or follow the suggestions above.")
        return 1
