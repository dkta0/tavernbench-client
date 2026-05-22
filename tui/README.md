# TavernBench Go TUI Spectator

A zero-dependency read-only spectator for TavernBench.  Connects to the
`spectate:<zone>` Phoenix channel and renders a live 2D ASCII map, action
log, quest status, score and step counter — all in a standard terminal.

## Requirements

- Go 1.22+
- No external packages (stdlib only)

## Build

```sh
go build ./...
```

This produces a `spectator` binary in the current directory.

## Usage

```sh
./spectator [host] [zone] [api_key]
```

| Argument  | Default           | Description                                      |
|-----------|-------------------|--------------------------------------------------|
| `host`    | `127.0.0.1:4100`  | WebSocket host:port of the TavernBench server    |
| `zone`    | `tavern_hall`     | Zone to spectate (`tavern_hall`, `dark_alley`, …)|
| `api_key` | `spectator`       | API key (passed as `?api_key=` query parameter)  |

### Examples

```sh
# Local dev server, default zone
./spectator

# Remote server, custom zone and key
./spectator game.example.com:4100 dark_alley mykey
```

## Layout (80×24)

```
╔ TavernBench Spectator ╗  zone:tavern_hall  tick:142  lag:12ms
──────────────────────────────────────────────────────────────────
 Map: tavern_hall (8x6)     Action Log (23 entries)
┌─────────────────┐         [combat] player → enemy_thug  dmg:12
│ · · · · · · · · │         [died]   Thug  score_delta:0
│ · N · · · · · · │         [event]  player fled
│ · · · · · · · · │         [quest]  Find the Missing… COMPLETE
│ · · · @ · · · · │
│ · · · N · · · · │
│ · · · · · · · > │
└─────────────────┘
@=player  N=npc  E=enemy  >=exit
──────────────────────────────────────────────────────────────────
 Quests
  [ ] Find the Missing Merchant
    ✓ Learn where Aldric went
    ○ Deal with whatever threatened Aldric
──────────────────────────────────────────────────────────────────
Score:95    Steps:3     Entities:4    q=quit  ↑↓=scroll log
```

## Key bindings

| Key      | Action              |
|----------|---------------------|
| `q` / `Q` / Ctrl-C | Quit         |
| `↑` / `k` | Scroll log up      |
| `↓` / `j` | Scroll log down    |

## Protocol

The spectator connects via the Phoenix Channels wire protocol (v1 JSON serializer)
to `ws://<host>/socket/websocket?api_key=<key>&protocol_version=1.0`
and joins topic `spectate:<zone>`.

It receives:
- `tick` — full entity map every 500 ms
- `event` — combat, entity_died, fled (zone-level broadcasts)
- `quest_complete` — zone-level quest completion

See `docs/protocol.md` in the TavernBench repo for the full spec.

## Reconnection

The spectator reconnects automatically on WebSocket disconnect (2-second backoff).
