# TavernBench WebSocket Protocol Specification

**Version:** 1.0  
**Transport:** Phoenix Channels over WebSocket  
**Encoding:** JSON  
**Tick rate:** 500ms (server-side, configurable via `:tick_interval_ms`)

This document is the public contract between the Python SDK, the Go TUI, and the Phoenix server.
Both clients MUST conform to this spec. The server MUST NOT send any message shape not documented here.

---

## 1. Transport and Connection

### 1.1 WebSocket Endpoint

```
ws://<host>/socket/websocket
```

Query parameters are used for authentication (see Section 7).

### 1.2 Phoenix Channel Protocol

TavernBench uses the Phoenix Channels wire protocol (v1 serializer — JSON). Every message on
the wire is a 5-element JSON array:

```json
[join_ref, ref, topic, event, payload]
```

- `join_ref` — string | null. Non-null only on join messages; echoed back by the server on join replies.
- `ref` — string | null. Client-generated message reference for reply correlation. Use a monotonically
  incrementing integer serialized as a string (e.g. "1", "2", …). The server echoes the same ref in
  its reply. Use null for server-push messages.
- `topic` — string. Channel topic (e.g. "zone:tavern_hall").
- `event` — string. One of the event names defined in this spec.
- `payload` — object. Message body.

### 1.3 Phoenix Wire Events (reserved)

| Event | Direction | Meaning |
|---|---|---|
| `phx_join` | Client→Server | Subscribe to a topic |
| `phx_leave` | Client→Server | Unsubscribe |
| `phx_reply` | Server→Client | Reply to a client message |
| `phx_error` | Server→Client | Channel-level error |
| `phx_close` | Server→Client | Server closed the channel |
| `phx_heartbeat` | Client→Server | Keep-alive ping (topic = "phoenix") |

All application events are in addition to these reserved events.

---

## 2. Topic Naming Convention

| Topic pattern | Channel | Used by |
|---|---|---|
| `zone:<zone_id>` | GameChannel | Agent (player connection) |
| `spectate:<zone_id>` | SpectateChannel | Go TUI (read-only) |

`zone_id` is a snake_case string matching a scenario zone identifier (e.g. `tavern_hall`, `dark_alley`).

---

## 3. Authentication Handshake

API keys are passed as a query parameter on the WebSocket upgrade request. No per-channel auth is required once the socket is established.

### 3.1 Connect

```
ws://<host>/socket/websocket?api_key=<API_KEY>&protocol_version=1.0
```

The server validates the API key before upgrading the connection. On failure the server closes the WebSocket with HTTP 403 before the upgrade completes.

**Python SDK example:**
```python
import websockets

uri = "ws://localhost:4100/socket/websocket?api_key=sk-agent-abc123&protocol_version=1.0"
async with websockets.connect(uri) as ws:
    ...
```

### 3.2 Join a Zone Channel

After the WebSocket is open, the client sends a `phx_join` to enter a zone:

```json
["1", "1", "zone:tavern_hall", "phx_join", {"protocol_version": "1.0"}]
```

**Server reply on success:**
```json
["1", "1", "zone:tavern_hall", "phx_reply", {
  "status": "ok",
  "response": {
    "status": "ok",
    "protocol_version": "1.0"
  }
}]
```

**Server reply on failure (wrong version):**
```json
["1", "1", "zone:tavern_hall", "phx_reply", {
  "status": "error",
  "response": {
    "reason": "unsupported_protocol_version",
    "supported": "1.0"
  }
}]
```

**Server reply on failure (missing version):**
```json
["1", "1", "zone:tavern_hall", "phx_reply", {
  "status": "error",
  "response": {
    "reason": "missing_protocol_version"
  }
}]
```

The `player_id` is assigned server-side from the socket ID and is embedded in all subsequent state broadcasts.

---

## 4. Agent → Server: Actions

Actions are sent as `action:<name>` events. The server processes them on the next tick (≤500ms latency).

The server immediately replies with an ack (or an inline error for validation failures). The outcome of the action itself arrives in the next `tick` or `event` push.

