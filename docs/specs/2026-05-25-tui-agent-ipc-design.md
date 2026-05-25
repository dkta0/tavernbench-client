# TUI-Mediated Agent IPC Design

**Status:** Approved
**Date:** 2026-05-25
**Scope:** Replaces the current direct-to-server MCP/SDK path with a TUI-mediated unix-socket bridge. Adds run transcript recording on the server side.

---

## Problem

Today an agent connecting to TavernBench has two failures:

1. **Per-action reconnect breaks runs.** The MCP server opens a fresh WebSocket, joins a zone, dispatches one action, and disconnects per tool call. Server-side `PlayerSession` is keyed by a UUID minted at channel join. State never accumulates across calls, so scores stay at 0, `quest_complete` never fires, and the leaderboard never sees the run.
2. **No "watch your agent run" path.** The Go spectator TUI works against a live zone, but there's no relationship between the agent the user just hooked up and what shows up in the TUI. CLI subcommands `play`, `watch`, `leaderboard`, `history` are all stubs.

The current trust model is also "casual" — anyone can post any score. Strengthening that is a separate concern that this spec does not solve, but it should not preclude.

## Solution overview

One Go binary, the **TUI**, becomes the only process that speaks the Phoenix WebSocket protocol. It holds the parsed `GameState`, renders continuously, and listens on a unix domain socket for commands from a small **CLI**. Agents — whatever the user calls "their agent" — drive runs by shelling out to that CLI. The TUI may optionally spawn the agent itself as a subprocess for a one-terminal experience, or accept an attach from any other terminal for two-terminal cases.

Effects:

- One persistent server-side player session per run, so state accumulates and runs can complete.
- The TUI "lights up" visually the moment an agent attaches.
- Agent integration surface is just shell commands — works with any tool that can call them (Claude Code, Cursor, scripts).
- The Python SDK as a separate concept is deleted. The Go TUI's code is the SDK.
- A new `RunTranscript` table records every action/tick pair, providing the evidence base for any future verification work.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│ User's terminal (one-terminal case)                            │
│   $ tavernbench play --scenario tavern_hall --agent './a.py'   │
│   ┌────────────────────────────────────────────────────────┐   │
│   │  TUI (Go binary)                                       │   │
│   │  ┌──────────────────┐    ┌────────────────────────┐    │   │
│   │  │ WS client        │    │ unix-socket listener   │    │   │
│   │  │ → Phoenix server │    │ /run/.../<token>.sock  │    │   │
│   │  └────────┬─────────┘    └──────────┬─────────────┘    │   │
│   │           │ ticks, events           │ CLI commands     │   │
│   │           ▼                         ▼                  │   │
│   │  ┌──────────────────────────────────────────────────┐  │   │
│   │  │ GameState (single source of truth)               │  │   │
│   │  │ agent_state: detached | attached(<name>)         │  │   │
│   │  └──────────────────────────────────────────────────┘  │   │
│   │           ▼                                            │   │
│   │  Renderer (10 fps, alt-screen, ANSI)                   │   │
│   │  Agent subprocess: ./a.py (stdout/stderr captured)     │   │
│   └────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

Two-terminal case is identical except `--agent` is not passed; the agent runs anywhere with access to the socket file and calls `tavernbench attach <token>`.

## Components

### TUI (`tui/main.go`)

Long-lived Go process. Replaces both `tui/main.go` (spectator) and `tui/play/main.go` (player) with one binary, modes selected by flags.

Responsibilities:
- Open one Phoenix WebSocket; join `zone:<id>` as a player or `spectate:<id>` as a spectator (mode flag).
- Maintain authoritative parsed `GameState`.
- Listen on `${XDG_RUNTIME_DIR:-/tmp}/tavernbench/<token>.sock` with `0600` permissions.
- Render at 10 fps to an alt-screen with ANSI; the existing spectator renderer is reused.
- Track `agent_state: detached | attached(name)` and apply the "lights up" visual shift on attach: themed accent color, agent name in the title bar, action-intent panel appears, idle UI dims. Revert on detach.
- Optionally spawn `--agent <cmd>` as a subprocess with `TAVERNBENCH_TOKEN=<token>` in the environment, capturing stdout/stderr into a panel ring buffer (1000-line cap).
- Handle keyboard: `q` aborts the run, `?` shows help.

New internal packages:

