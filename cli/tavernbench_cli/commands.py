"""CLI subcommand implementations."""
from __future__ import annotations

import getpass
import sys
import typer
from typing import Optional

from tavernbench_cli import config

# ---------------------------------------------------------------------------
# mcp sub-app (handles `tavernbench mcp serve`)
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
    _sdk_dir = os.path.join(_repo, "sdk")
    _cli_dir = os.path.join(_repo, "cli")

    # Ensure mcp/, sdk/, cli/ are importable.  sdk must come before cli/ so that
    # `import tavernbench` resolves to sdk/tavernbench (has client.py) not cli/tavernbench.
    for _p in [_mcp_dir, _cli_dir, _sdk_dir]:
        if _p not in sys.path:
            sys.path.insert(0, _p)

    try:
        from server import run_server  # mcp/server.py
    except ImportError as exc:
        typer.echo(f"Error: could not load MCP server: {exc}", err=True)
        raise typer.Exit(code=1)

    run_server()


# ---------------------------------------------------------------------------
# auth — the one real implementation
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


# ---------------------------------------------------------------------------
# Stub subcommands
# ---------------------------------------------------------------------------

def play(
    scenario: Optional[str] = typer.Option(None, "--scenario", "-s", help="Scenario ID to run."),
) -> None:
    """Play TavernBench interactively (human TUI mode)."""
    typer.echo(f"[stub] play  scenario={scenario}")
    raise typer.Exit()


def watch(
    run_id: Optional[str] = typer.Argument(None, help="Run ID to spectate. Omit for latest."),
) -> None:
    """Watch a live or recorded benchmark run."""
    typer.echo(f"[stub] watch  run_id={run_id}")
    raise typer.Exit()


def leaderboard(
    scenario: Optional[str] = typer.Option(None, "--scenario", "-s", help="Filter by scenario."),
    top: int = typer.Option(10, "--top", "-n", help="Number of entries to show."),
) -> None:
    """Display the global leaderboard."""
    typer.echo(f"[stub] leaderboard  scenario={scenario} top={top}")
    raise typer.Exit()


def history(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of past runs to show."),
) -> None:
    """Show your personal run history."""
    typer.echo(f"[stub] history  limit={limit}")
    raise typer.Exit()


def install(
    client: str = typer.Argument(..., help="MCP client to configure (claude, cursor, vscode, custom)."),
) -> None:
    """Install the TavernBench MCP server entry into a supported AI client config."""
    typer.echo(f"[stub] install  client={client}")
    raise typer.Exit()


def doctor() -> None:
    """Run pre-flight checks (API key, server reachability, MCP server binary)."""
    typer.echo("[stub] doctor")
    raise typer.Exit()