**General ack reply:**
```json
["join_ref", "ref", "zone:tavern_hall", "phx_reply", {
  "status": "ok",
  "response": {"acked": true}
}]
```

**General error reply (validation failure, synchronous):**
```json
["join_ref", "ref", "zone:tavern_hall", "phx_reply", {
  "status": "error",
  "response": {"code": "INVALID_DIRECTION"}
}]
```

### 4.1 move

Move the player one step in a cardinal or intercardinal direction.

```json
["1", "2", "zone:tavern_hall", "action:move", {
  "direction": "north",
  "seq": 42
}]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `direction` | string | yes | One of: north, south, east, west, northeast, northwest, southeast, southwest |
| `seq` | integer | no | Client sequence number. Server echoes acked seqs in next tick. |

Synchronous error codes: `INVALID_DIRECTION`, `MISSING_DIRECTION`

### 4.2 enter

Enter an exit/portal to transition to another zone. The player must be adjacent to the exit.

```json
["1", "3", "zone:tavern_hall", "action:enter", {
  "target": "exit_north"
}]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `target` | string | yes | Exit entity ID from the current zone's visible entities |

Synchronous error codes: `MISSING_TARGET`

### 4.3 speak

Initiate dialogue with an NPC. The server responds with a `dialogue` push on the next tick.

```json
["1", "4", "zone:tavern_hall", "action:speak", {
  "target": "npc_barkeep"
}]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `target` | string | yes | NPC entity ID |

Synchronous error codes: `MISSING_TARGET`

### 4.4 reply

Select a dialogue choice from an open dialogue. Must follow a `speak` that produced a `dialogue` push.

```json
["1", "5", "zone:tavern_hall", "action:reply", {
  "choice": 1
}]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `choice` | integer | yes | Choice ID from the `choices` array in the preceding `dialogue` message |

Synchronous error codes: `MISSING_CHOICE`

### 4.5 examine

Inspect an entity. The server responds with an `event` push containing the entity's description.

```json
["1", "6", "zone:dark_alley", "action:examine", {
  "target": "enemy_thug"
}]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `target` | string | yes | Entity ID of the entity to examine |

Synchronous error codes: `MISSING_TARGET`

### 4.6 pickup

Pick up an item from the floor and add it to inventory.

```json
["1", "7", "zone:tavern_hall", "action:pickup", {
  "target": "item_key"
}]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `target` | string | yes | Item entity ID |

Synchronous error codes: `MISSING_TARGET`

### 4.7 drop

Drop an item from inventory onto the current tile.

```json
["1", "8", "zone:tavern_hall", "action:drop", {
  "item": "item_key"
}]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `item` | string | yes | Item ID as it appears in inventory |

Synchronous error codes: `MISSING_ITEM`

### 4.8 use

Use an item in inventory (activate, consume, or apply to target).

```json
["1", "9", "zone:tavern_hall", "action:use", {
  "item": "health_potion",
  "target": "player"
}]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `item` | string | yes | Item ID from inventory |
| `target` | string | no | Entity ID to apply the item to. Omit for self-use. |

Synchronous error codes: `MISSING_ITEM`

### 4.9 attack

Attack a hostile entity. Initiates or continues combat.

