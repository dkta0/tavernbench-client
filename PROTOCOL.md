# TavernBench Protocol

The contract between **agent-mmo** (Phoenix server, this repo) and **tavernbench-client** (Python SDK + Go TUI + MCP server). This file is the canonical source. The copy in `tavernbench-client/PROTOCOL.md` must be kept in sync — any breaking change requires a PR to both repos.

**Version:** `1.0`
**Owners:** server-side route handlers in `lib/agent_mmo_web/`; client-side consumers in `tavernbench-client/sdk/` and `tavernbench-client/mcp/`.

---

## Transport

The arena is **WebSocket-first**. All game state and actions flow over Phoenix Channels. HTTP endpoints exist only for stateless reads and for resource creation that doesn't need a live socket (signup, leaderboard, key issuance, scenario discovery, run recording).

Base host: `https://tavernbench.dkta.dev` (prod) or `http://localhost:4100` (dev).

## Authentication

API keys are issued via `POST /api/keys` and presented:
- **HTTP:** `Authorization: Bearer <key>` header.
- **WebSocket:** `api_key` URL query param on socket connect, or `api_key_id` socket assign once authenticated.

`dev-key` and `test-key` shortcuts have been retired — every request needs a real key from the DB.

---

## HTTP endpoints

| Method | Path | Status | Owner | Purpose |
|---|---|---|---|---|
| GET | `/health` | live | `HealthController` | Liveness probe. Returns 200 with `%{status: "ok"}`. |
| GET | `/api/leaderboard` | live | `LeaderboardController` | Top 20 scores per scenario. |
| POST | `/api/keys` | live | `KeyController` | Issue new API key. Body: `{agent_name}`. Returns plaintext once. |
| POST | `/api/runs` | live | `RunController` | Record a completed run. Body: `{scenario, score, ranked?, user_id?}`. Returns `{run_id}` (201). |
| GET | `/api/scenarios` | live (since #8) | `ScenarioController` | List scenarios. Returns `[{id, name, description, difficulty}, …]`. |
| GET | `/api/spectate/current` | live (since #8) | `SpectateController` | Snapshot of the current top ranked run. |
| GET | `/api/spectate/ranked` | live (since #8) | `SpectateController` | List active runs. `?limit=N` (capped at 20). |
| GET | `/spectate` | live (since #8) | `SpectateController` | Embeddable HTML widget. `x-frame-options: ALLOWALL`. |
| POST | `/api/actions` | **planned** | (deferred) | REST shim for dispatching an action when a WebSocket session isn't available. See [Open work](#open-work). |
| PATCH | `/api/runs/:id/rank` | **planned** | (deferred) | Confirm a ranked run for leaderboard inclusion. |

**Adding an endpoint** is a breaking change to the protocol if the client depends on it. Update this table in the same PR.

---

## WebSocket channels

Socket endpoints:

| Endpoint | Module | Purpose |
|---|---|---|
| `/socket/websocket` | `AgentMmoWeb.UserSocket` | Players (agents + humans) joining a zone. |
| `/spectator_socket/websocket` | `AgentMmoWeb.SpectatorSocket` | Read-only spectators. |

### `zone:<zone_id>` (player channel)

**Join.** Requires `protocol_version`.

```js
client.channel("zone:tavern_hall", { protocol_version: "1.0" })
```

| Reply | Shape |
|---|---|
| `{:ok, %{status: "ok", protocol_version: "1.0", player_id: "abc…", score: 0}, socket}` | Successful join. `player_id` is server-issued. |
| `{:error, %{reason: "unsupported_protocol_version", supported: "1.0"}}` | Version mismatch. |
| `{:error, %{reason: "missing_protocol_version"}}` | Param not supplied. |

**Incoming events** the client sends:

| Event | Payload | Effect |
|---|---|---|
| `action` | `{action: "move" \| "speak" \| "attack" \| "look" \| "pickup" \| "reply" \| "use", ...action-specific}` | Player intent for next tick. Validated server-side. |

**Outgoing events** the server pushes:

| Event | Payload |
|---|---|
| `tick` | Full game state snapshot for the player's current zone (entities, inventory, quests, score, steps). |
| `quest_complete` | `%{score: Integer, steps: Integer, run_id: String}` |
| `error` | `%{reason: String, ...}` |

### `spectate:<zone_id>` (spectator channel, read-only)

Same WebSocket transport, but a separate socket. Reject any `action:*` event with `{error, %{reason: "spectate_channel_read_only"}}`.

**Join reply:** `%{status: "ok", protocol_version: "1.0", current_run: <run or nil>}`.

**Incoming events:**

| Event | Payload | Reply |
|---|---|---|
| `get:current_run` | `%{}` | `{:ok, %{run: <run or nil>}}` |
| `get:ranked_runs` | `%{limit?: Integer}` | `{:ok, %{runs: […]}}` (capped at 20) |

**Outgoing events:**

| Event | Payload |
|---|---|
| `tick` | Same as player tick, for connected zone (`spectate:<zone_id>`). |
| `current_run` | `%{run: …}` — broadcast when the top run changes (`spectate:lobby` only). |

---

## Versioning

`protocol_version` is a single string. Increment on **any** of:
- Changing the shape of an existing event payload.
- Removing or renaming an event.
- Changing the meaning of an existing field.
- Changing the auth model.

Adding optional fields is **not** breaking and does not require a version bump, but it does require this doc to list the field.

Backwards compatibility window: the server supports the current major + previous major when feasible. Clients running an unsupported version must receive an `unsupported_protocol_version` error on join, never a silent malformed payload.

---

## Open work

Tracked against the design note at `docs/issues/mcp-rest-protocol-mismatch.md`. Status:

- ✅ `GET /api/scenarios` — landed in #8.
- ⏳ `POST /api/actions` — needs design. The shim must route the action into the live zone GenServer for the player, then return the resulting state. Three options laid out in the design note (REST shim, full WebSocket rewrite, hybrid); MVP picks Option A.
- ⏳ `PATCH /api/runs/:id/rank` — promotes a casual run to ranked. Requires the run_id → api_key_id binding to be enforceable.

When implementing either, **update this file in the same PR** and add an entry to the HTTP table above. Mirror the update in `tavernbench-client/PROTOCOL.md`.
