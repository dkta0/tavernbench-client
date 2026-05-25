"""TavernBench CLI entry point."""
import typer
from tavernbench_cli import commands

app = typer.Typer(
    name="tavernbench-mcp",
    help="TavernBench — MCP server + install + auth",
    add_completion=False,
    no_args_is_help=True,
)

app.add_typer(commands.mcp_app, name="mcp")
app.command()(commands.auth)
app.command()(commands.install)
app.command()(commands.doctor)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