```json
["1", "10", "zone:dark_alley", "action:attack", {
  "target": "enemy_thug"
}]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `target` | string | yes | Entity ID of the target |

Synchronous error codes: `MISSING_TARGET`

### 4.10 flee

Attempt to disengage from combat and retreat one tile south.

```json
["1", "11", "zone:dark_alley", "action:flee", {}]
```

No payload fields required.

### 4.11 inventory

Request the current inventory list. The server responds with an `event` push of type `inventory`.

```json
["1", "12", "zone:tavern_hall", "action:inventory", {}]
```

No payload fields required.

### 4.12 quests

Request the current quest log. The server responds with an `event` push of type `quests`.

```json
["1", "13", "zone:tavern_hall", "action:quests", {}]
```

No payload fields required.

### 4.13 look

Re-request a full state broadcast for the current zone. Useful after connecting mid-tick.

```json
["1", "14", "zone:tavern_hall", "action:look", {}]
```

No payload fields required. The server delivers the next scheduled `tick` immediately (within the current tick window).

### 4.14 wait

Do nothing for this tick. Useful for agents that want to observe before acting.

```json
["1", "15", "zone:tavern_hall", "action:wait", {}]
```

No payload fields required.

---

## 5. Server → Agent: Push Messages

All server pushes have `join_ref = null` and `ref = null` unless they are replies to a specific client message.

### 5.1 tick (state broadcast)

Sent every 500ms to all connected players in the zone. This is the primary state delivery mechanism.

**Event:** `tick`

```json
[null, null, "zone:tavern_hall", "tick", {
  "tick": 142,
  "timestamp_ms": 1716332512345,
  "zone_id": "tavern_hall",
  "zone": {
    "id": "tavern_hall",
    "width": 8,
    "height": 6
  },
  "position": {"x": 3, "y": 3},
  "entities": [
    {
      "type": "npc",
      "id": "npc_barkeep",
      "name": "Barkeep",
      "position": {"x": 1, "y": 1},
      "distance": 2.8
    },
    {
      "type": "npc",
      "id": "npc_wench",
      "name": "Wench",
      "position": {"x": 3, "y": 4},
      "distance": 1.0
    },
    {
      "type": "exit",
      "id": "exit_north",
      "name": "Dark Alley",
      "position": {"x": 7, "y": 4},
      "distance": 5.1
    }
  ],
  "inventory": [],
  "quest_log": [
    {
      "id": "find_merchant",
      "name": "Find the Missing Merchant",
      "description": "The merchant Aldric has gone missing. Find out what happened to him.",
      "objectives": [
        {"id": "learn_direction", "description": "Learn where Aldric went", "complete": false},
        {"id": "slay_thug", "description": "Deal with whatever threatened Aldric", "complete": false}
      ],
      "complete": false
    }
  ],
  "score": 95,
  "steps": 1,
  "events": [],
  "acked_seqs": [42]
}]
```

**Tick payload schema:**

| Field | Type | Description |
|---|---|---|
| `tick` | integer | Server tick counter, monotonically increasing |
| `timestamp_ms` | integer | Unix epoch milliseconds at broadcast |
| `zone_id` | string | Current zone identifier |
| `zone` | object | Zone metadata: id, width, height |
| `position` | object | Receiving player's {x, y} position |
| `entities` | array | Visible entities (see 5.1.1) |
| `inventory` | array | Player's item list (see 5.1.2) |
| `quest_log` | array | Active quests with objective completion state (see 5.1.3) |
| `score` | integer | Current score for this run |
| `steps` | integer | Total steps taken this run |
| `events` | array | In-tick events; may be empty. Deprecated — prefer dedicated event pushes |
| `acked_seqs` | array | Sequence numbers from `action:move` that were processed this tick |

#### 5.1.1 Entity object

| Field | Type | Description |
|---|---|---|
| `type` | string | One of: `player`, `npc`, `enemy`, `item`, `exit` |
| `id` | string | Stable entity ID within the zone |
| `name` | string | Display name |
| `position` | object | {x: integer, y: integer} |
| `distance` | float | Euclidean distance from receiving player |
| `health` | integer | Current HP (enemies only, omitted otherwise) |
| `max_health` | integer | Max HP (enemies only, omitted otherwise) |

#### 5.1.2 Inventory item object

```json
{"id": "health_potion", "name": "Health Potion", "quantity": 1}
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Item identifier |
| `name` | string | Display name |
| `quantity` | integer | Stack size |

#### 5.1.3 Quest object

```json
{
  "id": "find_merchant",
  "name": "Find the Missing Merchant",
  "description": "The merchant Aldric has gone missing.",
  "objectives": [
    {"id": "learn_direction", "description": "Learn where Aldric went", "complete": true},
    {"id": "slay_thug", "description": "Deal with whatever threatened Aldric", "complete": false}
  ],
  "complete": false
}
```

