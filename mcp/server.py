"""
TavernBench MCP server.

Exposes 5 tools for MCP-connected agents to play TavernBench:
  tavernbench_list_scenarios
  tavernbench_start_run
  tavernbench_confirm_ranked
  tavernbench_act
  tavernbench_observe

Invoked via: tavernbench mcp serve  (stdio transport)
"""
from __future__ import annotations

import asyncio
import os
import sys
import urllib.request
import urllib.error
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Path setup — allow import of sdk and cli packages from the repo layout
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
# Ensure SDK comes before cli/ on sys.path so 'tavernbench' resolves to
# sdk/tavernbench (which has client.py) rather than cli/tavernbench/ (config only).
_SDK = os.path.join(_REPO, "sdk")
_CLI = os.path.join(_REPO, "cli")
# Always place sdk at index 0 and cli right after it.
for _p in [_CLI, _SDK]:
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, _CLI)
sys.path.insert(0, _SDK)
# Remove the mcp/ repo directory from sys.path so it does NOT shadow the
# 'mcp' pip package.  We do this after fixing up SDK/CLI so the removal is
# always applied regardless of how Python found this file.
# Also remove the repo root — pytest adds it to sys.path, which would make
# the local mcp/ directory importable as the 'mcp' package.
if _HERE in sys.path:
    sys.path.remove(_HERE)
if _REPO in sys.path:
    sys.path.remove(_REPO)

from mcp.server.fastmcp import FastMCP
from tavernbench.client import AsyncClient, GameState

try:
    from tavernbench.config import get_api_key as _cfg_get_api_key
except ImportError:
    def _cfg_get_api_key() -> Optional[str]:
        return None

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    key = os.environ.get("TAVERNBENCH_API_KEY") or _cfg_get_api_key() or ""
    return key


def _get_host() -> str:
    return os.environ.get("TAVERNBENCH_HOST", "ws://localhost:4100")


def _ws_to_http(ws_host: str) -> str:
    return ws_host.replace("ws://", "http://").replace("wss://", "https://")


# ---------------------------------------------------------------------------
# In-process run registry
# ---------------------------------------------------------------------------

RUN_REGISTRY: dict[str, dict] = {}


def _make_observation(state: GameState) -> dict:
    return {
        "tick": state.tick,
        "zone_id": state.zone_id,
        "position": {"x": state.position.x, "y": state.position.y} if state.position else None,
        "entities": [
            {
                "type": e.type,
                "id": e.id,
                "name": e.name,
                "position": {"x": e.position.x, "y": e.position.y},
                "distance": e.distance,
            }
            for e in state.entities
        ],
        "inventory": [
            {"id": i.id, "name": i.name, "quantity": i.quantity}
            for i in state.inventory
        ],
        "quests": [
            {"id": q.id, "name": q.name, "complete": q.complete}
            for q in state.quest_log
        ],
        "score": state.score,
        "steps": state.steps,
    }


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("tavernbench")

SCENARIO_BRIEF = (
    "TavernBench: guide your agent through a dungeon tavern. "
    "Move around the zone, speak to NPCs, reply to dialogue choices, "
    "complete quests, and maximize your score. "
    "Use tavernbench_act to take actions and tavernbench_observe to inspect state. "
    "The game ends when all quests are complete or you run out of steps."
)


@mcp.tool()
def tavernbench_list_scenarios() -> str:
    """Browse available TavernBench scenarios.

    Returns a JSON list of scenarios with id, name, description, and difficulty.
    """
    http_host = _ws_to_http(_get_host())
    url = f"{http_host}/api/scenarios"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return json.dumps(data)
    except urllib.error.HTTPError as e:
        return json.dumps({"error": f"HTTP {e.code}: {e.reason}", "url": url})
    except Exception as e:
        # Server may not be running; return a default scenario list
        default = [
            {
                "id": "tavern_hall",
                "name": "The Tavern Hall",
                "description": "Classic starting scenario. Find the missing apprentice.",
                "difficulty": "easy",
            }
        ]
        return json.dumps(default)


