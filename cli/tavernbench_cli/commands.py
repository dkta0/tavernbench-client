"""CLI subcommand implementations."""
from __future__ import annotations

import getpass
import typer
from typing import Optional

from tavernbench_cli import config

# ---------------------------------------------------------------------------
# mcp sub-app (handles `tavernbench-mcp mcp serve`)
# ---------------------------------------------------------------------------
mcp_app = typer.Typer(
    help="MCP server commands.",
    add_completion=False,
    no_args_is_help=True,
)


@mcp_app.command("serve")
def mcp_serve() -> None:
    """Start the TavernBench MCP server (stdio transport) for AI agents.

    This command is invoked automatically by MCP clients (Claude Code, Cursor,
    Codex) when they start the server process. It communicates over stdio using
    the MCP protocol.
    """
    import os
    import sys

    # Locate repo root from this file's position:
    # cli/tavernbench_cli/commands.py  →  cli/  →  repo root
    _here = os.path.dirname(os.path.abspath(__file__))
    _repo = os.path.dirname(os.path.dirname(_here))  # up from tavernbench_cli/ → cli/ → repo root
    _mcp_dir = os.path.join(_repo, "mcp")
    _cli_dir = os.path.join(_repo, "cli")

    # Ensure mcp/ and cli/ are importable.
    for _p in [_mcp_dir, _cli_dir]:
        if _p not in sys.path:
            sys.path.insert(0, _p)

    try:
        from server import run_server  # mcp/server.py
    except ImportError as exc:
        typer.echo(f"Error: could not load MCP server: {exc}", err=True)
        raise typer.Exit(code=1)

    run_server()


# ---------------------------------------------------------------------------
# auth — kept for backward compat during transition; Go CLI's `auth` is canonical.
# ---------------------------------------------------------------------------

def auth(
    key: Optional[str] = typer.Option(None, "--key", "-k", help="API key (omit for hidden prompt)."),
) -> None:
    """Save your TavernBench API key to ~/.config/tavernbench/config.toml."""
    typer.echo("TavernBench — store API key")
    typer.echo("")
    typer.echo("Get your key at https://tavernbench.dkta.dev/dashboard")
    typer.echo("")

    existing = config.get_api_key()
    if existing:
        masked = existing[:6] + "..." + existing[-4:] if len(existing) > 10 else "***"
        typer.echo(f"Current key: {masked}")
        overwrite = typer.prompt("Overwrite? [y/N]", default="N")
        if overwrite.strip().lower() not in ("y", "yes"):
            typer.echo("Aborted — keeping existing key.")
            raise typer.Exit()
        typer.echo("")

    if key:
        api_key = key.strip()
    else:
        api_key = getpass.getpass("Paste API key (input hidden): ").strip()

    if not api_key:
        typer.echo("Error: no key entered.", err=True)
        raise typer.Exit(code=1)

    config.set_api_key(api_key)
    typer.echo(f"\n✓ Key saved to {config.CONFIG_FILE}")


def install(
    client: str = typer.Argument(..., help="MCP client to configure (claude-code, cursor, codex)."),
    local: bool = typer.Option(False, "--local", help="Write to workspace-local config rather than user home."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would be written without changing anything."),
) -> None:
    """Install the TavernBench MCP server entry into a supported AI client config."""
    from tavernbench_cli import install_cmd

    install_cmd.run(client, local=local, dry_run=dry_run)


def doctor(
    fix: bool = typer.Option(False, "--fix", help="Attempt to auto-repair detected issues."),
) -> None:
    """Run pre-flight checks (API key, server reachability, MCP registration)."""
    from tavernbench_cli import doctor_cmd

    raise typer.Exit(code=doctor_cmd.run(fix=fix))