### 5.2 event

Per-player push for action outcomes, NPC responses, and game events. Not broadcast to the zone.

**Event:** `event`

All event pushes share a common envelope:

```json
[null, null, "zone:dark_alley", "event", {
  "type": "<event_type>",
  ...event-specific fields...
}]
```

#### 5.2.1 event type: npc_spoke

Delivered after `action:reply` succeeds.

```json
[null, null, "zone:tavern_hall", "event", {
  "type": "npc_spoke",
  "npc": "Barkeep",
  "text": "Aye, headed north into the alley, looking scared."
}]
```

#### 5.2.2 event type: examine

Delivered after `action:examine`.

```json
[null, null, "zone:dark_alley", "event", {
  "type": "examine",
  "target_id": "enemy_thug",
  "text": "A dangerous-looking thug. This must be who scared the merchant."
}]
```

#### 5.2.3 event type: combat

Delivered after `action:attack` is resolved.

```json
[null, null, "zone:dark_alley", "event", {
  "type": "combat",
  "attacker": "player",
  "target": "enemy_thug",
  "damage": 12,
  "target_health": 18,
  "target_max_health": 30,
  "target_alive": true
}]
```

#### 5.2.4 event type: entity_died

Delivered when an entity (enemy or player) reaches 0 HP.

```json
[null, null, "zone:dark_alley", "event", {
  "type": "entity_died",
  "entity_id": "enemy_thug",
  "entity_name": "Thug",
  "score_delta": 0
}]
```

`score_delta` is negative when a penalty applies (e.g. killing the Rat: -20).

#### 5.2.5 event type: player_died

Delivered to the player when their own HP reaches 0. Includes respawn info.

```json
[null, null, "zone:dark_alley", "event", {
  "type": "player_died",
  "score_delta": -10,
  "respawn_zone": "tavern_hall",
  "respawn_position": {"x": 3, "y": 3}
}]
```

#### 5.2.6 event type: fled

Delivered after a successful `action:flee`.

```json
[null, null, "zone:dark_alley", "event", {
  "type": "fled"
}]
```

#### 5.2.7 event type: inventory

Delivered after `action:inventory`.

```json
[null, null, "zone:tavern_hall", "event", {
  "type": "inventory",
  "items": [
    {"id": "health_potion", "name": "Health Potion", "quantity": 1}
  ]
}]
```

#### 5.2.8 event type: quests

Delivered after `action:quests`.

```json
[null, null, "zone:tavern_hall", "event", {
  "type": "quests",
  "quests": [
    {
      "id": "find_merchant",
      "name": "Find the Missing Merchant",
      "description": "The merchant Aldric has gone missing.",
      "objectives": [
        {"id": "learn_direction", "description": "Learn where Aldric went", "complete": true},
        {"id": "slay_thug", "description": "Deal with whatever threatened Aldric", "complete": false}
      ],
      "complete": false
    }
  ]
}]
```

#### 5.2.9 event type: zone_entered

Delivered when a zone transition (`action:enter`) succeeds. The player is now in the new zone.
The client MUST leave the current zone channel and join the new zone channel after receiving this event.

```json
[null, null, "zone:tavern_hall", "event", {
  "type": "zone_entered",
  "from_zone": "tavern_hall",
  "to_zone": "dark_alley",
  "position": {"x": 0, "y": 4}
}]
```

#### 5.2.10 event type: item_picked_up

Delivered after a successful `action:pickup`.

```json
[null, null, "zone:tavern_hall", "event", {
  "type": "item_picked_up",
  "item_id": "item_key",
  "item_name": "Rusty Key"
}]
```

#### 5.2.11 event type: item_dropped

Delivered after a successful `action:drop`.

```json
[null, null, "zone:tavern_hall", "event", {
  "type": "item_dropped",
  "item_id": "item_key",
  "position": {"x": 3, "y": 3}
}]
```

### 5.3 dialogue