| Package | Purpose |
|---|---|
| `tui/internal/wsclient` | Phoenix WS client lifted from the existing hand-rolled spectator code. |
| `tui/internal/state` | `GameState` types and tick reducer. |
| `tui/internal/ipc` | Unix-socket server and the request/response wire protocol. |
| `tui/internal/render` | Split out from the current monolithic `tui/main.go`. |
| `tui/internal/agentproc` | Subprocess spawner with stdio capture. |

### CLI (`cli/tavernbench`)

One-shot Go binary. Each invocation opens the unix socket, sends one request, prints the JSON reply, exits. Replaces the Python CLI stub commands.

| Subcommand | Behavior |
|---|---|
| `tavernbench attach <token>` | Handshake; sets the agent name (`$TAVERNBENCH_AGENT_NAME` or argv[0]) on the TUI. Triggers the "lights up" transition. |
| `tavernbench act <verb> [args]` | Send action, return resulting observation as JSON. Verbs match the Phoenix game protocol: `move`, `enter`, `speak`, `reply`, `examine`, `pickup`, `drop`, `use`, `attack`, `flee`, `inventory`, `quests`, `look`, `wait`. |
| `tavernbench observe` | Return current observation without acting. |
| `tavernbench scenarios` | List scenarios via HTTP `GET /api/scenarios`. (Does not require a running TUI.) |
| `tavernbench leaderboard --scenario <id>` | Print scores via HTTP `GET /api/leaderboard`. (Does not require a running TUI.) |
| `tavernbench play --scenario <id> [--agent <cmd>]` | Launch the TUI. |
| `tavernbench auth [--key <k>]` | Store the API key at `~/.config/tavernbench/config.toml`. Unchanged from the existing Python implementation, ported to Go. |
| `tavernbench doctor [--fix]` | Pre-flight checks (key present, server reachable, MCP registration). Unchanged in behavior, ported to Go. |
| `tavernbench mcp install <client>` | Register the MCP server with Claude Code / Cursor / Codex. Stays in Python for now (it manipulates those clients' config files; minimal code, no benefit to porting). |

Socket resolution priority for non-`play` commands:
1. `$TAVERNBENCH_SOCK` env var (explicit socket path)
2. `$TAVERNBENCH_TOKEN` env var → derived path
3. `--token` flag

If none of these resolve to a live socket, exit 1 with `tavernbench: no active run (is the TUI running?)` on stderr.

### MCP shim (`mcp/server.py`)

Tool surface stays the same for backward compatibility, but each tool becomes a `subprocess.run(["tavernbench", ...])` call. The in-process `RUN_REGISTRY` goes away — the TUI owns the run.

Approximate shape:

```python
@mcp.tool()
def tavernbench_act(run_id: str, action: str, target: str = "") -> str:
    args = ["tavernbench", "act", action]
    if target:
        args.append(target)
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return json.dumps({"error": result.stderr.strip()})
    return result.stdout
```

The `run_id` parameter becomes advisory — the CLI doesn't need it because the TUI is the run.

### Deletions

- `sdk/tavernbench/client.py` (614 lines) — gone. Phoenix protocol owned by the TUI's Go code.
- `cli/tavernbench_cli/commands.py` Python stubs (`play`, `watch`, `leaderboard`, `history`) — gone, replaced by Go subcommands.
- `tui/play/main.go` — folded into `tui/main.go` with mode flags.
- Bulk of `mcp/server.py` — kept as a ~80-line shim.

`tavernbench auth` and `tavernbench doctor` are ported to Go alongside the new subcommands. `tavernbench mcp install` and `tavernbench mcp serve` stay in Python.

## Data flow

### Run start (one-terminal)

```
User: $ tavernbench play --scenario tavern_hall --agent './my-agent.py'
  TUI: mint token (TAVERN-A8X3), open unix socket at /run/.../TAVERN-A8X3.sock
  TUI: read API key from ~/.config/tavernbench/config.toml
       (if missing, exit with "run `tavernbench auth` first")
  TUI: open WS → ws://server/socket/websocket?api_key=<k>
  TUI: phx_join "zone:tavern_hall" → ok, player_id=<uuid>
  TUI: spawn ./my-agent.py with TAVERNBENCH_TOKEN=TAVERN-A8X3 in env
  TUI: render begins; agent_state=detached
  Agent: $ tavernbench attach $TAVERNBENCH_TOKEN
    CLI → TUI: {op:"attach", name:"my-agent.py"}
    TUI → CLI: {ok:true, observation:<initial state>}
  TUI: agent_state=attached("my-agent.py") → lights up
```

### Per-action loop

```
Agent: $ tavernbench act move north
  CLI → TUI: {op:"act", verb:"move", args:{direction:"north"}}
  TUI → WS:  ["jr","r17","zone:tavern_hall","action",{action:"move",direction:"north"}]
  TUI: marks await-tick on ref r17
  WS  → TUI: phx_reply ok
  WS  → TUI: tick {entities:…, score:5, steps:1}
  TUI: applies tick to GameState, rerenders
  TUI → CLI: {ok:true, observation:{...}, events:[...], run_complete:false}
  CLI: prints JSON, exits 0
```

Latency: one WS round-trip + one tick wait. Same as the SDK does today.

### Run end

`quest_complete` arrives → TUI marks `run_complete:true` → server has already persisted `BenchmarkRun` and broadcast `leaderboard:<scenario>` PubSub → any subsequent `tavernbench act` returns `{ok:true, run_complete:true, final_result:{...}}` without forwarding to the server.

### Two-terminal case

Identical except no subprocess is spawned. The TUI prints the token to its log panel and to stdout before entering alt-screen, so the user can copy it.

### IPC wire format

Newline-delimited JSON over the unix socket. One message per CLI invocation:

```json
// Request (CLI → TUI)
{"op": "act|observe|attach|abort", "verb": "...", "args": {...}, "id": "uuid"}

// Response (TUI → CLI), success
{"id": "uuid", "ok": true, "observation": {...}, "events": [...], "run_complete": false}

// Response (TUI → CLI), error
{"id": "uuid", "ok": false, "error": {"code": "...", "message": "..."}}
```

The IPC schema is intentionally distinct from the Phoenix wire protocol. The TUI translates between them so Phoenix protocol changes do not ripple into CLI/MCP/agent code.

## Error handling

### TUI ↔ Phoenix WebSocket

| Failure | Handling |
|---|---|
| WS connect rejected (bad API key or protocol version) | Show error in log panel, exit 2. Socket file never created → attach fails fast. |
| WS disconnect mid-run | Auto-reconnect with 2s backoff, capped at 3 attempts (existing spectator code). After cap: print "Run lost — server disconnected", keep TUI open so user can read it. |
| Heartbeat missed | Same as disconnect path. |

### TUI ↔ CLI unix socket

| Failure | Handling |
|---|---|
| CLI can't open socket | Stderr `tavernbench: no active run (is the TUI running?)`, exit 1. |
| Stale socket file (TUI crashed) | TUI cleans up on startup if `connect()` to its own socket path fails. |
| Garbage JSON from CLI | TUI replies `{ok:false, error:{code:"bad_request"}}` and closes the connection. No TUI crash. |
| Action arrives mid-tick | Queued; reply only after the resulting tick lands. CLI sees a synchronous round-trip. |
| Two `act` requests concurrent (multi-agent racing the same socket) | Processed serially. Queue depth cap 4 — beyond that, second reply is `{ok:false, error:{code:"action_in_flight"}}`. |

### Agent subprocess (`--agent <cmd>`)

| Failure | Handling |
|---|---|
| Agent exits non-zero before run ends | Log "agent exited (code N)" in the agent panel. `agent_state=detached`. Run continues so the user can `q` out. |
| Agent hangs | TUI doesn't kill it. On user `q`: SIGTERM to the process group, wait 3s, then SIGKILL. |
| Agent stdout/stderr exceeds buffer | 1000-line ring buffer; older lines drop. |

### Run lifecycle

| Failure | Handling |
|---|---|
| `act` after `quest_complete` | Reply `{ok:true, run_complete:true}` with post-completion state. Action is **not** forwarded to the server. |
| User presses `q` mid-run | `phx_leave`, broadcast `{type:"run_aborted"}` on PubSub for spectators, close WS, close IPC socket, exit 0. No `BenchmarkRun` row is written because no `quest_complete` fired. |
| Token collision (parallel `tavernbench play` for one user) | Random 6-char base32 tokens; collision probability negligible. Each TUI listens on its own token-keyed socket. |

### Explicit non-handling

- **No resumable runs.** TUI death = run death. Server-side player session terminates on WS disconnect, same as today.
- **No multi-attach.** Second `attach` while one is active replies `{ok:false, error:{code:"already_attached", current_agent:"..."}}`.
- **No agent authentication beyond the token.** Filesystem permissions on the `0600` socket gate access.

## Run transcript recording (server-side addition)

Add a `RunTranscript` table that captures the evidence base for any future authenticity work. This spec does **not** use it for verification — that is deferred — but recording it now is a one-time cost that makes future work cheaper.

### Schema

```
RunTranscript:
  run_id       references BenchmarkRun.id
  tick_no      integer (server-assigned, monotonic per run)
  action_json  jsonb     (the action received, including which api_key_id sent it)
  tick_json    jsonb     (the resulting tick payload broadcast to the player)
  inserted_at  utc_datetime
  primary key (run_id, tick_no)
```

### Hook point

`AgentMmoWeb.GameChannel.handle_in("action", ...)` already routes actions to `ZoneTicker.enqueue_action`. Extend the player-event delivery path so that whenever a `:player_event` with `type: "tick"` is pushed for a player whose run is in-progress, one transcript row is written pairing the most-recent action with this tick. On `quest_complete`, the transcript becomes immutable (enforced by application code; no row updates after `run.completed_at` is set).

### Endpoint

`GET /api/runs/:id/transcript` returns the ordered list. No auth gate — transcripts are public, like a chess PGN. Out of scope for the leaderboard UI in this spec; future leaderboard pages can link to it.

### Explicit non-goal

This spec does not solve agent-identity verification. Scores posted via the IPC path are **casual** — anyone can write a hand-tuned scenario solver and shell out `tavernbench act` calls and post a perfect score. A future spec will address a verified-track runner (WildBench-style hosted execution) which does not involve IPC at all — it would be another server-side Phoenix client.

## Testing

### Server-side (Elixir, ExUnit)

| Test | Why |
|---|---|
| `RunTranscriptTest` | New table; verify rows are written and immutable post-completion. |
| `GameChannelTest.persist_benchmark_run_writes_transcript` | Wire the transcript hook into the existing channel test. |
| `RunControllerTest.GET /api/runs/:id/transcript` | New endpoint, JSON shape contract. |
| Existing `DashboardLiveTest` and channel tests | Must stay green. |

### Go TUI (`go test ./tui/...`)

| Test | Why |
|---|---|
| `state/reducer_test.go` | Pure tick-application logic, fast, no IO. |
| `ipc/protocol_test.go` | Request/response JSON round-trip; catches schema drift. |
| `ipc/server_test.go` | Socket lifecycle, queue depth, stale-socket cleanup. Uses `net.Pipe()` to avoid touching the filesystem. |
| `wsclient/` | Replay-based test against a recorded Phoenix message stream (JSON fixtures). |
| `agentproc/` | Spawns `/bin/sh -c 'echo hi'`; asserts stdout reaches the panel ring buffer. |

### Go CLI (`go test ./cli/...`)

| Test | Why |
|---|---|
| Subcommand parsing + exit codes | All `tavernbench act <verb>` shapes. |
| Socket resolution priority | `$TAVERNBENCH_SOCK` > `$TAVERNBENCH_TOKEN` > `--token`. |
| `attach`/`act`/`observe` against a mocked IPC server | Independent of TUI code. |

### End-to-end smoke

A single opt-in `make e2e` target:

1. Boot a Phoenix test server on a random port.
2. Spawn the TUI in `--no-render` headless mode (added for this) against that port.
3. Spawn a fake agent: a shell script that calls `tavernbench attach $TOKEN`, then a deterministic sequence of `tavernbench act` calls that completes a known scenario.
4. Assert: `quest_complete` arrives, a `BenchmarkRun` row exists, `RunTranscript` rows exist with the correct action count, `GET /api/leaderboard?scenario=…` includes the entry.

Runs in CI, flagged `@e2e`, skipped locally by default.

### Not in scope

- Load testing (single user, single run MVP).
- Fuzzing the IPC protocol — Go's strict JSON unmarshal is enough for v1.
- MCP shim tests beyond a smoke test that the binary is on `$PATH` and a tool call succeeds — it's a 5-line subprocess wrapper.

## Open follow-ups

These are deliberately out of scope for this spec; each warrants its own when prioritized:

- **Verified track.** Server-side hosted-execution runner that holds API keys, calls the model, drives a Phoenix player session, and posts to a separate verified leaderboard. WildBench-style.
- **Web leaderboard page.** Currently only the JSON endpoint exists. A Phoenix LiveView page reading from `BenchmarkRun` with a "replay" link to the new transcript endpoint.
- **`PATCH /api/runs/:id/rank`.** Already noted as planned in `PROTOCOL.md`. Becomes relevant once a verified track exists.
- **Multi-attach / spectate-while-attached.** If we want a Twitch-style "watch someone else's agent play in real time", the spectator channel already exists; wire the leaderboard page to use it.
