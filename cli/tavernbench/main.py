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

from . import config
from . import install_cmd as _install_cmd


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

def cmd_stub(name: str) -> int:
    print(f"`tavernbench {name}` is not yet implemented.")
    return 1


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

SUBCOMMANDS = {
    "auth": cmd_auth,
    "leaderboard": lambda args: cmd_stub("leaderboard"),
    "history": lambda args: cmd_stub("history"),
    "doctor": lambda args: cmd_stub("doctor"),
    "play": lambda args: cmd_stub("play"),
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

    # stub subcommands
    for name in ("leaderboard", "history", "doctor", "play", "watch", "install"):
        sp = subparsers.add_parser(name)
        sp.set_defaults(func=lambda args, n=name: cmd_stub(n))

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