@mcp.tool()
def tavernbench_start_run(scenario_id: str = "", ranked: bool = False) -> str:
    """Begin a TavernBench run.

    Args:
        scenario_id: Scenario to play. Omit for the default daily scenario.
        ranked: If True, the run will be submitted to the leaderboard once confirmed.

    Returns JSON with run_id, brief (natural language goal), initial observation,
    and ranked_pending (True if you must call tavernbench_confirm_ranked before acting).
    """
    host = _get_host()
    api_key = _get_api_key()
    zone_id = scenario_id if scenario_id else "tavern_hall"
    run_id = str(uuid.uuid4())

    async def _connect_and_observe():
        client = AsyncClient(host=host, api_key=api_key)
        await client.connect()
        try:
            await client.join(zone_id)
            # Wait for first tick to populate state
            try:
                await asyncio.wait_for(client._wait_for_tick(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
            state = client.state
            obs = _make_observation(state)
        finally:
            await client.disconnect()
        return obs

    try:
        obs = asyncio.run(_connect_and_observe())
    except Exception as e:
        # Server not reachable — return a minimal stub observation
        obs = {
            "tick": 0,
            "zone_id": zone_id,
            "position": None,
            "entities": [],
            "inventory": [],
            "quests": [],
            "score": 0,
            "steps": 0,
        }

    RUN_REGISTRY[run_id] = {
        "zone_id": zone_id,
        "ranked": ranked,
        "confirmed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "host": host,
        "api_key": api_key,
    }

    result = {
        "run_id": run_id,
        "brief": SCENARIO_BRIEF,
        "observation": obs,
        "ranked_pending": ranked,
    }
    return json.dumps(result)


@mcp.tool()
def tavernbench_confirm_ranked(run_id: str) -> str:
    """Confirm a ranked run. Must be called after start_run(ranked=True) and before any act().

    Without this call the run is silently treated as casual (not posted to leaderboard).

    Args:
        run_id: The run_id returned by tavernbench_start_run.

    Returns JSON with confirmed and started_at timestamp.
    """
    run = RUN_REGISTRY.get(run_id)
    if not run:
        return json.dumps({"error": f"run_id {run_id!r} not found. Call tavernbench_start_run first."})
    run["confirmed"] = True
    return json.dumps({"confirmed": True, "started_at": run["created_at"]})


@mcp.tool()
def tavernbench_act(run_id: str, action: str, target: str = "", params: Optional[str] = None) -> str:
    """Dispatch an action in a TavernBench run.

    Args:
        run_id: The run_id returned by tavernbench_start_run.
        action: One of: move, enter, speak, reply, examine, pickup, drop, use,
                attack, flee, inventory, quests, look, wait.
        target: Action-specific target. For move: direction (north/south/east/west).
                For reply: dialogue choice number (as string, e.g. "1").
                For use: "item_id on entity_id". For other actions: entity or item id.
        params: Optional JSON string with extra parameters (reserved for future use).

    Returns JSON with observation, events, score, run_complete, and optional final_result.
    """
    run = RUN_REGISTRY.get(run_id)
    if not run:
        return json.dumps({"error": f"run_id {run_id!r} not found. Call tavernbench_start_run first."})

    host = run["host"]
    api_key = run["api_key"]
    zone_id = run["zone_id"]

    async def _do_action():
        client = AsyncClient(host=host, api_key=api_key)
        await client.connect()
        events_collected: list[dict] = []

        def on_event(etype, payload):
            events_collected.append({"type": etype, "data": payload})

        client._on_event = on_event

        try:
            await client.join(zone_id)
            try:
                await asyncio.wait_for(client._wait_for_tick(), timeout=3.0)
            except asyncio.TimeoutError:
                pass

            result_payload: dict = {}

            if action == "move":
                result_payload = await client.move(target)
            elif action == "enter":
                result_payload = await client.enter(target)
            elif action == "speak":
                result_payload = await client.speak(target)
            elif action == "reply":
                try:
                    choice = int(target)
                except ValueError:
                    choice = 1
                result_payload = await client.reply(choice)
            elif action == "examine":
                result_payload = await client.examine(target)
            elif action == "pickup":
                result_payload = await client.pickup(target)
            elif action == "drop":
                result_payload = await client.drop(target)
            elif action == "use":
                parts = target.split(" on ", 1)
                item = parts[0].strip()
                on_target = parts[1].strip() if len(parts) > 1 else None
                result_payload = await client.use(item, on_target)
            elif action == "attack":
                result_payload = await client.attack(target)
            elif action == "flee":
                result_payload = await client.flee()
            elif action == "inventory":
                result_payload = await client.inventory()
            elif action == "quests":
                result_payload = await client.quests()
            elif action == "look":
                result_payload = await client.look()
            elif action == "wait":
                result_payload = await client.wait_turn()
            else:
                return {"error": f"Unknown action: {action!r}. Valid: move/enter/speak/reply/examine/pickup/drop/use/attack/flee/inventory/quests/look/wait"}

            # Wait for the resulting tick
            try:
                await asyncio.wait_for(client._wait_for_tick(), timeout=3.0)
            except asyncio.TimeoutError:
                pass

            state = client.state
            obs = _make_observation(state)
            run_complete = bool(result_payload.get("game_over") or result_payload.get("run_complete"))
            final_result = result_payload.get("final_result") or result_payload.get("result")

            return {
                "observation": obs,
                "events": events_collected,
                "score": state.score,
                "run_complete": run_complete,
                "final_result": final_result,
            }
        finally:
            await client.disconnect()

    try:
        return json.dumps(asyncio.run(_do_action()))
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def tavernbench_observe(run_id: str) -> str:
    """Look at the current game state without taking an action.

    Args:
        run_id: The run_id returned by tavernbench_start_run.

    Returns JSON with observation (tick, zone_id, position, entities, inventory, quests, score, steps).
    """
    run = RUN_REGISTRY.get(run_id)
    if not run:
        return json.dumps({"error": f"run_id {run_id!r} not found. Call tavernbench_start_run first."})

    host = run["host"]
    api_key = run["api_key"]
    zone_id = run["zone_id"]

    async def _do_look():
        client = AsyncClient(host=host, api_key=api_key)
        await client.connect()
        try:
            await client.join(zone_id)
            try:
                await asyncio.wait_for(client._wait_for_tick(), timeout=3.0)
            except asyncio.TimeoutError:
                pass
            await client.look()
            try:
                await asyncio.wait_for(client._wait_for_tick(), timeout=3.0)
            except asyncio.TimeoutError:
                pass
            return _make_observation(client.state)
        finally:
            await client.disconnect()

    try:
        obs = asyncio.run(_do_look())
        return json.dumps({"observation": obs})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_server():
    """Run the MCP server on stdio. Called by `tavernbench mcp serve`."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_server()
