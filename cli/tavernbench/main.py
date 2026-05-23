"""
TavernBench CLI — entry point.

Usage:
  tavernbench auth              store/refresh API key (hidden paste)
  tavernbench leaderboard       print top-N to terminal
  tavernbench history           your own past runs
  tavernbench doctor            key valid? server reachable?
  tavernbench mcp serve         start the MCP server (stdio)
  tavernbench play              human plays in TUI
  tavernbench watch [run_id]    spectate a run
  tavernbench install <client>  register MCP server with claude-code / cursor / codex
"""
from __future__ import annotations

import argparse
import getpass
import sys

import os
import subprocess
from pathlib import Path

from . import config
from . import install_cmd as _install_cmd
from . import doctor_cmd as _doctor_cmd


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------

def cmd_install(args: argparse.Namespace) -> int:
    """Register the TavernBench MCP server with an agent client."""
    _install_cmd.run(
        args.client,
        local=getattr(args, "local", False),
        dry_run=getattr(args, "dry_run", False),
    )
    return 0


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------

def cmd_auth(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Prompt for an API key (hidden paste) and store it."""
    print("TavernBench — store API key")
    print()
    print("Get your key at https://tavernbench.dkta.dev/dashboard")
    print()

    existing = config.get_api_key()
    if existing:
        masked = existing[:6] + "..." + existing[-4:] if len(existing) > 10 else "***"
        print(f"Current key: {masked}")
        overwrite = input("Overwrite? [y/N] ").strip().lower()
        if overwrite not in ("y", "yes"):
            print("Aborted — keeping existing key.")
            return 0
        print()

    key = getpass.getpass("Paste API key (input hidden): ").strip()
    if not key:
        print("Error: no key entered.", file=sys.stderr)
        return 1

    config.set_api_key(key)
    print(f"\n✓ Key saved to {config.CONFIG_FILE}")
    return 0


# ---------------------------------------------------------------------------
# Stub handlers for other subcommands (to be fleshed out in follow-up tasks)
# ---------------------------------------------------------------------------

def cmd_doctor(args: argparse.Namespace) -> int:
    """Run health checks; with --fix, attempt to repair detected issues."""
    return _doctor_cmd.run(fix=getattr(args, "fix", False))


def cmd_stub(name: str) -> int:
    print(f"`tavernbench {name}` is not yet implemented.")
    return 1


# ---------------------------------------------------------------------------
# play
# ---------------------------------------------------------------------------

def _find_play_binary() -> Path | None:
    """Find the compiled play binary. Searches alongside this file's package,
    then ~/.tavernbench/tui/play/play, then PATH."""
    candidates = [
        Path(__file__).parent.parent.parent / "tui" / "play" / "play",
        Path.home() / ".tavernbench" / "tui" / "play" / "play",
    ]
    for p in candidates:
        if p.exists() and os.access(p, os.X_OK):
            return p
    # Check PATH
    import shutil
    found = shutil.which("tavernbench-play")
    if found:
        return Path(found)
    return None


def _build_play_binary(src_dir: Path) -> Path | None:
    """Attempt to build the play binary from source using go build."""
    import shutil
    if not shutil.which("go"):
        return None
    out = src_dir / "play"
    result = subprocess.run(
        ["go", "build", "-o", str(out), "."],
        cwd=str(src_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and out.exists():
        return out
    print(f"go build failed:\n{result.stderr}", file=sys.stderr)
    return None


def cmd_play(args: argparse.Namespace) -> int:
    """Launch the human TUI player (Go binary)."""
    host = getattr(args, "host", "tavernbench.dkta.dev")
    zone = getattr(args, "zone", "tavern_hall")
    api_key = getattr(args, "api_key", None) or config.get_api_key()

    binary = _find_play_binary()
    if binary is None:
        # Try to build from source
        src_dir = Path(__file__).parent.parent.parent / "tui" / "play"
        if src_dir.exists():
            print("Building play binary from source...", file=sys.stderr)
            binary = _build_play_binary(src_dir)
        if binary is None:
            print(
                "Error: play binary not found.\n"
                "  Expected: tui/play/play  (or tavernbench-play on PATH)\n"
                "  Build it: cd tui/play && go build -o play .",
                file=sys.stderr,
            )
            return 1

    cmd = [str(binary), host, zone]
    if api_key:
        cmd.append(api_key)

    try:
        os.execv(str(binary), cmd)
    except OSError as exc:
        print(f"Error launching play: {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

SUBCOMMANDS = {
    "auth": cmd_auth,
    "leaderboard": lambda args: cmd_stub("leaderboard"),
    "history": lambda args: cmd_stub("history"),
    "doctor": cmd_doctor,
    "play": cmd_play,
    "watch": lambda args: cmd_stub("watch"),
    "install": cmd_install,
    "mcp": lambda args: cmd_stub("mcp serve"),
}


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tavernbench",
        description="TavernBench CLI — benchmark your AI agent in a text RPG arena.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # auth
    auth_p = subparsers.add_parser("auth", help="store/refresh API key")
    auth_p.set_defaults(func=cmd_auth)

    # install
    install_p = subparsers.add_parser(
        "install",
        help="register MCP server with an agent client (claude-code, cursor, codex)",
    )
    install_p.add_argument(
        "client",
        choices=list(_install_cmd.SUPPORTED_CLIENTS),
        help="agent client to register with",
    )
    install_p.add_argument(
        "--local",
        action="store_true",
        help="write to workspace-local config (e.g. .cursor/mcp.json in cwd)",
    )
    install_p.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="print what would be written without making changes",
    )
    install_p.set_defaults(func=cmd_install)

    # stub subcommands (not play — handled separately below)
    for name in ("leaderboard", "history", "watch"):
        sp = subparsers.add_parser(name)
        sp.set_defaults(func=lambda args, n=name: cmd_stub(n))

    # doctor
    doctor_p = subparsers.add_parser("doctor", help="run health checks (API key, server, MCP)")
    doctor_p.add_argument(
        "--fix",
        action="store_true",
        help="attempt to repair detected issues (e.g. home-dir symlink)",
    )
    doctor_p.set_defaults(func=cmd_doctor)

    # play
    play_p = subparsers.add_parser("play", help="play in the TUI as a human")
    play_p.add_argument("--host", default="tavernbench.dkta.dev",
                        help="Arena host (default: tavernbench.dkta.dev)")
    play_p.add_argument("--zone", default="tavern_hall",
                        help="Zone to join (default: tavern_hall)")
    play_p.add_argument("--api-key", dest="api_key", default=None,
                        help="API key (default: from config)")
    play_p.set_defaults(func=cmd_play)

    # mcp (with sub-subcommand `serve`)
    mcp_p = subparsers.add_parser("mcp", help="MCP server management")
    mcp_sub = mcp_p.add_subparsers(dest="mcp_command", metavar="<mcp_command>")
    serve_p = mcp_sub.add_parser("serve", help="start MCP server (stdio)")
    serve_p.set_defaults(func=lambda args: cmd_stub("mcp serve"))
    mcp_p.set_defaults(func=lambda args: cmd_stub("mcp serve"))

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    rc = args.func(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
