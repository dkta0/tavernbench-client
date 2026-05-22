# TavernBench Python SDK

Python SDK for the [TavernBench](https://github.com/your-org/agent_mmo) agent benchmarking platform — a DnD dungeon crawler for evaluating AI agents.

## Install

```bash
pip install websockets
```

No package published yet; add the `clients/python` directory to your `PYTHONPATH`:

```bash
export PYTHONPATH=/path/to/agent_mmo/clients/python:$PYTHONPATH
```

Or install editable:

```bash
pip install -e /path/to/agent_mmo/clients/python
```

## Quick start (async)

```python
import asyncio
import tavernbench as tb

async def run():
    async with tb.AsyncClient("ws://localhost:4100", api_key="your-key") as client:
        await client.join("tavern_hall")
        await client.wait_tick()                 # wait for first state broadcast

        print(client.state.position)             # Position(3, 3)
        print([e.name for e in client.state.entities])

        await client.move("north")
        await client.wait_tick()
        await client.speak("npc_barkeep")
        await client.wait_tick()
        await client.reply(1)

asyncio.run(run())
```

## Quick start (blocking)

```python
import tavernbench as tb

with tb.Client("ws://localhost:4100", api_key="your-key") as client:
    client.join("tavern_hall")
    client.wait_tick()

    print(client.state.position)
    client.move("north")
    client.wait_tick()
```

## API reference

### Connection

| Call | Description |
|---|---|
| `AsyncClient(host, api_key, ...)` | Create async client |
| `Client(host, api_key, ...)` | Create blocking client |
| `await client.connect()` | Open WebSocket |
| `await client.disconnect()` | Close WebSocket |
| `async with client` | Context manager (connect/disconnect) |

### Channel

| Call | Description |
|---|---|
| `await client.join(zone_id)` | Join a zone channel |
| `await client.leave()` | Leave current channel |

### Actions

| Call | Description |
|---|---|
| `await client.move(direction)` | north/south/east/west/northeast/… |
| `await client.enter(target)` | Enter an exit (zone transition) |
| `await client.speak(target)` | Initiate NPC dialogue |
| `await client.reply(choice_id)` | Select dialogue choice |
| `await client.examine(target)` | Examine entity |
| `await client.pickup(target)` | Pick up item |
| `await client.drop(item)` | Drop inventory item |
| `await client.use(item, target?)` | Use item |
| `await client.attack(target)` | Attack enemy |
| `await client.flee()` | Flee from combat |
| `await client.inventory()` | Request inventory list |
| `await client.quests()` | Request quest log |
| `await client.look()` | Request immediate state broadcast |
| `await client.wait_turn()` | Do nothing this tick |
| `await client.wait_tick(n)` | Block until n ticks received |

### State

The `client.state` object is updated automatically on every tick:

```python
s = client.state
s.position        # Position(x, y)
s.zone_id         # "tavern_hall"
s.zone            # Zone(id, width, height)
s.entities        # list of Entity
s.inventory       # list of InventoryItem
s.quest_log       # list of Quest
s.score           # int
s.steps           # int
s.tick            # int

# helpers
s.visible("npc")          # filter by type
s.nearest("exit")         # closest entity of type
s.get_entity("npc_barkeep")
```

### Callbacks

Pass callbacks to the constructor to react to server pushes:

```python
def on_dialogue(npc_id, npc_name, text, choices):
    print(f"{npc_name}: {text}")
    # choices is list of {id: int, text: str}

def on_quest_complete(final_score, steps_taken):
    print(f"Finished! Score: {final_score}")

def on_event(event_type, payload):
    # event_type: npc_spoke | combat | entity_died | player_died |
    #              fled | inventory | quests | zone_entered |
    #              item_picked_up | item_dropped | examine
    pass

tb.AsyncClient(host, api_key=key,
    on_dialogue=on_dialogue,
    on_quest_complete=on_quest_complete,
    on_event=on_event,
)
```

Callbacks may be regular functions or `async def`.

### Errors

| Exception | When |
|---|---|
| `AuthError` | Server rejects API key (HTTP 403) |
| `ChannelError` | join() fails (wrong protocol version, etc.) |
| `ActionError` | Action reply has status=error (e.g. INVALID_DIRECTION) |
| `TavernBenchError` | Base class |

```python
try:
    await client.move("sideways")
except tb.ActionError as e:
    print(e.code)  # "INVALID_DIRECTION"
```

## Running the example agent

```bash
cd clients/python
python example.py
```

The example agent connects, joins tavern_hall, and runs a simple decision loop: speak to nearby NPCs, enter exits, attack enemies, or move north.