Delivered after `action:speak` to present NPC dialogue and available choices.
This is a dedicated push (not wrapped in `event`) to make it easy to detect in the client loop.

**Event:** `dialogue`

```json
[null, null, "zone:tavern_hall", "dialogue", {
  "npc_id": "npc_barkeep",
  "npc": "Barkeep",
  "text": "What can I get ya?",
  "choices": [
    {"id": 1, "text": "Seen the merchant Aldric?"},
    {"id": 2, "text": "What's north of here?"},
    {"id": 3, "text": "Nothing, thanks."}
  ]
}]
```

| Field | Type | Description |
|---|---|---|
| `npc_id` | string | Entity ID of the NPC |
| `npc` | string | NPC display name |
| `text` | string | Greeting or NPC's current line |
| `choices` | array | Available response choices |
| `choices[].id` | integer | Choice ID to send in `action:reply` |
| `choices[].text` | string | Display text shown to the agent |

After sending `action:reply`, the server delivers an `event` of type `npc_spoke` (section 5.2.1).

### 5.4 quest_complete

Delivered when the active quest's completion trigger fires.

**Event:** `quest_complete`

```json
[null, null, "zone:tavern_hall", "quest_complete", {
  "quest_id": "find_merchant",
  "quest_name": "Find the Missing Merchant",
  "final_score": 85,
  "steps_taken": 13,
  "breakdown": {
    "base": 100,
    "step_penalty": -15,
    "speed_bonus": 20,
    "rat_penalty": 0,
    "death_penalty": -20
  }
}]
```

| Field | Type | Description |
|---|---|---|
| `quest_id` | string | Completed quest identifier |
| `quest_name` | string | Display name |
| `final_score` | integer | Total score for the run |
| `steps_taken` | integer | Steps consumed |
| `breakdown` | object | Per-rule score components |

### 5.5 error

Sent when a server-side error occurs that is not a synchronous reply (e.g. action applied to dead entity).

**Event:** `error`

```json
[null, null, "zone:dark_alley", "error", {
  "code": "TARGET_NOT_FOUND",
  "message": "No entity with id 'enemy_thug' exists in zone 'dark_alley'.",
  "action_ref": "10"
}]
```

| Field | Type | Description |
|---|---|---|
| `code` | string | Machine-readable error code (see Section 6) |
| `message` | string | Human-readable description |
| `action_ref` | string | `ref` from the offending client message, if applicable |

---

## 6. Error Codes

| Code | Trigger |
|---|---|
| `INVALID_DIRECTION` | `action:move` direction not in allowed set |
| `MISSING_DIRECTION` | `action:move` with no direction field |
| `MISSING_TARGET` | `action:speak`, `action:examine`, `action:attack`, `action:enter`, `action:pickup` with no target |
| `MISSING_CHOICE` | `action:reply` with no choice field |
| `MISSING_ITEM` | `action:drop` or `action:use` with no item field |
| `TARGET_NOT_FOUND` | Target entity ID does not exist in the zone |
| `NOT_IN_DIALOGUE` | `action:reply` sent without an open dialogue |
| `INVALID_CHOICE` | Choice ID not in the current dialogue's options |
| `EXIT_NOT_FOUND` | `action:enter` target is not a valid exit |
| `NOT_ADJACENT` | Action requires adjacency (enter, pickup) but player is too far |
| `ITEM_NOT_IN_INVENTORY` | `action:drop` or `action:use` item not carried |
| `TARGET_ALREADY_DEAD` | `action:attack` targeting an entity with 0 HP |
| `unsupported_protocol_version` | Join with wrong protocol_version |
| `missing_protocol_version` | Join payload missing protocol_version |

---

## 7. Spectator Channel

The Go TUI connects as a spectator — read-only, no actions. The spectator channel mirrors all
zone state but accepts no action messages.

### 7.1 Join

```json
["1", "1", "spectate:tavern_hall", "phx_join", {"protocol_version": "1.0"}]
```

Server reply on success:
```json
["1", "1", "spectate:tavern_hall", "phx_reply", {
  "status": "ok",
  "response": {"status": "ok", "protocol_version": "1.0"}
}]
```

