"""CLI subcommand implementations (stubs)."""
from __future__ import annotations

import typer
from typing import Optional

# ---------------------------------------------------------------------------
# mcp sub-app (handles `tavernbench mcp serve`)
# ---------------------------------------------------------------------------
mcp_app = typer.Typer(
    help="MCP server commands.",
    add_completion=False,
    no_args_is_help=True,
)


@mcp_app.command("serve")
def mcp_serve(
    host: str = typer.Option("127.0.0.1", help="Bind host for the MCP server."),
    port: int = typer.Option(8765, help="Bind port for the MCP server."),
) -> None:
    """Start the TavernBench MCP server so AI agents can connect."""
    typer.echo(f"[stub] mcp serve  host={host} port={port}")
    raise typer.Exit()


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------


def auth(
    key: Optional[str] = typer.Option(None, "--key", "-k", help="API key (omit for hidden prompt)."),
) -> None:
    """Save your TavernBench API key to ~/.config/tavernbench/config.toml."""
    typer.echo(f"[stub] auth  key={'<hidden>' if key else 'prompt'}")
    raise typer.Exit()


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
