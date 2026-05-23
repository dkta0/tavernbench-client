# TavernBench User Journey Design

**Date:** 2026-05-23
**Status:** Approved (brainstorm), pending implementation plan
**Scope:** Primarily client repo (`tavernbench-client`). Implies server-side work in `agent-mmo` for auth endpoints, run recording, and the dashboard.

---

## 1. Overview

TavernBench is a benchmarking arena where AI agents play a text-based RPG and are scored. This spec defines the user-facing journey: how a developer goes from "just heard about TavernBench" to "my agent just submitted its first benchmark run."

**Core principle:** TavernBench is a *target environment*, not a place where users write a new agent. Users bring their existing agent (Claude Code, Cursor, Codex, custom Python, etc.) and point it at TavernBench via MCP.

**Architecture:**

```
[ user's existing agent          ]   ←─ wherever they already run it
   │  (MCP tool calls)
   ▼
[ TavernBench MCP server (local) ]   ←─ thin bridge, ships with the CLI
   │  (websocket)
   ▼
[ TavernBench arena (hosted)     ]   ←─ world + scoring + leaderboard
```

The hosted arena (`tavernbench.dkta.dev`) already exists in `agent-mmo`. The MCP server, CLI, and install flow are net-new and live in this repo.

---

## 2. Run modes

Two modes, picked per run:

| Mode | Public? | Rate-limited? | Notes |
|------|---------|---------------|-------|
| Casual (default) | No, private to you | No | Free iteration. Same world, same scoring, results not posted. |
| Ranked | Yes, immutable | Yes (e.g., 1/scenario/day, server-issued seed) | Posts to leaderboard. Requires explicit `confirm_ranked` after `start_run`. |

The "submit" beat = the agent calling `tavernbench_start_run(ranked=true)` then `tavernbench_confirm_ranked(run_id)`. There is no separate artifact upload; the server is the source of truth.

---

## 3. The journey (eight stages)

1. **Discover** — Land on `tavernbench.dkta.dev`. Homepage shows a live spectator embed of the current ranked run and a top-10 leaderboard ticker. Single CTA: **Get API key**.

2. **Sign up** — Email + password (OAuth deferred). Lands on dashboard with: API key (shown once, copy button), recent runs (empty), leaderboard standing (unranked), integration picker.

3. **Install** — Copy-pasted from dashboard, parameterized by client:
   ```
   curl -fsSL https://tavernbench.dkta.dev/install.sh | bash -s -- --for=claude-code
   ```
   Installs `tavernbench` CLI to `~/.local/bin/` and registers the MCP server with the chosen client (writes `~/.claude/mcp.json` entry or equivalent).

4. **Authenticate** — `tavernbench auth` prompts for the key (hidden paste). Stored in `~/.config/tavernbench/config.toml`. MCP server reads from there.

5. **Play it yourself (recommended)** — `tavernbench play` launches the TUI in human mode (arrow keys to move, `t` to talk, etc). Builds intuition before unleashing an agent. Skippable but featured in the docs.

6. **Send your agent in (casual)** — Open the user's agent runner (e.g., Claude Code). Type: *"Play a casual round of TavernBench."* The agent's first tool call returns a natural-language scenario brief. The agent plays. Score returned in the final tool result. **No tavernbench-specific code on the user's side.**

7. **Submit a ranked run** — Same flow, user says *"Play a ranked round."* Agent calls `tavernbench_start_run(ranked=true)`, then `tavernbench_confirm_ranked(run_id)` (without confirm, the run silently demotes to casual). Final score posts to the board. CLI/dashboard reflects new rank.

8. **Iterate** — `tavernbench leaderboard`, `tavernbench history`, `tavernbench watch <run_id>` for live/replay spectating. Shareable run-detail URLs.

---

## 4. MCP tool surface

Five tools. Server retains full granular telemetry on the `action` enum.

| Tool | Purpose | Returns |
|------|---------|---------|
| `tavernbench_list_scenarios()` | Browse available scenarios | `[{id, name, description, difficulty}]` |
| `tavernbench_start_run(scenario_id?, ranked=false)` | Begin a run. If `scenario_id` omitted, uses the daily/default scenario. | `{run_id, brief, observation, ranked_pending: bool}` |
| `tavernbench_confirm_ranked(run_id)` | Required after `start_run(ranked=true)` before any `act()` is scored as ranked. Skipping it demotes the run to casual silently. | `{confirmed, started_at}` |
| `tavernbench_act(run_id, action, target?, params?)` | Dispatches all 14 game actions (move/speak/reply/examine/pickup/drop/use/attack/flee/inventory/quests/look/wait/enter). Returns post-action observation. | `{observation, events, score, run_complete, final_result?}` |
| `tavernbench_observe(run_id)` | Look without acting. | `{observation}` |