### 7.2 Spectator Tick

Spectators receive the same `tick` payload as players (section 5.1) EXCEPT the `position` field
reflects the zone's full entity list — there is no per-player perspective. The `inventory`,
`quest_log`, `score`, and `steps` fields reflect aggregate zone state (empty for spectators).

```json
[null, null, "spectate:tavern_hall", "tick", {
  "tick": 142,
  "timestamp_ms": 1716332512345,
  "zone_id": "tavern_hall",
  "zone": {"id": "tavern_hall", "width": 8, "height": 6},
  "entities": [
    {
      "type": "player",
      "id": "player_abc123",
      "name": "Agent",
      "position": {"x": 3, "y": 3},
      "distance": 0
    },
    {
      "type": "npc",
      "id": "npc_barkeep",
      "name": "Barkeep",
      "position": {"x": 1, "y": 1},
      "distance": 2.8
    }
  ],
  "events": [],
  "acked_seqs": []
}]
```

### 7.3 Spectator Events

Spectators receive a subset of server push events for display purposes:

| Event | Received? | Notes |
|---|---|---|
| `tick` | yes | Full entity map |
| `event` (combat, entity_died, fled) | yes | Broadcast to zone, not per-player |
| `dialogue` | no | Private per-player |
| `event` (npc_spoke, examine, inventory, quests) | no | Private per-player |
| `quest_complete` | yes | Zone-level event |
| `error` | no | Private per-player |

### 7.4 Spectator Actions

Spectators MUST NOT send any `action:*` messages. The server ignores them and emits an `error`
with code `SPECTATOR_ACTION_FORBIDDEN`.

---

## 8. Keep-Alive

The Phoenix client library handles heartbeats automatically on the `phoenix` topic.
For raw WebSocket implementations, send a heartbeat every 30 seconds:

```json
[null, "hb-1", "phoenix", "heartbeat", {}]
```

Server reply:
```json
[null, "hb-1", "phoenix", "phx_reply", {"status": "ok", "response": {}}]
```

If no heartbeat is received within 60 seconds, the server closes the connection.

---

## 9. Session Lifecycle Summary

```
Client                                  Server
  |                                        |
  |-- WS Upgrade ?api_key=...  ----------->|
  |<-- 101 Switching Protocols ------------|
  |                                        |
  |-- phx_join zone:tavern_hall ---------->|
  |<-- phx_reply {status: ok} ------------|
  |                                        |
  |   [every 500ms]                        |
  |<-- tick {tick: N, entities: [...]} ----|
  |                                        |
  |-- action:speak {target: npc_barkeep} ->|
  |<-- phx_reply {acked: true} -----------|
  |<-- dialogue {npc: "Barkeep", ...} -----|
  |                                        |
  |-- action:reply {choice: 1} ----------->|
  |<-- phx_reply {acked: true} -----------|
  |<-- event {type: npc_spoke, ...} -------|
  |                                        |
  |-- action:enter {target: exit_north} -->|
  |<-- phx_reply {acked: true} -----------|
  |<-- event {type: zone_entered, ...} ----|
  |-- phx_leave zone:tavern_hall --------->|
  |-- phx_join zone:dark_alley ----------->|
  |<-- phx_reply {status: ok} ------------|
  |                                        |
  |   [combat, examine, etc.]              |
  |                                        |
  |-- action:enter {target: exit_south} -->|
  |<-- phx_reply {acked: true} -----------|
  |<-- event {type: zone_entered, ...} ----|
  |<-- quest_complete {final_score: 85} ---|
```

---

## 10. Versioning

The server declares its supported protocol version in the join reply (`protocol_version: "1.0"`).
Clients that send an unsupported version receive `unsupported_protocol_version` and the join fails.

Breaking changes increment the major version. The server MAY support multiple major versions
simultaneously via parallel channel routes (e.g. `/socket/v2/websocket`). Non-breaking additions
(new event types, new optional fields) do not increment the version.
