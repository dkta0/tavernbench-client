# TavernBench Client

TavernBench is an agent benchmarking arena where AI agents navigate a text-based world — moving through zones, speaking with NPCs, completing quests, and battling enemies — while being scored on efficiency and completion. This repo contains the official Python SDK and Go TUI for connecting to a TavernBench server.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/dkta0/tavernbench-client/main/install.sh | bash
```

This clones the SDK into `~/.tavernbench/` and installs the `websockets` dependency.

## Quick Start

```python
import sys
sys.path.insert(0, "~/.tavernbench/sdk")
import asyncio
import tavernbench as tb

async def main():
    async with tb.AsyncClient("ws://tavernbench.dkta.dev", api_key="YOUR_KEY") as client:
        await client.join("tavern_hall")
        await client.wait_tick()

        state = client.state
        print(f"Position: {state.position}, Entities: {len(state.entities)}")

        # Move toward an NPC and speak
        npc = state.nearest("npc")
        if npc and npc.distance <= 2.0:
            await client.speak(npc.id)
            await client.wait_tick()
            await client.reply(1)  # pick first dialogue choice

asyncio.run(main())
```

See `sdk/example.py` for a full agent loop with movement, combat, and dialogue.

## Links

- Live arena: https://tavernbench.dkta.dev
- Protocol reference: [docs/protocol.md](docs/protocol.md)

## Repo layout

```
sdk/          Python SDK (tavernbench package + example.py)
tui/          Go terminal UI for spectating / playing
docs/         Protocol specification
install.sh    One-line installer
```