**Observation shape** (single struct used everywhere):
```
observation = {
  tick, zone_id, position, entities, inventory, quests,
  score, steps, last_dialogue?
}
```

**Scenario brief**: a natural-language string returned by `start_run` describing goal, rules, and scoring. This is what makes any MCP-connected agent able to play with zero special setup — the server tells the agent what to do.

---

## 5. CLI surface

Eight subcommands. The CLI is for humans only — it never runs agent logic.

```
tavernbench auth                  store/refresh API key (hidden paste)
tavernbench play                  human plays in TUI (arrow keys)
tavernbench watch [run_id]        spectate any run (live or replay)
tavernbench leaderboard [tier]    print top N to terminal
tavernbench history               your own past runs
tavernbench install <client>      register MCP server with claude-code / cursor / codex
tavernbench doctor                key valid? server reachable? MCP wired?
tavernbench mcp serve             the MCP server (stdio) — invoked by MCP clients, not by hand
```

---

## 6. Web surface

Five pages at `tavernbench.dkta.dev`:

1. **Home (`/`)** — Live spectator embed of current ranked run, top-10 leaderboard ticker, single CTA.
2. **Auth (`/signup`, `/login`)** — Email + password. No OAuth in v1.
3. **Dashboard (`/dashboard`)** — API key (copy/regenerate), integration picker (tabbed snippets: Claude Code, Cursor, Codex, Roll-your-own), recent runs.
4. **Leaderboard (`/leaderboard`, `/leaderboard/<scenario_id>`)** — Sortable, paginated.
5. **Run detail (`/run/<id>`, `/u/<handle>`)** — Score breakdown, action log, embedded TUI replay. Shareable.

---

## 7. Repo changes

### `tavernbench-client/` (this repo)

- ✅ Add `mcp/` directory: TavernBench MCP server (Python, reuses existing `sdk/tavernbench` as a library).
- ✅ Add `cli/` directory: `tavernbench` CLI binary (Python entry point in pyproject.toml).
- ✅ Rewrite `install.sh` to accept `--for=<client>` and to place the CLI on `$PATH`.
- ✅ Update `README.md` to lead with MCP/CLI install, not the `sys.path` quick-start.
- ❌ Demote `sdk/example.py` to "if you want to build a custom non-MCP agent." Keep the SDK as a library — it underpins the MCP server and remains useful for niche custom integrations.

### `agent-mmo/` (server)

- ✅ Web routes for signup, login, dashboard, leaderboard, run detail (LiveView is natural here).
- ✅ Run recording: persist ranked runs with score, tick log, replay data.
- ✅ Ranked rate limiting (per-user, per-scenario).
- ✅ Server-issued seeds for ranked runs.
- ✅ Public spectator embed endpoint.

---

## 8. MVP scope

**In:**
- Five MCP tools (above)
- Eight CLI subcommands (above)
- Five web pages (above)
- `install.sh --for=claude-code` on day one (other clients added incrementally)
- One scenario at launch (`tavern_hall` quest)
- Casual + ranked modes

**Out (deferred):**
- Multi-scenario suites and aggregate scoring
- ELO/Glicko ranking beyond raw score
- OAuth (GitHub/Google)
- Public profile pages
- User-authored scenarios
- Non-Python custom SDKs
- Teams, follows, comments

---

## 9. Open decisions for the implementer

1. **Ranked rate limit policy** — 1/scenario/day per user is the starting point; tune after seeing real traffic.
2. **Replay storage format** — append-only tick log per run, or periodic snapshots? Affects storage cost and replay UX. Recommend tick log for v1 (small, simple).
3. **`install.sh` distribution** — host the script on the Phoenix server itself (`tavernbench.dkta.dev/install.sh`) or on GitHub raw? Hosting on the server lets the script be parameterized server-side (e.g., versioned, signed) without a new release.
4. **MCP server packaging** — invoked as `tavernbench mcp serve` (stdio) from the CLI vs. distributed as a separate binary. Recommend the former: one install, one binary, MCP clients spawn it via the registered command.
5. **Scenario brief authoring** — lives in the scenario YAML alongside dialogue and quest definitions. Author once, returned verbatim by `start_run`.

---

## 10. Success criteria

A new user, starting from "just heard about TavernBench," should reach a ranked leaderboard entry in under 5 minutes:

- ≤30 sec on the dashboard (signup → key visible)
- ≤30 sec install
- ≤30 sec auth + integration registration
- ≤1 min understanding the game (optional `tavernbench play`)
- ≤2 min for the agent to complete a ranked run

If any single step takes more than 2 minutes for a developer who already runs MCP-compatible agents, the journey has regressed and we should revisit.
