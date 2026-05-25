"""TavernBench MCP server — thin shim that shells out to the `tavernbench` CLI."""
from __future__ import annotations

import json
import os
import subprocess
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tavernbench")

CLI_BIN = os.environ.get("TAVERNBENCH_CLI_BIN", "tavernbench")


def _run(args: list[str]) -> str:
    result = subprocess.run(
        [CLI_BIN, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return json.dumps({"error": result.stderr.strip() or "cli failed"})
    return result.stdout.strip() or "{}"


@mcp.tool()
def tavernbench_list_scenarios() -> str:
    """List available scenarios."""
    return _run(["scenarios"])


@mcp.tool()
def tavernbench_start_run(scenario_id: str = "", ranked: bool = False) -> str:
    """Attach to the active TUI as the agent and return the initial observation.

    The TUI must already be running (`tavernbench play --scenario ...`). This tool
    does NOT launch the TUI — interactive play is the user's job. `ranked` is
    advisory only; the casual leaderboard always records.
    """
    _ = scenario_id, ranked  # currently advisory only
    token = os.environ.get("TAVERNBENCH_TOKEN", "")
    if not token:
        return json.dumps({"error": "TAVERNBENCH_TOKEN env var not set — start `tavernbench play` first"})
    return _run(["attach", token])


@mcp.tool()
def tavernbench_act(run_id: str, action: str, target: str = "", params: Optional[str] = None) -> str:
    """Dispatch one action via the running TUI."""
    _ = run_id, params  # run_id is advisory in the IPC architecture
    args = ["act", action]
    if target:
        args.append(target)
    return _run(args)


@mcp.tool()
def tavernbench_observe(run_id: str) -> str:
    """Return the current observation."""
    _ = run_id  # run_id is advisory in the IPC architecture
    return _run(["observe"])


@mcp.tool()
def tavernbench_confirm_ranked(run_id: str) -> str:
    """Deprecated: casual-leaderboard MVP records every completion."""
    _ = run_id
    return json.dumps({"confirmed": True, "note": "casual-leaderboard MVP — confirmation is a no-op"})


def run_server() -> None:
    mcp.run()


if __name__ == "__main__":
    run_server()
