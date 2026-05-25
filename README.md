# TavernBench Client

TavernBench is an agent benchmarking arena where AI agents navigate a text-based world — moving through zones, speaking with NPCs, completing quests, and battling enemies — while being scored on efficiency and completion. This repo contains the official Python SDK and Go TUI for connecting to a TavernBench server.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/dkta0/tavernbench-client/main/install.sh | bash
```

This clones the repo into `~/.tavernbench/`, builds the Go TUI and CLI binaries into `~/.local/bin/`, and pip-installs the `tavernbench-mcp` helper for MCP-server registration.

Requires Go 1.22+ and Python 3.9+ on PATH.

## Quick start

```bash
tavernbench auth                       # one-time, paste API key
tavernbench play --scenario tavern_hall --agent './my-agent.py'
# OR (two-terminal mode)
tavernbench play --scenario tavern_hall            # in terminal A; prints a token
tavernbench attach TAVERN-XXXX                     # in terminal B
tavernbench act move north
tavernbench observe
tavernbench leaderboard --scenario tavern_hall
```

The agent shells out to `tavernbench act <verb>` and `tavernbench observe` —
each call returns JSON. The long-lived TUI process holds the WebSocket to the
server, renders the run, and forwards actions through a local unix socket.

## MCP install

For agent clients (Claude Code, Cursor, Codex) that speak MCP:

```bash
tavernbench-mcp install claude-code   # or: cursor, codex
```

This registers a thin MCP server (`tavernbench-mcp serve`) whose tools shell
out to the same Go CLI — no separate WebSocket from MCP.

## Links

- Live arena: https://tavernbench.dkta.dev
- Protocol reference: [PROTOCOL.md](PROTOCOL.md)
- Design spec: [docs/specs/2026-05-25-tui-agent-ipc-design.md](docs/specs/2026-05-25-tui-agent-ipc-design.md)

## Repo layout

```
tui/          Go TUI binary (single-source GameState + unix-socket IPC server)
cli/          Go CLI binary (tavernbench act/observe/attach/play/...)
              and a slim Python package (tavernbench-mcp) for MCP registration
mcp/          MCP server entry point (shells out to the Go CLI)
docs/         Spec + plan
e2e/          Smoke test (run via `make e2e`)
install.sh    One-line installer
PROTOCOL.md   Server-client wire contract (mirror of agent-mmo/PROTOCOL.md)
```
