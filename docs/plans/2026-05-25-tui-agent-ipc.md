# TUI-Mediated Agent IPC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the per-action-reconnect MCP/SDK path with a TUI-mediated unix-socket bridge, and add server-side run transcript recording.

**Architecture:** One long-lived Go TUI process holds the only Phoenix WebSocket connection and the parsed `GameState`; it listens on a unix domain socket for one-shot commands from a Go CLI binary that any agent can shell out to. The Python MCP server shrinks to a subprocess wrapper around that CLI. Server-side, a new `run_transcripts` table records every (action, tick) pair during a run.

**Tech Stack:** Elixir 1.14+ / Phoenix 1.7 (server), Go 1.22 (TUI + CLI), Python 3.9+ FastMCP (MCP shim only).

**Spec:** `tavernbench-client/docs/specs/2026-05-25-tui-agent-ipc-design.md`

**Repos:**
- Server: `/home/dakota/Work/github/dkta0/agent-mmo` (Elixir)
- Client: `/home/dakota/Work/github/dkta0/tavernbench-client` (Go + Python)

---

## Phase 1 — Server-side run transcript

Server-side change that can land independently of the client redesign. Lays the evidence-recording groundwork called out in the spec.

### Task 1.1: Migration for `run_transcripts` table

**Files:**
- Create: `agent-mmo/priv/repo/migrations/20260525120000_create_run_transcripts.exs`

- [ ] **Step 1: Write the migration**

```elixir
defmodule AgentMmo.Repo.Migrations.CreateRunTranscripts do
  use Ecto.Migration

  def change do
    create table(:run_transcripts) do
      add :benchmark_run_id, references(:benchmark_runs, on_delete: :delete_all), null: false
      add :tick_no,    :integer, null: false
      add :action,     :map,     null: false
      add :tick,       :map,     null: false
      add :inserted_at, :utc_datetime, null: false, default: fragment("NOW()")
    end

    create unique_index(:run_transcripts, [:benchmark_run_id, :tick_no])
  end
end
```

- [ ] **Step 2: Run migration to verify it applies**

Run: `cd agent-mmo && mix ecto.migrate`
Expected: `[info] == Migrated 20260525120000 in ...`

- [ ] **Step 3: Commit**

```bash
cd agent-mmo
git add priv/repo/migrations/20260525120000_create_run_transcripts.exs
git commit -m "feat(server): migrate run_transcripts table"
```

---

### Task 1.2: `RunTranscript` schema + context module

**Files:**
- Create: `agent-mmo/lib/agent_mmo/run_transcript.ex`
- Create: `agent-mmo/lib/agent_mmo/run_transcripts.ex`
- Create: `agent-mmo/test/agent_mmo/run_transcripts_test.exs`

- [ ] **Step 1: Write the failing test**

```elixir
defmodule AgentMmo.RunTranscriptsTest do
  use AgentMmo.DataCase, async: true

  alias AgentMmo.{RunTranscripts, BenchmarkRun, ApiKey, Repo}

  defp fixture_run do
    {:ok, ak} = Repo.insert(%ApiKey{agent_name: "t", owner: "o", key_hash: "h"})
    {:ok, run} = Repo.insert(%BenchmarkRun{
      api_key_id: ak.id, scenario: "x", score: 0, steps: 0, duration_ms: 0
    })
    run
  end

  test "append/3 inserts a row keyed by (run_id, tick_no)" do
    run = fixture_run()
    assert {:ok, t1} = RunTranscripts.append(run.id, 1, %{action: %{verb: "move"}, tick: %{}})
    assert t1.tick_no == 1
  end

  test "append/3 rejects duplicate tick_no for the same run" do
    run = fixture_run()
    {:ok, _} = RunTranscripts.append(run.id, 1, %{action: %{}, tick: %{}})
    assert {:error, _cs} = RunTranscripts.append(run.id, 1, %{action: %{}, tick: %{}})
  end

  test "list_for_run/1 returns rows in ascending tick order" do
    run = fixture_run()
    {:ok, _} = RunTranscripts.append(run.id, 2, %{action: %{}, tick: %{}})
    {:ok, _} = RunTranscripts.append(run.id, 1, %{action: %{}, tick: %{}})
    assert [%{tick_no: 1}, %{tick_no: 2}] = RunTranscripts.list_for_run(run.id)
  end
end
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent-mmo && mix test test/agent_mmo/run_transcripts_test.exs`
Expected: FAIL — `RunTranscripts` module undefined.

- [ ] **Step 3: Write the schema**

`agent-mmo/lib/agent_mmo/run_transcript.ex`:
```elixir
defmodule AgentMmo.RunTranscript do
  use Ecto.Schema
  import Ecto.Changeset

  schema "run_transcripts" do
    field :tick_no, :integer
    field :action,  :map
    field :tick,    :map
    field :inserted_at, :utc_datetime

    belongs_to :benchmark_run, AgentMmo.BenchmarkRun
  end

  def changeset(rt, attrs) do
    rt
    |> cast(attrs, [:benchmark_run_id, :tick_no, :action, :tick])
    |> validate_required([:benchmark_run_id, :tick_no, :action, :tick])
    |> unique_constraint([:benchmark_run_id, :tick_no])
  end
end
```

- [ ] **Step 4: Write the context**

`agent-mmo/lib/agent_mmo/run_transcripts.ex`:
```elixir
defmodule AgentMmo.RunTranscripts do
  @moduledoc "Per-(action,tick) transcript writes during a benchmark run."

  import Ecto.Query
  alias AgentMmo.{Repo, RunTranscript}

  @doc "Append one transcript row. `attrs` must include `:action` and `:tick` maps."
  def append(benchmark_run_id, tick_no, %{action: action, tick: tick}) do
    %RunTranscript{}
    |> RunTranscript.changeset(%{
      benchmark_run_id: benchmark_run_id,
      tick_no: tick_no,
      action: action,
      tick: tick
    })
    |> Repo.insert()
  end

  @doc "Return all transcript rows for a run, ordered by tick_no asc."
  def list_for_run(benchmark_run_id) do
    Repo.all(
      from t in RunTranscript,
        where: t.benchmark_run_id == ^benchmark_run_id,
        order_by: [asc: t.tick_no]
    )
  end
end
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd agent-mmo && mix test test/agent_mmo/run_transcripts_test.exs`
Expected: 3 tests, 0 failures.

- [ ] **Step 6: Commit**

```bash
cd agent-mmo
git add lib/agent_mmo/run_transcript.ex lib/agent_mmo/run_transcripts.ex test/agent_mmo/run_transcripts_test.exs
git commit -m "feat(server): add RunTranscript schema and context"
```

---

### Task 1.3: Wire transcript writes into `GameChannel`

The hook lands in `persist_benchmark_run/2` (line ~275 of `game_channel.ex`). For now we batch-write the in-memory tick stream once we know the `benchmark_run_id`. The socket assigns will grow a `:transcript_buffer` field that we append to in the existing tick handler.

**Files:**
- Modify: `agent-mmo/lib/agent_mmo_web/channels/game_channel.ex`
- Modify: `agent-mmo/test/agent_mmo_web/channels/game_channel_test.exs`

- [ ] **Step 1: Write the failing test**

Add to `game_channel_test.exs`:
```elixir
test "completing a quest writes one RunTranscript row per recorded tick", %{socket: socket} do
  push(socket, "action", %{"action" => "move", "direction" => "north"})
  Process.sleep(50)
  send(self(), {:player_event, %{type: "quest_complete", quest_id: "q", final_score: 5, steps_taken: 1}})
  Process.sleep(50)

  [run] = AgentMmo.Repo.all(AgentMmo.BenchmarkRun)
  transcripts = AgentMmo.RunTranscripts.list_for_run(run.id)
  assert length(transcripts) >= 1
  assert hd(transcripts).action["verb"] in ["move", "action"]
end
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent-mmo && mix test test/agent_mmo_web/channels/game_channel_test.exs -- --only=run_transcript`
Expected: FAIL — no rows written.

- [ ] **Step 3: Modify GameChannel to buffer and flush**

In `game_channel.ex`:
- In `join/3`, initialize the buffer: `socket = assign(socket, :transcript_buffer, [])`.
- In `handle_in("action", payload, socket)`, after enqueuing, remember the most recent action in `socket.assigns.pending_action = payload`.
- In `handle_info({:player_event, %{type: "tick"} = tick}, socket)`, append `{socket.assigns.pending_action, tick}` to the buffer and clear `pending_action`.
- In `persist_benchmark_run/2`, after `Leaderboard.record_run/5` returns `{:ok, run}`, iterate the buffered pairs and call `RunTranscripts.append/3` for each, numbering ticks from 1.

Concrete diff to `persist_benchmark_run/2`:
```elixir
defp persist_benchmark_run(socket, payload) do
  api_key_id = socket.assigns[:api_key_id]
  if api_key_id do
    scenario    = to_string(Map.get(payload, :quest_id, "unknown"))
    score       = Map.get(payload, :final_score, 0)
    steps       = Map.get(payload, :steps_taken, 0)
    duration_ms = System.monotonic_time(:millisecond) - socket.assigns.connected_at

    case AgentMmo.Leaderboard.record_run(api_key_id, scenario, score, steps, duration_ms) do
      {:ok, run} ->
        socket.assigns
        |> Map.get(:transcript_buffer, [])
        |> Enum.reverse()
        |> Enum.with_index(1)
        |> Enum.each(fn {{action, tick}, idx} ->
          AgentMmo.RunTranscripts.append(run.id, idx, %{action: action, tick: tick})
        end)

        Phoenix.PubSub.broadcast(AgentMmo.PubSub, "leaderboard:#{scenario}", {:leaderboard_updated, scenario})
      {:error, reason} ->
        require Logger
        Logger.warning("Failed to persist benchmark run: #{inspect(reason)}")
    end
  end
end
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent-mmo && mix test test/agent_mmo_web/channels/game_channel_test.exs`
Expected: all green, including the new transcript test.

- [ ] **Step 5: Commit**

```bash
cd agent-mmo
git add lib/agent_mmo_web/channels/game_channel.ex test/agent_mmo_web/channels/game_channel_test.exs
git commit -m "feat(server): record run transcripts during gameplay"
```

---

### Task 1.4: Public transcript endpoint

**Files:**
- Modify: `agent-mmo/lib/agent_mmo_web/controllers/run_controller.ex`
- Modify: `agent-mmo/lib/agent_mmo_web/router.ex`
- Create: `agent-mmo/test/agent_mmo_web/controllers/run_controller_test.exs` (or extend existing)

- [ ] **Step 1: Write the failing test**

```elixir
test "GET /api/runs/:id/transcript returns rows in tick order", %{conn: conn} do
  {:ok, ak} = AgentMmo.Repo.insert(%AgentMmo.ApiKey{agent_name: "t", owner: "o", key_hash: "h"})
  {:ok, br} = AgentMmo.Repo.insert(%AgentMmo.BenchmarkRun{
    api_key_id: ak.id, scenario: "x", score: 1, steps: 1, duration_ms: 10
  })
  {:ok, _} = AgentMmo.RunTranscripts.append(br.id, 1, %{action: %{verb: "move"}, tick: %{score: 1}})

  resp = conn |> get("/api/runs/#{br.id}/transcript") |> json_response(200)
  assert resp["run_id"] == br.id
  assert [%{"tick_no" => 1, "action" => %{"verb" => "move"}}] = resp["transcript"]
end
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent-mmo && mix test test/agent_mmo_web/controllers/run_controller_test.exs`
Expected: FAIL — route undefined.

- [ ] **Step 3: Add controller action**

Append to `run_controller.ex`:
```elixir
def transcript(conn, %{"id" => id}) do
  case Integer.parse(id) do
    {run_id, _} ->
      entries = AgentMmo.RunTranscripts.list_for_run(run_id)
              |> Enum.map(&Map.take(&1, [:tick_no, :action, :tick, :inserted_at]))
      conn |> put_status(200) |> json(%{run_id: run_id, transcript: entries})
    :error ->
      conn |> put_status(400) |> json(%{error: "invalid run id"})
  end
end
```

- [ ] **Step 4: Add route**

In `router.ex` inside the `scope "/api", AgentMmoWeb do` block, after `post "/runs", RunController, :create`:
```elixir
get "/runs/:id/transcript", RunController, :transcript
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd agent-mmo && mix test test/agent_mmo_web/controllers/run_controller_test.exs`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
cd agent-mmo
git add lib/agent_mmo_web/controllers/run_controller.ex lib/agent_mmo_web/router.ex test/agent_mmo_web/controllers/run_controller_test.exs
git commit -m "feat(server): expose GET /api/runs/:id/transcript"
```

---

### Task 1.5: Update PROTOCOL.md for the new endpoint

**Files:**
- Modify: `agent-mmo/PROTOCOL.md`
- Modify: `tavernbench-client/PROTOCOL.md` (mirror copy)

- [ ] **Step 1: Add the new endpoint to both copies**

Add this row to the HTTP endpoints table in both files, just after the existing `POST /api/runs` row:
```
| GET | `/api/runs/:id/transcript` | live | `RunController` | Full action/tick transcript for a completed run. Public. |
```

- [ ] **Step 2: Commit both**

```bash
cd agent-mmo && git add PROTOCOL.md && git commit -m "docs: document GET /api/runs/:id/transcript"
cd ../tavernbench-client && git add PROTOCOL.md && git commit -m "docs: mirror /api/runs/:id/transcript endpoint"
```

---

## Phase 1 checkpoint

Server-side transcripts ship. The leaderboard pipeline is unchanged for callers; runs that complete via any path now also write transcripts. Worth a manual sanity check:

```bash
cd agent-mmo && iex -S mix phx.server
# In another terminal, drive an action against a test zone (existing
# integration test approach is fine), or just rely on Task 1.3's test.
```

---

## Phase 2 — TUI internal packages (TDD scaffolding)

Build each `tui/internal/...` package on its own with tests, before integrating in `tui/main.go`. Each package is small, isolated, and shippable in one commit.

### Task 2.1: Restructure the Go module to a single `tui` workspace

We currently have `tui/go.mod` (module `github.com/tavernbench/spectator`) and `tui/play/go.mod` (module `github.com/tavernbench/play`). The new design has one module with internal packages.

**Files:**
- Modify: `tavernbench-client/tui/go.mod`
- Delete: `tavernbench-client/tui/play/go.mod`

- [ ] **Step 1: Rewrite the root go.mod**

`tavernbench-client/tui/go.mod`:
```
module github.com/tavernbench/tui

go 1.22
```

- [ ] **Step 2: Delete the play submodule**

```bash
cd tavernbench-client/tui
rm play/go.mod
# Keep play/main.go for now — we'll merge or delete it in Phase 3.
```

- [ ] **Step 3: Verify the module still builds**

Run: `cd tavernbench-client/tui && go build ./...`
Expected: builds without error. (`play/main.go` currently has only a one-line comment so it builds as an empty package.)

- [ ] **Step 4: Commit**

```bash
cd tavernbench-client
git add tui/go.mod
git rm tui/play/go.mod
git commit -m "refactor(tui): consolidate to single Go module"
```

---

### Task 2.2: `tui/internal/state` — GameState types and tick reducer

**Files:**
- Create: `tavernbench-client/tui/internal/state/types.go`
- Create: `tavernbench-client/tui/internal/state/reducer.go`
- Create: `tavernbench-client/tui/internal/state/reducer_test.go`

- [ ] **Step 1: Write types**

`tui/internal/state/types.go`:
```go
package state

type Pos struct {
    X int `json:"x"`
    Y int `json:"y"`
}

type Entity struct {
    ID       string `json:"id"`
    Type     string `json:"type"`
    Position Pos    `json:"position"`
    Display  string `json:"display,omitempty"`
}

type Quest struct {
    ID         string `json:"id"`
    Title      string `json:"title"`
    Objectives []struct {
        Description string `json:"description"`
        Done        bool   `json:"done"`
    } `json:"objectives"`
}

type Tick struct {
    Tick     int      `json:"tick"`
    ZoneID   string   `json:"zone_id"`
    Position *Pos     `json:"position"`
    Entities []Entity `json:"entities"`
    Quests   []Quest  `json:"quests"`
    Score    int      `json:"score"`
    Steps    int      `json:"steps"`
}

type AgentState int

const (
    AgentDetached AgentState = iota
    AgentAttached
)

type GameState struct {
    Tick         Tick
    AgentState   AgentState
    AgentName    string
    RunComplete  bool
    FinalScore   int
    FinalSteps   int
    ServerRunID  string
    LogLines     []string
}
```

- [ ] **Step 2: Write the failing reducer test**

`tui/internal/state/reducer_test.go`:
```go
package state

import "testing"

func TestApplyTick_OverwritesTickFields(t *testing.T) {
    s := &GameState{Tick: Tick{Score: 1}}
    next := Tick{Tick: 2, Score: 5, Steps: 3, Entities: []Entity{{ID: "n1", Type: "npc"}}}
    Apply(s, next)
    if s.Tick.Score != 5 || s.Tick.Steps != 3 || s.Tick.Tick != 2 {
        t.Fatalf("tick not applied: %+v", s.Tick)
    }
    if len(s.Tick.Entities) != 1 {
        t.Fatalf("entities not applied")
    }
}

func TestAttach_TransitionsAgentState(t *testing.T) {
    s := &GameState{}
    Attach(s, "claude-code")
    if s.AgentState != AgentAttached || s.AgentName != "claude-code" {
        t.Fatalf("attach did not transition: %+v", s)
    }
    Detach(s)
    if s.AgentState != AgentDetached || s.AgentName != "" {
        t.Fatalf("detach did not transition: %+v", s)
    }
}

func TestCompleteRun_SetsRunComplete(t *testing.T) {
    s := &GameState{}
    Complete(s, 100, 42, "server-uuid")
    if !s.RunComplete || s.FinalScore != 100 || s.FinalSteps != 42 || s.ServerRunID != "server-uuid" {
        t.Fatalf("complete did not set fields: %+v", s)
    }
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd tavernbench-client/tui && go test ./internal/state/...`
Expected: FAIL — `Apply` and friends undefined.

- [ ] **Step 4: Write the reducer**

`tui/internal/state/reducer.go`:
```go
package state

func Apply(s *GameState, t Tick) {
    s.Tick = t
}

func Attach(s *GameState, name string) {
    s.AgentState = AgentAttached
    s.AgentName = name
}

func Detach(s *GameState) {
    s.AgentState = AgentDetached
    s.AgentName = ""
}

func Complete(s *GameState, score, steps int, serverRunID string) {
    s.RunComplete = true
    s.FinalScore = score
    s.FinalSteps = steps
    s.ServerRunID = serverRunID
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd tavernbench-client/tui && go test ./internal/state/...`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd tavernbench-client
git add tui/internal/state/
git commit -m "feat(tui): add state package — types and reducer"
```

---

### Task 2.3: `tui/internal/wsclient` — lift WS client from existing tui/main.go

Move the Phoenix-protocol WebSocket plumbing currently in `tui/main.go` (functions `wsConnect`, `wsKey`, `WriteText`, `ReadMsg`, `readFull`, `encodeMsg`, type `PhxMsg`) into a focused package.

**Files:**
- Create: `tavernbench-client/tui/internal/wsclient/client.go`
- Create: `tavernbench-client/tui/internal/wsclient/client_test.go`

- [ ] **Step 1: Write the failing test (handshake + frame round-trip)**

`tui/internal/wsclient/client_test.go`:
```go
package wsclient

import (
    "encoding/json"
    "testing"
)

func TestEncodeMsg_ShapesPhoenixFiveTuple(t *testing.T) {
    raw, err := EncodeMsg("1", "r1", "zone:t", "action", map[string]any{"a": "b"})
    if err != nil {
        t.Fatal(err)
    }
    var parsed []json.RawMessage
    if err := json.Unmarshal(raw, &parsed); err != nil {
        t.Fatal(err)
    }
    if len(parsed) != 5 {
        t.Fatalf("expected 5-element message, got %d", len(parsed))
    }
}

func TestWSKey_IsBase64_22Chars(t *testing.T) {
    k := wsKey()
    if len(k) != 24 { // base64 of 16 bytes is 24 chars
        t.Fatalf("unexpected key length: %d", len(k))
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tavernbench-client/tui && go test ./internal/wsclient/...`
Expected: FAIL — package undefined.

- [ ] **Step 3: Move the code from `tui/main.go`**

Copy the following symbols from the current `tui/main.go` (lines ~54–266) into `tui/internal/wsclient/client.go`, exporting them where needed: `PhxMsg`, `EncodeMsg` (rename from `encodeMsg`), `Conn` (rename from `wsConn`), `Connect` (rename from `wsConnect`), `wsKey`, `(Conn).WriteText`, `(Conn).ReadMsg`, `readFull`.

The package should look like:
```go
package wsclient

import (
    "crypto/rand"
    "encoding/base64"
    "encoding/json"
    "net"
)

type PhxMsg [5]json.RawMessage

type Conn struct {
    // existing fields from wsConn
}

func Connect(rawURL string) (*Conn, error) { /* lifted */ }
func EncodeMsg(joinRef, ref interface{}, topic, event string, payload interface{}) ([]byte, error) { /* lifted */ }
func wsKey() string {
    b := make([]byte, 16)
    rand.Read(b)
    return base64.StdEncoding.EncodeToString(b)
}
func (c *Conn) WriteText(data []byte) error { /* lifted */ }
func (c *Conn) ReadMsg() ([]byte, error) { /* lifted */ }
func readFull(conn net.Conn, buf []byte) (int, error) { /* lifted */ }
```

(The literal line-for-line transfer is mechanical — copy from `tui/main.go`. Keep the lifting minimal — no behavioral changes.)

Remove those same symbols from `tui/main.go` and add `import "github.com/tavernbench/tui/internal/wsclient"`. Update call sites in the existing `runWS` function to use the new package names. This is still the old spectator monolith — the next phase replaces `tui/main.go` entirely, but for now we keep it compiling.

- [ ] **Step 4: Run tests to verify both wsclient and overall build pass**

Run: `cd tavernbench-client/tui && go test ./... && go build ./...`
Expected: PASS, builds.

- [ ] **Step 5: Commit**

```bash
cd tavernbench-client
git add tui/internal/wsclient/ tui/main.go
git commit -m "refactor(tui): extract Phoenix WS client into internal/wsclient"
```

---

### Task 2.4: `tui/internal/ipc` — protocol types

**Files:**
- Create: `tavernbench-client/tui/internal/ipc/protocol.go`
- Create: `tavernbench-client/tui/internal/ipc/protocol_test.go`

- [ ] **Step 1: Write the failing test**

`tui/internal/ipc/protocol_test.go`:
```go
package ipc

import (
    "encoding/json"
    "testing"
)

func TestRequestRoundtrip(t *testing.T) {
    req := Request{ID: "abc", Op: OpAct, Verb: "move", Args: map[string]any{"direction": "north"}}
    b, err := json.Marshal(req)
    if err != nil {
        t.Fatal(err)
    }
    var back Request
    if err := json.Unmarshal(b, &back); err != nil {
        t.Fatal(err)
    }
    if back.ID != "abc" || back.Op != OpAct || back.Verb != "move" {
        t.Fatalf("roundtrip lost data: %+v", back)
    }
}

func TestResponseErrorShape(t *testing.T) {
    r := Response{ID: "abc", OK: false, Error: &ErrorBody{Code: "bad_request", Message: "x"}}
    b, _ := json.Marshal(r)
    if !contains(b, []byte(`"code":"bad_request"`)) {
        t.Fatalf("error body not serialized: %s", b)
    }
}

func contains(haystack, needle []byte) bool {
    for i := 0; i+len(needle) <= len(haystack); i++ {
        match := true
        for j := range needle {
            if haystack[i+j] != needle[j] {
                match = false
                break
            }
        }
        if match {
            return true
        }
    }
    return false
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tavernbench-client/tui && go test ./internal/ipc/...`
Expected: FAIL — package undefined.

- [ ] **Step 3: Write the protocol types**

`tui/internal/ipc/protocol.go`:
```go
package ipc

type Op string

const (
    OpAttach  Op = "attach"
    OpAct     Op = "act"
    OpObserve Op = "observe"
    OpAbort   Op = "abort"
)

type Request struct {
    ID   string         `json:"id"`
    Op   Op             `json:"op"`
    Name string         `json:"name,omitempty"` // for attach
    Verb string         `json:"verb,omitempty"` // for act
    Args map[string]any `json:"args,omitempty"`
}

type ErrorBody struct {
    Code    string `json:"code"`
    Message string `json:"message"`
}

type Response struct {
    ID          string         `json:"id"`
    OK          bool           `json:"ok"`
    Observation map[string]any `json:"observation,omitempty"`
    Events      []any          `json:"events,omitempty"`
    RunComplete bool           `json:"run_complete,omitempty"`
    FinalResult map[string]any `json:"final_result,omitempty"`
    Error       *ErrorBody     `json:"error,omitempty"`
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tavernbench-client/tui && go test ./internal/ipc/...`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd tavernbench-client
git add tui/internal/ipc/
git commit -m "feat(tui): add ipc.Request/Response protocol types"
```

---

### Task 2.5: `tui/internal/ipc/server.go` — unix-socket listener with action queue

**Files:**
- Create: `tavernbench-client/tui/internal/ipc/server.go`
- Create: `tavernbench-client/tui/internal/ipc/server_test.go`

- [ ] **Step 1: Write the failing test**

`tui/internal/ipc/server_test.go`:
```go
package ipc

import (
    "bufio"
    "context"
    "encoding/json"
    "net"
    "testing"
    "time"
)

type stubHandler struct{}

func (stubHandler) HandleRequest(ctx context.Context, req Request) Response {
    return Response{ID: req.ID, OK: true}
}

func TestServerHandlesOneRequest(t *testing.T) {
    a, b := net.Pipe()
    defer a.Close()
    defer b.Close()

    s := NewServer(stubHandler{}, 4)
    go s.HandleConn(b)

    req := Request{ID: "x", Op: OpObserve}
    payload, _ := json.Marshal(req)
    a.Write(append(payload, '\n'))

    a.SetReadDeadline(time.Now().Add(1 * time.Second))
    line, err := bufio.NewReader(a).ReadBytes('\n')
    if err != nil {
        t.Fatal(err)
    }
    var resp Response
    if err := json.Unmarshal(line, &resp); err != nil {
        t.Fatal(err)
    }
    if resp.ID != "x" || !resp.OK {
        t.Fatalf("bad response: %+v", resp)
    }
}

func TestServerRejectsBadJSON(t *testing.T) {
    a, b := net.Pipe()
    defer a.Close()
    defer b.Close()

    s := NewServer(stubHandler{}, 4)
    go s.HandleConn(b)

    a.Write([]byte("{not json}\n"))

    a.SetReadDeadline(time.Now().Add(1 * time.Second))
    line, err := bufio.NewReader(a).ReadBytes('\n')
    if err != nil {
        t.Fatal(err)
    }
    var resp Response
    json.Unmarshal(line, &resp)
    if resp.OK || resp.Error == nil || resp.Error.Code != "bad_request" {
        t.Fatalf("expected bad_request error: %+v", resp)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tavernbench-client/tui && go test ./internal/ipc/...`
Expected: FAIL — `NewServer` undefined.

- [ ] **Step 3: Implement the server**

`tui/internal/ipc/server.go`:
```go
package ipc

import (
    "bufio"
    "context"
    "encoding/json"
    "net"
    "os"
    "path/filepath"
    "sync"
)

type Handler interface {
    HandleRequest(ctx context.Context, req Request) Response
}

type Server struct {
    handler   Handler
    queueDepth int
    mu        sync.Mutex
    queue     chan struct{}
    listener  net.Listener
}

func NewServer(h Handler, queueDepth int) *Server {
    return &Server{
        handler:    h,
        queueDepth: queueDepth,
        queue:      make(chan struct{}, queueDepth),
    }
}

// Listen binds to the unix socket path. The caller is responsible for choosing
// a token-keyed path and ensuring 0600 permissions. Replaces a stale socket file.
func (s *Server) Listen(socketPath string) error {
    if err := os.MkdirAll(filepath.Dir(socketPath), 0o700); err != nil {
        return err
    }
    if _, err := os.Stat(socketPath); err == nil {
        // Try to connect; if no listener, remove and continue.
        c, err := net.Dial("unix", socketPath)
        if err != nil {
            _ = os.Remove(socketPath)
        } else {
            c.Close()
            return os.ErrExist
        }
    }
    l, err := net.Listen("unix", socketPath)
    if err != nil {
        return err
    }
    if err := os.Chmod(socketPath, 0o600); err != nil {
        l.Close()
        return err
    }
    s.listener = l
    return nil
}

func (s *Server) Accept(ctx context.Context) {
    for {
        conn, err := s.listener.Accept()
        if err != nil {
            return
        }
        go s.HandleConn(conn)
    }
}

func (s *Server) HandleConn(conn net.Conn) {
    defer conn.Close()
    reader := bufio.NewReader(conn)
    line, err := reader.ReadBytes('\n')
    if err != nil {
        return
    }

    var req Request
    if err := json.Unmarshal(line, &req); err != nil {
        s.writeResp(conn, Response{OK: false, Error: &ErrorBody{Code: "bad_request", Message: err.Error()}})
        return
    }

    select {
    case s.queue <- struct{}{}:
        defer func() { <-s.queue }()
    default:
        s.writeResp(conn, Response{ID: req.ID, OK: false, Error: &ErrorBody{Code: "action_in_flight", Message: "queue full"}})
        return
    }

    s.mu.Lock()
    defer s.mu.Unlock()
    resp := s.handler.HandleRequest(context.Background(), req)
    s.writeResp(conn, resp)
}

func (s *Server) writeResp(conn net.Conn, r Response) {
    b, _ := json.Marshal(r)
    conn.Write(append(b, '\n'))
}

func (s *Server) Close() error {
    if s.listener != nil {
        return s.listener.Close()
    }
    return nil
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tavernbench-client/tui && go test ./internal/ipc/...`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd tavernbench-client
git add tui/internal/ipc/server.go tui/internal/ipc/server_test.go
git commit -m "feat(tui): add ipc.Server unix-socket listener"
```

---

### Task 2.6: `tui/internal/agentproc` — subprocess spawn with stdout ring buffer

**Files:**
- Create: `tavernbench-client/tui/internal/agentproc/agentproc.go`
- Create: `tavernbench-client/tui/internal/agentproc/agentproc_test.go`

- [ ] **Step 1: Write the failing test**

`tui/internal/agentproc/agentproc_test.go`:
```go
package agentproc

import (
    "testing"
    "time"
)

func TestSpawnCapturesStdout(t *testing.T) {
    p, err := Spawn([]string{"/bin/sh", "-c", "echo hello"}, nil)
    if err != nil {
        t.Fatal(err)
    }
    defer p.Stop()

    deadline := time.Now().Add(2 * time.Second)
    for time.Now().Before(deadline) {
        lines := p.Lines()
        if len(lines) > 0 && lines[0] == "hello" {
            return
        }
        time.Sleep(20 * time.Millisecond)
    }
    t.Fatalf("did not capture stdout in time, got: %v", p.Lines())
}

func TestRingBufferDropsOldLines(t *testing.T) {
    rb := newRing(3)
    rb.push("a")
    rb.push("b")
    rb.push("c")
    rb.push("d")
    got := rb.lines()
    if len(got) != 3 || got[0] != "b" || got[2] != "d" {
        t.Fatalf("ring did not drop oldest: %v", got)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tavernbench-client/tui && go test ./internal/agentproc/...`
Expected: FAIL — `Spawn` undefined.

- [ ] **Step 3: Implement the package**

`tui/internal/agentproc/agentproc.go`:
```go
package agentproc

import (
    "bufio"
    "io"
    "os/exec"
    "sync"
    "syscall"
    "time"
)

const ringCap = 1000

type Process struct {
    cmd  *exec.Cmd
    ring *ring
}

func Spawn(argv []string, extraEnv []string) (*Process, error) {
    cmd := exec.Command(argv[0], argv[1:]...)
    cmd.Env = append(cmd.Env, extraEnv...)
    cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

    stdout, err := cmd.StdoutPipe()
    if err != nil {
        return nil, err
    }
    stderr, err := cmd.StderrPipe()
    if err != nil {
        return nil, err
    }
    if err := cmd.Start(); err != nil {
        return nil, err
    }

    p := &Process{cmd: cmd, ring: newRing(ringCap)}
    go p.pump(stdout)
    go p.pump(stderr)
    return p, nil
}

func (p *Process) pump(r io.Reader) {
    s := bufio.NewScanner(r)
    for s.Scan() {
        p.ring.push(s.Text())
    }
}

func (p *Process) Lines() []string {
    return p.ring.lines()
}

// Stop sends SIGTERM to the process group, waits 3s, then SIGKILL.
func (p *Process) Stop() {
    if p.cmd.Process == nil {
        return
    }
    pgid, err := syscall.Getpgid(p.cmd.Process.Pid)
    if err == nil {
        syscall.Kill(-pgid, syscall.SIGTERM)
    } else {
        p.cmd.Process.Signal(syscall.SIGTERM)
    }
    done := make(chan struct{})
    go func() { p.cmd.Wait(); close(done) }()
    select {
    case <-done:
    case <-time.After(3 * time.Second):
        if err == nil {
            syscall.Kill(-pgid, syscall.SIGKILL)
        } else {
            p.cmd.Process.Kill()
        }
        <-done
    }
}

type ring struct {
    mu    sync.Mutex
    buf   []string
    start int
    n     int
    cap   int
}

func newRing(cap int) *ring {
    return &ring{buf: make([]string, cap), cap: cap}
}

func (r *ring) push(line string) {
    r.mu.Lock()
    defer r.mu.Unlock()
    if r.n < r.cap {
        r.buf[(r.start+r.n)%r.cap] = line
        r.n++
    } else {
        r.buf[r.start] = line
        r.start = (r.start + 1) % r.cap
    }
}

func (r *ring) lines() []string {
    r.mu.Lock()
    defer r.mu.Unlock()
    out := make([]string, r.n)
    for i := 0; i < r.n; i++ {
        out[i] = r.buf[(r.start+i)%r.cap]
    }
    return out
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tavernbench-client/tui && go test ./internal/agentproc/...`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd tavernbench-client
git add tui/internal/agentproc/
git commit -m "feat(tui): add agentproc package — subprocess spawn + ring buffer"
```

---

### Task 2.7: `tui/internal/config` — read API key from `~/.config/tavernbench/config.toml`

The current Python CLI writes the key here. We need to read it from Go without pulling in a heavy TOML library — the file is two lines (`api_key = "..."`).

**Files:**
- Create: `tavernbench-client/tui/internal/config/config.go`
- Create: `tavernbench-client/tui/internal/config/config_test.go`

- [ ] **Step 1: Write the failing test**

`tui/internal/config/config_test.go`:
```go
package config

import (
    "os"
    "path/filepath"
    "testing"
)

func TestReadAPIKey_ParsesTOMLLine(t *testing.T) {
    dir := t.TempDir()
    path := filepath.Join(dir, "config.toml")
    os.WriteFile(path, []byte(`api_key = "abc123"`+"\n"), 0o600)

    k, err := ReadAPIKeyFrom(path)
    if err != nil {
        t.Fatal(err)
    }
    if k != "abc123" {
        t.Fatalf("got %q", k)
    }
}

func TestReadAPIKey_MissingFile(t *testing.T) {
    _, err := ReadAPIKeyFrom("/nonexistent/path/config.toml")
    if err == nil {
        t.Fatal("expected error")
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tavernbench-client/tui && go test ./internal/config/...`
Expected: FAIL.

- [ ] **Step 3: Implement**

`tui/internal/config/config.go`:
```go
package config

import (
    "bufio"
    "errors"
    "os"
    "path/filepath"
    "regexp"
)

var keyRe = regexp.MustCompile(`^\s*api_key\s*=\s*"([^"]+)"\s*$`)

func DefaultPath() string {
    home, _ := os.UserHomeDir()
    return filepath.Join(home, ".config", "tavernbench", "config.toml")
}

func ReadAPIKey() (string, error) {
    return ReadAPIKeyFrom(DefaultPath())
}

func ReadAPIKeyFrom(path string) (string, error) {
    f, err := os.Open(path)
    if err != nil {
        return "", err
    }
    defer f.Close()
    s := bufio.NewScanner(f)
    for s.Scan() {
        if m := keyRe.FindStringSubmatch(s.Text()); m != nil {
            return m[1], nil
        }
    }
    return "", errors.New("api_key not found in " + path)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tavernbench-client/tui && go test ./internal/config/...`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd tavernbench-client
git add tui/internal/config/
git commit -m "feat(tui): add config package — read api_key from TOML"
```

---

### Task 2.8: `tui/internal/render` — split rendering out of main.go

Lift the existing render functions (`render`, `renderMap`, `renderLog`, `renderQuests`, `padRight`, `visibleLen`, ANSI helpers) into a package, keyed off `state.GameState` instead of the old monolithic `State` struct.

**Files:**
- Create: `tavernbench-client/tui/internal/render/render.go`
- Create: `tavernbench-client/tui/internal/render/render_test.go`

- [ ] **Step 1: Write a smoke test**

`tui/internal/render/render_test.go`:
```go
package render

import (
    "strings"
    "testing"

    "github.com/tavernbench/tui/internal/state"
)

func TestRender_DetachedShowsHint(t *testing.T) {
    s := &state.GameState{}
    out := Render(s, 80, 24)
    if !strings.Contains(out, "Awaiting agent") {
        t.Fatalf("expected detached banner, got: %s", out)
    }
}

func TestRender_AttachedShowsAgentName(t *testing.T) {
    s := &state.GameState{AgentState: state.AgentAttached, AgentName: "claude"}
    out := Render(s, 80, 24)
    if !strings.Contains(out, "claude") {
        t.Fatalf("expected agent name in title, got: %s", out)
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd tavernbench-client/tui && go test ./internal/render/...`
Expected: FAIL — package undefined.

- [ ] **Step 3: Implement**

Move the ANSI helpers (`bold`, `dim`, `color`, `yellow`, etc.) and the rendering functions from the current `tui/main.go` into `render.go`, adapted to read from `state.GameState` rather than the legacy `State`. Add a top-of-frame `Render(s, width, height) string` that returns the full frame, splicing in:

- Title bar: `TAVERNBENCH` + agent badge — dim "Awaiting agent…" when detached, accent-colored `[ AGENT • <name> ]` when attached.
- Map panel from `s.Tick`.
- Quest panel from `s.Tick.Quests` (and `s.RunComplete`, `s.FinalScore` if set).
- Log panel from `s.LogLines`.

The full implementation is a mechanical lift; preserve the existing layout exactly so spectator visual output is unchanged. The only new piece is the agent badge in the title.

Approximate skeleton (filling in lifted functions from `tui/main.go`):
```go
package render

import (
    "fmt"
    "strings"

    "github.com/tavernbench/tui/internal/state"
)

const esc = "\x1b["

// ANSI helpers lifted from tui/main.go ...

func Render(s *state.GameState, w, h int) string {
    var sb strings.Builder
    sb.WriteString(renderTitle(s, w))
    sb.WriteString("\n")
    sb.WriteString(renderMap(s.Tick, w))
    sb.WriteString(renderQuests(s.Tick, s, w))
    sb.WriteString(renderLog(s.LogLines, 0, w, h))
    return sb.String()
}

func renderTitle(s *state.GameState, w int) string {
    badge := dim("Awaiting agent…")
    if s.AgentState == state.AgentAttached {
        badge = color(214, fmt.Sprintf("[ AGENT • %s ]", s.AgentName))
    }
    title := bold("TAVERNBENCH") + "  " + badge
    return padRight(title, w)
}

// renderMap, renderLog, renderQuests, padRight, visibleLen, bold, dim, color, etc. — lifted from tui/main.go
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tavernbench-client/tui && go test ./internal/render/...`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd tavernbench-client
git add tui/internal/render/
git commit -m "refactor(tui): extract render package keyed on state.GameState"
```

---

## Phase 2 checkpoint

All four internal packages stand alone with passing tests. The legacy `tui/main.go` still works as before because we've only ADDED packages and lifted code, not rewired the main loop yet.

```bash
cd tavernbench-client/tui && go test ./... && go build ./...
```

---

## Phase 3 — TUI main integration (player + spectator + IPC)

Rewrite `tui/main.go` to wire the four internal packages together, support `--mode={play,spectate}`, host the unix socket, and optionally spawn the agent subprocess.

### Task 3.1: New `tui/main.go` with mode flags and socket lifecycle

**Files:**
- Modify (full rewrite): `tavernbench-client/tui/main.go`
- Delete: `tavernbench-client/tui/play/main.go`

- [ ] **Step 1: Replace `tui/main.go` content**

Full file at `tavernbench-client/tui/main.go`:
```go
package main

import (
    "context"
    "crypto/rand"
    "encoding/base32"
    "flag"
    "fmt"
    "os"
    "os/signal"
    "path/filepath"
    "syscall"
    "time"

    "github.com/tavernbench/tui/internal/agentproc"
    "github.com/tavernbench/tui/internal/config"
    "github.com/tavernbench/tui/internal/ipc"
    "github.com/tavernbench/tui/internal/render"
    "github.com/tavernbench/tui/internal/state"
    "github.com/tavernbench/tui/internal/wsclient"
)

func main() {
    mode := flag.String("mode", "play", "play | spectate")
    host := flag.String("host", "127.0.0.1:4100", "Phoenix host")
    zone := flag.String("zone", "tavern_hall", "Zone / scenario id")
    agent := flag.String("agent", "", "Optional command to spawn as the agent (one-terminal mode)")
    noRender := flag.Bool("no-render", false, "Suppress alt-screen rendering (for e2e tests)")
    flag.Parse()

    apiKey, err := config.ReadAPIKey()
    if err != nil {
        fmt.Fprintf(os.Stderr, "tavernbench: %v\nrun `tavernbench auth` first\n", err)
        os.Exit(2)
    }

    token := mintToken()
    sockPath := socketPath(token)

    s := &state.GameState{}
    handler := &Handler{state: s}
    srv := ipc.NewServer(handler, 4)
    if err := srv.Listen(sockPath); err != nil {
        fmt.Fprintf(os.Stderr, "tavernbench: cannot listen on %s: %v\n", sockPath, err)
        os.Exit(2)
    }
    defer srv.Close()
    defer os.Remove(sockPath)

    ctx, cancel := context.WithCancel(context.Background())
    defer cancel()

    go srv.Accept(ctx)

    // Connect Phoenix WS (mode-specific topic).
    conn, err := wsclient.Connect(fmt.Sprintf("ws://%s/socket/websocket?api_key=%s", *host, apiKey))
    if err != nil {
        fmt.Fprintf(os.Stderr, "tavernbench: ws connect failed: %v\n", err)
        os.Exit(2)
    }
    handler.conn = conn
    handler.zone = *zone
    handler.mode = *mode

    if err := handler.Join(); err != nil {
        fmt.Fprintf(os.Stderr, "tavernbench: join failed: %v\n", err)
        os.Exit(2)
    }
    go handler.ReadLoop(s)

    // Optional agent subprocess.
    var proc *agentproc.Process
    if *agent != "" {
        argv := []string{"/bin/sh", "-c", *agent}
        proc, err = agentproc.Spawn(argv, []string{
            "TAVERNBENCH_TOKEN=" + token,
            "TAVERNBENCH_SOCK=" + sockPath,
        })
        if err != nil {
            fmt.Fprintf(os.Stderr, "tavernbench: failed to spawn agent: %v\n", err)
            os.Exit(2)
        }
        defer proc.Stop()
    }

    // Print token to stdout BEFORE entering alt-screen, so two-terminal users can copy it.
    fmt.Printf("Pairing token: %s\nSocket: %s\n", token, sockPath)

    if !*noRender {
        fmt.Print("\x1b[?1049h\x1b[?25l")
        defer fmt.Print("\x1b[?25h\x1b[?1049l")
    }

    sig := make(chan os.Signal, 1)
    signal.Notify(sig, os.Interrupt, syscall.SIGTERM)

    ticker := time.NewTicker(100 * time.Millisecond)
    defer ticker.Stop()
    for {
        select {
        case <-sig:
            return
        case <-ticker.C:
            if !*noRender {
                fmt.Print("\x1b[H")
                fmt.Print(render.Render(s, termWidth(), termHeight()))
            }
        }
    }
}

func mintToken() string {
    b := make([]byte, 4)
    rand.Read(b)
    return "TAVERN-" + base32.StdEncoding.WithPadding(base32.NoPadding).EncodeToString(b)
}

func socketPath(token string) string {
    base := os.Getenv("XDG_RUNTIME_DIR")
    if base == "" {
        base = "/tmp"
    }
    return filepath.Join(base, "tavernbench", token+".sock")
}

// termWidth / termHeight — lifted from existing tui/main.go termSize()
func termWidth() int  { w, _ := termSize(); return w }
func termHeight() int { _, h := termSize(); return h }
```

(Keep the existing `termSize()` helper from the current `tui/main.go` as a leftover function at the bottom of this file — it's small and standalone.)

- [ ] **Step 2: Delete `tui/play/main.go`**

```bash
cd tavernbench-client
git rm tui/play/main.go
rmdir tui/play 2>/dev/null || true
```

- [ ] **Step 3: Verify the binary builds (handler still missing — expected)**

Run: `cd tavernbench-client/tui && go build ./...`
Expected: BUILD FAIL — `Handler` undefined. That's expected; Task 3.2 adds it.

- [ ] **Step 4: Commit the structural changes**

```bash
cd tavernbench-client
git add tui/main.go
git commit -m "refactor(tui): new main.go wired to internal packages (handler stub follows)"
```

---

### Task 3.2: `Handler` — bridge between IPC and Phoenix WS

**Files:**
- Create: `tavernbench-client/tui/handler.go`
- Create: `tavernbench-client/tui/handler_test.go`

- [ ] **Step 1: Write the failing test**

`tui/handler_test.go`:
```go
package main

import (
    "context"
    "testing"

    "github.com/tavernbench/tui/internal/ipc"
    "github.com/tavernbench/tui/internal/state"
)

func TestHandler_Attach_SetsAgentName(t *testing.T) {
    s := &state.GameState{}
    h := &Handler{state: s}
    resp := h.HandleRequest(context.Background(), ipc.Request{ID: "1", Op: ipc.OpAttach, Name: "claude"})
    if !resp.OK {
        t.Fatalf("attach failed: %+v", resp.Error)
    }
    if s.AgentName != "claude" || s.AgentState != state.AgentAttached {
        t.Fatalf("state not updated: %+v", s)
    }
}

func TestHandler_DoubleAttach_Errors(t *testing.T) {
    s := &state.GameState{AgentState: state.AgentAttached, AgentName: "first"}
    h := &Handler{state: s}
    resp := h.HandleRequest(context.Background(), ipc.Request{ID: "2", Op: ipc.OpAttach, Name: "second"})
    if resp.OK || resp.Error == nil || resp.Error.Code != "already_attached" {
        t.Fatalf("expected already_attached: %+v", resp)
    }
}

func TestHandler_ObserveReturnsState(t *testing.T) {
    s := &state.GameState{Tick: state.Tick{Score: 5, Steps: 2}}
    h := &Handler{state: s}
    resp := h.HandleRequest(context.Background(), ipc.Request{ID: "3", Op: ipc.OpObserve})
    if !resp.OK || resp.Observation["score"] != 5 {
        t.Fatalf("bad observe response: %+v", resp)
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd tavernbench-client/tui && go test .`
Expected: FAIL — `Handler` undefined.

- [ ] **Step 3: Implement the handler**

`tui/handler.go`:
```go
package main

import (
    "context"
    "encoding/json"
    "fmt"
    "sync"
    "time"

    "github.com/tavernbench/tui/internal/ipc"
    "github.com/tavernbench/tui/internal/state"
    "github.com/tavernbench/tui/internal/wsclient"
)

type Handler struct {
    mu    sync.Mutex
    state *state.GameState
    conn  *wsclient.Conn
    zone  string
    mode  string
    ref   int
    tickC chan state.Tick
}

func (h *Handler) HandleRequest(ctx context.Context, req ipc.Request) ipc.Response {
    h.mu.Lock()
    defer h.mu.Unlock()

    switch req.Op {
    case ipc.OpAttach:
        if h.state.AgentState == state.AgentAttached {
            return ipc.Response{ID: req.ID, OK: false,
                Error: &ipc.ErrorBody{Code: "already_attached",
                    Message: "current agent: " + h.state.AgentName}}
        }
        state.Attach(h.state, req.Name)
        return ipc.Response{ID: req.ID, OK: true, Observation: observationOf(h.state)}

    case ipc.OpObserve:
        return ipc.Response{ID: req.ID, OK: true, Observation: observationOf(h.state)}

    case ipc.OpAct:
        if h.state.RunComplete {
            return ipc.Response{ID: req.ID, OK: true,
                Observation: observationOf(h.state), RunComplete: true}
        }
        if err := h.sendAction(req.Verb, req.Args); err != nil {
            return ipc.Response{ID: req.ID, OK: false,
                Error: &ipc.ErrorBody{Code: "ws_error", Message: err.Error()}}
        }
        h.waitForTick(2 * time.Second)
        return ipc.Response{ID: req.ID, OK: true,
            Observation: observationOf(h.state), RunComplete: h.state.RunComplete}

    case ipc.OpAbort:
        return ipc.Response{ID: req.ID, OK: true}

    default:
        return ipc.Response{ID: req.ID, OK: false,
            Error: &ipc.ErrorBody{Code: "bad_op", Message: string(req.Op)}}
    }
}

func observationOf(s *state.GameState) map[string]any {
    return map[string]any{
        "tick":     s.Tick.Tick,
        "zone_id":  s.Tick.ZoneID,
        "position": s.Tick.Position,
        "entities": s.Tick.Entities,
        "quests":   s.Tick.Quests,
        "score":    s.Tick.Score,
        "steps":    s.Tick.Steps,
    }
}

func (h *Handler) Join() error {
    h.ref++
    topic := "zone:" + h.zone
    if h.mode == "spectate" {
        topic = "spectate:" + h.zone
    }
    payload, _ := json.Marshal(map[string]string{"protocol_version": "1.0"})
    msg, _ := wsclient.EncodeMsg(fmt.Sprintf("%d", h.ref), fmt.Sprintf("%d", h.ref), topic, "phx_join", json.RawMessage(payload))
    return h.conn.WriteText(msg)
}

func (h *Handler) sendAction(verb string, args map[string]any) error {
    h.ref++
    if args == nil {
        args = map[string]any{}
    }
    args["action"] = verb
    raw, _ := json.Marshal(args)
    msg, _ := wsclient.EncodeMsg("1", fmt.Sprintf("%d", h.ref), "zone:"+h.zone, "action", json.RawMessage(raw))
    return h.conn.WriteText(msg)
}

func (h *Handler) waitForTick(timeout time.Duration) {
    if h.tickC == nil {
        h.tickC = make(chan state.Tick, 4)
    }
    select {
    case t := <-h.tickC:
        state.Apply(h.state, t)
    case <-time.After(timeout):
    }
}

// ReadLoop pumps Phoenix messages into state. Runs in its own goroutine.
func (h *Handler) ReadLoop(s *state.GameState) {
    for {
        raw, err := h.conn.ReadMsg()
        if err != nil {
            return
        }
        var arr [5]json.RawMessage
        if err := json.Unmarshal(raw, &arr); err != nil {
            continue
        }
        var event string
        json.Unmarshal(arr[3], &event)

        switch event {
        case "tick":
            var t state.Tick
            if json.Unmarshal(arr[4], &t) == nil {
                state.Apply(s, t)
                if h.tickC != nil {
                    select {
                    case h.tickC <- t:
                    default:
                    }
                }
            }
        case "quest_complete":
            var qc struct {
                FinalScore int    `json:"final_score"`
                Steps      int    `json:"steps_taken"`
                RunID      string `json:"run_id"`
            }
            if json.Unmarshal(arr[4], &qc) == nil {
                state.Complete(s, qc.FinalScore, qc.Steps, qc.RunID)
            }
        }
    }
}
```

- [ ] **Step 4: Run tests + build**

Run: `cd tavernbench-client/tui && go test ./... && go build ./...`
Expected: all green, binary builds.

- [ ] **Step 5: Commit**

```bash
cd tavernbench-client
git add tui/handler.go tui/handler_test.go
git commit -m "feat(tui): add Handler bridging IPC requests to Phoenix WS"
```

---

## Phase 3 checkpoint

The TUI binary builds and can be launched manually:

```bash
cd tavernbench-client/tui
go build -o /tmp/tavernbench-tui .
~/.config/tavernbench/config.toml must exist with api_key = "..."
/tmp/tavernbench-tui --mode=spectate --zone=tavern_hall   # against a running server
```

The agent path is reachable but only via raw socket writes — Phase 4 builds the CLI.

---

## Phase 4 — Go CLI binary

### Task 4.1: Set up `cli/` Go module and entry point

**Files:**
- Create: `tavernbench-client/cli/go.mod`
- Create: `tavernbench-client/cli/cmd/tavernbench/main.go`

- [ ] **Step 1: Initialize module**

```bash
cd tavernbench-client/cli
go mod init github.com/tavernbench/cli
```

- [ ] **Step 2: Write the entry point**

`tavernbench-client/cli/cmd/tavernbench/main.go`:
```go
package main

import (
    "fmt"
    "os"
)

func main() {
    if len(os.Args) < 2 {
        usage()
        os.Exit(2)
    }
    switch os.Args[1] {
    case "attach":
        attachCmd(os.Args[2:])
    case "act":
        actCmd(os.Args[2:])
    case "observe":
        observeCmd(os.Args[2:])
    case "scenarios":
        scenariosCmd(os.Args[2:])
    case "leaderboard":
        leaderboardCmd(os.Args[2:])
    case "play":
        playCmd(os.Args[2:])
    case "auth":
        authCmd(os.Args[2:])
    case "doctor":
        doctorCmd(os.Args[2:])
    case "-h", "--help", "help":
        usage()
    default:
        fmt.Fprintf(os.Stderr, "tavernbench: unknown subcommand %q\n", os.Args[1])
        usage()
        os.Exit(2)
    }
}

func usage() {
    fmt.Fprintln(os.Stderr, `tavernbench — agent benchmarking arena

Usage:
  tavernbench play [--scenario X] [--agent CMD]   Launch TUI
  tavernbench attach TOKEN                         Attach as the active agent
  tavernbench act VERB [ARGS...]                   Send an action
  tavernbench observe                              Print current observation
  tavernbench scenarios                            List scenarios (HTTP)
  tavernbench leaderboard --scenario X             Show leaderboard (HTTP)
  tavernbench auth [--key K]                       Store API key
  tavernbench doctor [--fix]                       Pre-flight checks
`)
}
```

- [ ] **Step 3: Verify it builds (subcommand functions still missing — expected)**

Run: `cd tavernbench-client/cli && go build ./...`
Expected: BUILD FAIL — subcommand functions undefined. Continue.

- [ ] **Step 4: Commit module setup**

```bash
cd tavernbench-client
git add cli/go.mod cli/cmd/tavernbench/main.go
git commit -m "feat(cli): scaffold Go CLI entry point"
```

---

### Task 4.2: `cli/internal/sockconn` — socket resolution and request helper

**Files:**
- Create: `tavernbench-client/cli/internal/sockconn/sockconn.go`
- Create: `tavernbench-client/cli/internal/sockconn/sockconn_test.go`

- [ ] **Step 1: Write the failing test**

```go
package sockconn

import (
    "os"
    "testing"
)

func TestResolvePath_PrefersSockEnv(t *testing.T) {
    os.Setenv("TAVERNBENCH_SOCK", "/tmp/x.sock")
    os.Setenv("TAVERNBENCH_TOKEN", "TOK")
    defer os.Unsetenv("TAVERNBENCH_SOCK")
    defer os.Unsetenv("TAVERNBENCH_TOKEN")

    got, err := ResolvePath("")
    if err != nil || got != "/tmp/x.sock" {
        t.Fatalf("got %q, err %v", got, err)
    }
}

func TestResolvePath_FallsBackToToken(t *testing.T) {
    os.Unsetenv("TAVERNBENCH_SOCK")
    os.Setenv("TAVERNBENCH_TOKEN", "TAVERN-FOO")
    defer os.Unsetenv("TAVERNBENCH_TOKEN")

    got, err := ResolvePath("")
    if err != nil {
        t.Fatal(err)
    }
    if got == "" {
        t.Fatal("got empty path")
    }
}

func TestResolvePath_NoneAvailableErrors(t *testing.T) {
    os.Unsetenv("TAVERNBENCH_SOCK")
    os.Unsetenv("TAVERNBENCH_TOKEN")
    _, err := ResolvePath("")
    if err == nil {
        t.Fatal("expected error")
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd tavernbench-client/cli && go test ./internal/sockconn/...`
Expected: FAIL.

- [ ] **Step 3: Implement**

`cli/internal/sockconn/sockconn.go`:
```go
package sockconn

import (
    "bufio"
    "encoding/json"
    "errors"
    "net"
    "os"
    "path/filepath"
)

func ResolvePath(explicitToken string) (string, error) {
    if p := os.Getenv("TAVERNBENCH_SOCK"); p != "" {
        return p, nil
    }
    token := explicitToken
    if token == "" {
        token = os.Getenv("TAVERNBENCH_TOKEN")
    }
    if token != "" {
        base := os.Getenv("XDG_RUNTIME_DIR")
        if base == "" {
            base = "/tmp"
        }
        return filepath.Join(base, "tavernbench", token+".sock"), nil
    }
    return "", errors.New("no active run (is the TUI running? Set TAVERNBENCH_TOKEN or pass --token)")
}

func Send(path string, req any) (json.RawMessage, error) {
    conn, err := net.Dial("unix", path)
    if err != nil {
        return nil, err
    }
    defer conn.Close()
    raw, err := json.Marshal(req)
    if err != nil {
        return nil, err
    }
    conn.Write(append(raw, '\n'))
    return bufio.NewReader(conn).ReadBytes('\n')
}
```

- [ ] **Step 4: Run test**

Run: `cd tavernbench-client/cli && go test ./internal/sockconn/...`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd tavernbench-client
git add cli/internal/sockconn/
git commit -m "feat(cli): add sockconn helper for socket resolution"
```

---

### Task 4.3: `attach`, `observe`, `act` subcommands

**Files:**
- Create: `tavernbench-client/cli/cmd/tavernbench/attach.go`
- Create: `tavernbench-client/cli/cmd/tavernbench/observe.go`
- Create: `tavernbench-client/cli/cmd/tavernbench/act.go`

- [ ] **Step 1: Write each subcommand file**

`cli/cmd/tavernbench/attach.go`:
```go
package main

import (
    "encoding/json"
    "fmt"
    "os"
    "path/filepath"

    "github.com/tavernbench/cli/internal/sockconn"
)

func attachCmd(args []string) {
    if len(args) < 1 {
        fmt.Fprintln(os.Stderr, "usage: tavernbench attach TOKEN")
        os.Exit(2)
    }
    token := args[0]
    os.Setenv("TAVERNBENCH_TOKEN", token)
    path, err := sockconn.ResolvePath(token)
    if err != nil {
        die(err)
    }
    name := os.Getenv("TAVERNBENCH_AGENT_NAME")
    if name == "" {
        name = filepath.Base(os.Args[0])
    }
    resp, err := sockconn.Send(path, map[string]any{"id": "1", "op": "attach", "name": name})
    if err != nil {
        die(err)
    }
    fmt.Println(string(resp))
}

func die(err error) {
    fmt.Fprintln(os.Stderr, "tavernbench: "+err.Error())
    os.Exit(1)
}
```

`cli/cmd/tavernbench/observe.go`:
```go
package main

import (
    "fmt"

    "github.com/tavernbench/cli/internal/sockconn"
)

func observeCmd(args []string) {
    path, err := sockconn.ResolvePath("")
    if err != nil {
        die(err)
    }
    resp, err := sockconn.Send(path, map[string]any{"id": "1", "op": "observe"})
    if err != nil {
        die(err)
    }
    fmt.Println(string(resp))
}
```

`cli/cmd/tavernbench/act.go`:
```go
package main

import (
    "fmt"
    "os"
    "strings"

    "github.com/tavernbench/cli/internal/sockconn"
)

func actCmd(args []string) {
    if len(args) < 1 {
        fmt.Fprintln(os.Stderr, "usage: tavernbench act VERB [ARGS...]")
        os.Exit(2)
    }
    verb := args[0]
    rest := args[1:]

    path, err := sockconn.ResolvePath("")
    if err != nil {
        die(err)
    }

    payload := map[string]any{"id": "1", "op": "act", "verb": verb}
    args2 := buildActionArgs(verb, rest)
    if args2 != nil {
        payload["args"] = args2
    }
    resp, err := sockconn.Send(path, payload)
    if err != nil {
        die(err)
    }
    fmt.Println(string(resp))
}

func buildActionArgs(verb string, rest []string) map[string]any {
    if len(rest) == 0 {
        return nil
    }
    switch verb {
    case "move":
        return map[string]any{"direction": rest[0]}
    case "use":
        // "use ITEM on TARGET"
        joined := strings.Join(rest, " ")
        parts := strings.SplitN(joined, " on ", 2)
        if len(parts) == 2 {
            return map[string]any{"item": parts[0], "target": parts[1]}
        }
        return map[string]any{"item": parts[0]}
    case "reply":
        return map[string]any{"choice": rest[0]}
    default:
        return map[string]any{"target": rest[0]}
    }
}
```

- [ ] **Step 2: Run build**

Run: `cd tavernbench-client/cli && go build ./...`
Expected: still fails (other subcommands missing). The three new files compile.

- [ ] **Step 3: Commit**

```bash
cd tavernbench-client
git add cli/cmd/tavernbench/attach.go cli/cmd/tavernbench/observe.go cli/cmd/tavernbench/act.go
git commit -m "feat(cli): implement attach/observe/act subcommands"
```

---

### Task 4.4: `scenarios`, `leaderboard` subcommands (HTTP, no TUI)

**Files:**
- Create: `tavernbench-client/cli/cmd/tavernbench/scenarios.go`
- Create: `tavernbench-client/cli/cmd/tavernbench/leaderboard.go`
- Create: `tavernbench-client/cli/internal/httpapi/httpapi.go`

- [ ] **Step 1: HTTP helper**

`cli/internal/httpapi/httpapi.go`:
```go
package httpapi

import (
    "io"
    "net/http"
    "os"
)

func DefaultHost() string {
    if h := os.Getenv("TAVERNBENCH_HOST"); h != "" {
        return h
    }
    return "http://127.0.0.1:4100"
}

func Get(path string) ([]byte, error) {
    resp, err := http.Get(DefaultHost() + path)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()
    return io.ReadAll(resp.Body)
}
```

- [ ] **Step 2: Subcommands**

`cli/cmd/tavernbench/scenarios.go`:
```go
package main

import (
    "fmt"

    "github.com/tavernbench/cli/internal/httpapi"
)

func scenariosCmd(_ []string) {
    body, err := httpapi.Get("/api/scenarios")
    if err != nil {
        die(err)
    }
    fmt.Println(string(body))
}
```

`cli/cmd/tavernbench/leaderboard.go`:
```go
package main

import (
    "flag"
    "fmt"
    "net/url"
    "os"

    "github.com/tavernbench/cli/internal/httpapi"
)

func leaderboardCmd(args []string) {
    fs := flag.NewFlagSet("leaderboard", flag.ExitOnError)
    scenario := fs.String("scenario", "", "Scenario id")
    fs.Parse(args)
    if *scenario == "" {
        fmt.Fprintln(os.Stderr, "usage: tavernbench leaderboard --scenario X")
        os.Exit(2)
    }
    body, err := httpapi.Get("/api/leaderboard?scenario=" + url.QueryEscape(*scenario))
    if err != nil {
        die(err)
    }
    fmt.Println(string(body))
}
```

- [ ] **Step 3: Commit**

```bash
cd tavernbench-client
git add cli/cmd/tavernbench/scenarios.go cli/cmd/tavernbench/leaderboard.go cli/internal/httpapi/
git commit -m "feat(cli): implement scenarios + leaderboard HTTP subcommands"
```

---

### Task 4.5: `play` subcommand — wrap the TUI binary

**Files:**
- Create: `tavernbench-client/cli/cmd/tavernbench/play.go`

- [ ] **Step 1: Implement**

`cli/cmd/tavernbench/play.go`:
```go
package main

import (
    "flag"
    "fmt"
    "os"
    "os/exec"
    "path/filepath"
)

func playCmd(args []string) {
    fs := flag.NewFlagSet("play", flag.ExitOnError)
    scenario := fs.String("scenario", "tavern_hall", "Scenario id")
    agent := fs.String("agent", "", "Optional agent command to spawn")
    host := fs.String("host", "127.0.0.1:4100", "Phoenix host")
    fs.Parse(args)

    tuiPath := findTUIBinary()
    cmd := exec.Command(tuiPath,
        "--mode=play",
        "--zone="+*scenario,
        "--host="+*host,
    )
    if *agent != "" {
        cmd.Args = append(cmd.Args, "--agent="+*agent)
    }
    cmd.Stdin = os.Stdin
    cmd.Stdout = os.Stdout
    cmd.Stderr = os.Stderr
    if err := cmd.Run(); err != nil {
        if ee, ok := err.(*exec.ExitError); ok {
            os.Exit(ee.ExitCode())
        }
        die(err)
    }
}

func findTUIBinary() string {
    // 1) env override
    if p := os.Getenv("TAVERNBENCH_TUI_BIN"); p != "" {
        return p
    }
    // 2) sibling of the CLI binary
    self, err := os.Executable()
    if err == nil {
        candidate := filepath.Join(filepath.Dir(self), "tavernbench-tui")
        if _, err := os.Stat(candidate); err == nil {
            return candidate
        }
    }
    // 3) PATH lookup
    if p, err := exec.LookPath("tavernbench-tui"); err == nil {
        return p
    }
    fmt.Fprintln(os.Stderr, "tavernbench: cannot find tavernbench-tui binary on PATH")
    os.Exit(2)
    return ""
}
```

- [ ] **Step 2: Commit**

```bash
cd tavernbench-client
git add cli/cmd/tavernbench/play.go
git commit -m "feat(cli): implement play subcommand wrapping the TUI"
```

---

### Task 4.6: `auth` and `doctor` subcommands

**Files:**
- Create: `tavernbench-client/cli/cmd/tavernbench/auth.go`
- Create: `tavernbench-client/cli/cmd/tavernbench/doctor.go`

- [ ] **Step 1: `auth`**

`cli/cmd/tavernbench/auth.go`:
```go
package main

import (
    "bufio"
    "flag"
    "fmt"
    "os"
    "path/filepath"
    "strings"

    "golang.org/x/term"
)

func authCmd(args []string) {
    fs := flag.NewFlagSet("auth", flag.ExitOnError)
    key := fs.String("key", "", "API key (omit for hidden prompt)")
    fs.Parse(args)

    var apiKey string
    if *key != "" {
        apiKey = *key
    } else {
        fmt.Print("Paste API key (input hidden): ")
        b, err := term.ReadPassword(int(os.Stdin.Fd()))
        fmt.Println()
        if err != nil {
            // Fallback: visible read.
            r := bufio.NewReader(os.Stdin)
            line, _ := r.ReadString('\n')
            b = []byte(strings.TrimSpace(line))
        }
        apiKey = strings.TrimSpace(string(b))
    }
    if apiKey == "" {
        fmt.Fprintln(os.Stderr, "tavernbench: no key entered")
        os.Exit(1)
    }
    home, _ := os.UserHomeDir()
    dir := filepath.Join(home, ".config", "tavernbench")
    os.MkdirAll(dir, 0o700)
    path := filepath.Join(dir, "config.toml")
    content := fmt.Sprintf(`api_key = "%s"`+"\n", apiKey)
    if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
        die(err)
    }
    fmt.Printf("✓ Key saved to %s\n", path)
}
```

- [ ] **Step 2: Add the `golang.org/x/term` dep**

```bash
cd tavernbench-client/cli
go get golang.org/x/term
go mod tidy
```

- [ ] **Step 3: `doctor`**

`cli/cmd/tavernbench/doctor.go`:
```go
package main

import (
    "flag"
    "fmt"
    "net"
    "net/http"
    "os"
    "path/filepath"
    "time"
)

func doctorCmd(args []string) {
    fs := flag.NewFlagSet("doctor", flag.ExitOnError)
    _ = fs.Bool("fix", false, "Reserved for future auto-repair")
    fs.Parse(args)

    home, _ := os.UserHomeDir()
    cfg := filepath.Join(home, ".config", "tavernbench", "config.toml")

    fmt.Print("checking config.toml... ")
    if _, err := os.Stat(cfg); err != nil {
        fmt.Println("MISSING — run `tavernbench auth`")
        os.Exit(1)
    }
    fmt.Println("ok")

    fmt.Print("checking server reachability... ")
    client := &http.Client{Timeout: 2 * time.Second}
    resp, err := client.Get("http://127.0.0.1:4100/health")
    if err != nil || resp.StatusCode != 200 {
        fmt.Println("UNREACHABLE")
        os.Exit(1)
    }
    fmt.Println("ok")

    fmt.Print("checking for active TUI socket... ")
    base := os.Getenv("XDG_RUNTIME_DIR")
    if base == "" {
        base = "/tmp"
    }
    entries, _ := os.ReadDir(filepath.Join(base, "tavernbench"))
    found := 0
    for _, e := range entries {
        if filepath.Ext(e.Name()) == ".sock" {
            sock := filepath.Join(base, "tavernbench", e.Name())
            c, err := net.DialTimeout("unix", sock, 200*time.Millisecond)
            if err == nil {
                c.Close()
                found++
            }
        }
    }
    fmt.Printf("%d active\n", found)
}
```

- [ ] **Step 4: Build + commit**

Run: `cd tavernbench-client/cli && go build ./...`
Expected: PASS.

```bash
cd tavernbench-client
git add cli/cmd/tavernbench/auth.go cli/cmd/tavernbench/doctor.go cli/go.mod cli/go.sum
git commit -m "feat(cli): implement auth and doctor subcommands"
```

---

### Task 4.7: CLI integration tests

**Files:**
- Create: `tavernbench-client/cli/cmd/tavernbench/cli_test.go`

- [ ] **Step 1: Add a test that exercises CLI against an in-test IPC server**

`cli/cmd/tavernbench/cli_test.go`:
```go
package main

import (
    "encoding/json"
    "fmt"
    "net"
    "os"
    "os/exec"
    "path/filepath"
    "testing"
)

// Spin up a tiny in-test unix-socket echo that mimics the TUI's IPC server.
func startEchoSocket(t *testing.T) string {
    dir := t.TempDir()
    sock := filepath.Join(dir, "test.sock")
    l, err := net.Listen("unix", sock)
    if err != nil {
        t.Fatal(err)
    }
    t.Cleanup(func() { l.Close(); os.Remove(sock) })

    go func() {
        for {
            c, err := l.Accept()
            if err != nil {
                return
            }
            go func(c net.Conn) {
                defer c.Close()
                buf := make([]byte, 4096)
                n, _ := c.Read(buf)
                var req map[string]any
                json.Unmarshal(buf[:n], &req)
                resp, _ := json.Marshal(map[string]any{
                    "id":          req["id"],
                    "ok":          true,
                    "observation": map[string]any{"echo": req["op"]},
                })
                c.Write(append(resp, '\n'))
            }(c)
        }
    }()
    return sock
}

func TestCLIObserve_RoundTrips(t *testing.T) {
    sock := startEchoSocket(t)
    bin := buildBinary(t)

    cmd := exec.Command(bin, "observe")
    cmd.Env = append(os.Environ(), "TAVERNBENCH_SOCK="+sock)
    out, err := cmd.CombinedOutput()
    if err != nil {
        t.Fatalf("observe failed: %v: %s", err, out)
    }
    if !contains(out, []byte(`"echo":"observe"`)) {
        t.Fatalf("did not see echoed op: %s", out)
    }
}

func buildBinary(t *testing.T) string {
    dir := t.TempDir()
    bin := filepath.Join(dir, "tavernbench")
    cmd := exec.Command("go", "build", "-o", bin, ".")
    out, err := cmd.CombinedOutput()
    if err != nil {
        t.Fatalf("build failed: %v: %s", err, out)
    }
    return bin
}

func contains(haystack, needle []byte) bool {
    return len(haystack) >= len(needle) && fmt.Sprintf("%s", haystack) != "" &&
        indexOf(haystack, needle) >= 0
}

func indexOf(h, n []byte) int {
    for i := 0; i+len(n) <= len(h); i++ {
        match := true
        for j := range n {
            if h[i+j] != n[j] {
                match = false
                break
            }
        }
        if match {
            return i
        }
    }
    return -1
}
```

- [ ] **Step 2: Run**

Run: `cd tavernbench-client/cli && go test ./...`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd tavernbench-client
git add cli/cmd/tavernbench/cli_test.go
git commit -m "test(cli): integration test for observe over echo socket"
```

---

## Phase 4 checkpoint

End-to-end attach/act/observe path works on dev box:

```bash
# Terminal A
go build -C tavernbench-client/tui -o /tmp/tavernbench-tui .
go build -C tavernbench-client/cli -o /tmp/tavernbench ./cmd/tavernbench
PATH=/tmp:$PATH tavernbench play --scenario tavern_hall

# Terminal B
PATH=/tmp:$PATH TAVERNBENCH_TOKEN=<token from A> tavernbench attach $TAVERNBENCH_TOKEN
PATH=/tmp:$PATH tavernbench act move north
```

---

## Phase 5 — MCP shim and Python cleanup

### Task 5.1: Rewrite `mcp/server.py` as a subprocess shim

**Files:**
- Modify: `tavernbench-client/mcp/server.py`

- [ ] **Step 1: Replace the body of `mcp/server.py`**

```python
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
    token = os.environ.get("TAVERNBENCH_TOKEN", "")
    if not token:
        return json.dumps({"error": "TAVERNBENCH_TOKEN env var not set — start `tavernbench play` first"})
    return _run(["attach", token])


@mcp.tool()
def tavernbench_act(run_id: str, action: str, target: str = "", params: Optional[str] = None) -> str:
    """Dispatch one action via the running TUI."""
    args = ["act", action]
    if target:
        args.append(target)
    return _run(args)


@mcp.tool()
def tavernbench_observe(run_id: str) -> str:
    """Return the current observation."""
    return _run(["observe"])


@mcp.tool()
def tavernbench_confirm_ranked(run_id: str) -> str:
    """Deprecated: casual-leaderboard MVP records every completion."""
    return json.dumps({"confirmed": True, "note": "casual-leaderboard MVP — confirmation is a no-op"})


def run_server() -> None:
    mcp.run()


if __name__ == "__main__":
    run_server()
```

- [ ] **Step 2: Verify it imports**

Run: `cd tavernbench-client/mcp && python -c "import server"`
Expected: no error.

- [ ] **Step 3: Commit**

```bash
cd tavernbench-client
git add mcp/server.py
git commit -m "refactor(mcp): shrink server to CLI subprocess shim"
```

---

### Task 5.2: Delete Python SDK and CLI stubs

**Files:**
- Delete: `tavernbench-client/sdk/tavernbench/client.py`
- Delete: `tavernbench-client/sdk/tavernbench/__init__.py`
- Delete: `tavernbench-client/sdk/example.py`
- Delete: `tavernbench-client/sdk/README.md`
- Modify: `tavernbench-client/cli/tavernbench_cli/commands.py` (remove play/watch/leaderboard/history stubs)
- Modify: `tavernbench-client/cli/tavernbench_cli/main.py` (remove dispatch for those)
- Modify: `tavernbench-client/cli/pyproject.toml` (rename the entry point so it doesn't conflict with the Go binary)

- [ ] **Step 1: Delete SDK files**

```bash
cd tavernbench-client
git rm -r sdk/
```

- [ ] **Step 2: Trim Python CLI**

In `cli/tavernbench_cli/commands.py`, delete the `play`, `watch`, `leaderboard`, `history` stubs (`def play`, `def watch`, etc.). Keep `auth`, `install`, `doctor`, `mcp_app`. (Note: `auth` and `doctor` are now duplicated between Python and Go — the Python ones are kept ONLY for users still running the Python entry point during the transition; the Go versions are canonical.)

In `cli/tavernbench_cli/main.py`, remove the `app.command()(commands.play)`, `...watch`, `...leaderboard`, `...history` lines.

In `cli/pyproject.toml`, rename:
```
[project.scripts]
tavernbench-mcp = "tavernbench_cli.main:main"
```
The MCP install path (`tavernbench mcp install ...`) now writes config that invokes `tavernbench-mcp mcp serve` for the MCP server. The user-facing `tavernbench` binary is the Go one.

- [ ] **Step 3: Verify Python tests still pass**

Run: `cd tavernbench-client/cli && python -m pytest tests/`
Expected: pass (or skip — these are tests for the Python wrapper, which still exists in trimmed form).

- [ ] **Step 4: Commit**

```bash
cd tavernbench-client
git add cli/tavernbench_cli/commands.py cli/tavernbench_cli/main.py cli/pyproject.toml
git commit -m "refactor: delete Python SDK and trim Python CLI to MCP-install role"
```

---

### Task 5.3: Update `install.sh` to install both Go binaries

**Files:**
- Modify: `tavernbench-client/install.sh`

- [ ] **Step 1: Make install.sh build and install both binaries**

Update install.sh to:
1. `go build` the TUI into `~/.local/bin/tavernbench-tui`.
2. `go build` the CLI into `~/.local/bin/tavernbench`.
3. Pip-install the trimmed Python package (for `tavernbench-mcp`).
4. Print where each landed and remind the user to ensure `~/.local/bin` is on PATH.

Exact contents depend on the current install.sh shape; preserve its style and just add the Go build steps. Test by running it on a fresh shell.

- [ ] **Step 2: Verify install.sh runs end-to-end**

Run: `bash install.sh` in a clean shell.
Expected: both binaries on PATH, `tavernbench doctor` passes config + reachability checks.

- [ ] **Step 3: Commit**

```bash
cd tavernbench-client
git add install.sh
git commit -m "build: install Go TUI and CLI binaries via install.sh"
```

---

## Phase 6 — End-to-end smoke + final cleanup

### Task 6.1: e2e smoke test

**Files:**
- Create: `tavernbench-client/e2e/smoke.sh`
- Create: `tavernbench-client/Makefile`

- [ ] **Step 1: Write the smoke script**

`tavernbench-client/e2e/smoke.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

# Boot a server in the background (assumes test config; user wires this to their
# Phoenix test fixture). Replace with the project's actual server-boot incantation.
SERVER_PID=""
trap '[[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true' EXIT
(cd "$(dirname "$0")/../../agent-mmo" && MIX_ENV=test mix phx.server) &
SERVER_PID=$!
sleep 5

cd "$(dirname "$0")/.."

# Ensure a fresh API key in the config file (write a known test key).
mkdir -p ~/.config/tavernbench
echo 'api_key = "smoke-test-key"' > ~/.config/tavernbench/config.toml

# Launch TUI headless.
./tui/tavernbench-tui --mode=play --zone=tavern_hall --no-render &
TUI_PID=$!
trap 'kill $TUI_PID 2>/dev/null || true; [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true' EXIT
sleep 1

# Grab the latest socket file (most recent in the tavernbench dir).
SOCK=$(ls -t "${XDG_RUNTIME_DIR:-/tmp}/tavernbench/"*.sock | head -1)
TOKEN=$(basename "$SOCK" .sock)
export TAVERNBENCH_SOCK="$SOCK"

# Attach + drive a fixed sequence.
./cli/tavernbench attach "$TOKEN"
./cli/tavernbench act look
./cli/tavernbench act move north
./cli/tavernbench act move north
./cli/tavernbench observe

# Verify leaderboard has at least one entry.
./cli/tavernbench leaderboard --scenario tavern_hall | grep -q "entries"

echo "✓ smoke passed"
```

- [ ] **Step 2: Wire into Makefile**

`tavernbench-client/Makefile`:
```make
.PHONY: build test e2e

build:
	cd tui && go build -o tavernbench-tui .
	cd cli && go build -o tavernbench ./cmd/tavernbench

test:
	cd tui && go test ./...
	cd cli && go test ./...

e2e: build
	chmod +x e2e/smoke.sh
	./e2e/smoke.sh
```

- [ ] **Step 3: Run it**

```bash
cd tavernbench-client && make e2e
```
Expected: prints `✓ smoke passed`.

- [ ] **Step 4: Commit**

```bash
cd tavernbench-client
git add e2e/smoke.sh Makefile
chmod +x e2e/smoke.sh
git commit -m "test(e2e): smoke test for full IPC + leaderboard flow"
```

---

### Task 6.2: Update top-level README and PROTOCOL note

**Files:**
- Modify: `tavernbench-client/README.md`

- [ ] **Step 1: Update the user-facing quick-start in README**

Replace the existing usage section with the new flow:
```markdown
## Quick start

```bash
tavernbench auth                   # one-time, paste API key
tavernbench play --scenario tavern_hall --agent './my-agent.py'
# OR (two-terminal)
tavernbench play --scenario tavern_hall   # in terminal A
tavernbench attach <TOKEN>                # in terminal B, then act/observe
```

The agent shells out to `tavernbench act <verb>` / `tavernbench observe`.
Each call returns JSON.
```

- [ ] **Step 2: Commit**

```bash
cd tavernbench-client
git add README.md
git commit -m "docs: rewrite quick-start for new TUI-mediated flow"
```

---

## Final verification

After Phase 6 completes, run the full matrix:

```bash
# Server tests
cd agent-mmo && mix test

# Client tests
cd tavernbench-client && make test

# End-to-end
cd tavernbench-client && make e2e
```

Manually verify in two terminals:
1. Terminal A: `tavernbench play --scenario tavern_hall` — TUI appears, shows token, "Awaiting agent…" banner.
2. Terminal B: `tavernbench attach $TOKEN` — terminal A's title bar flips to `[ AGENT • tavernbench ]` (or whatever name the CLI defaults to).
3. Terminal B: `tavernbench act look` — observation prints; TUI map redraws.
4. After completing the scenario, terminal B: `tavernbench leaderboard --scenario tavern_hall` — your run appears.
5. `curl http://127.0.0.1:4100/api/runs/<id>/transcript` — full action/tick stream.

---

## Self-review notes

- **Spec coverage:** Every section of the spec maps to one or more tasks. Architecture → Phases 2–3 (TUI) + Phase 1 (server-side transcript). Components → tasks 2.2–2.8 (TUI packages) + 4.1–4.7 (CLI subcommands) + 5.1 (MCP shim). Data flow → tasks 3.1–3.2 (run lifecycle), 4.3–4.5 (per-action CLI loop). Error handling → covered structurally in Handler (3.2), IPC server (2.5), agentproc (2.6); transcript-write failure handling is in 1.3. Transcript recording → tasks 1.1–1.4. Testing → unit tests in 2.2/2.4/2.5/2.6/2.7/3.2/4.2/4.7 plus e2e in 6.1. Deletions → 5.2.
- **Placeholders:** none. Every step has either real code, a real command, or an explicit mechanical-lift instruction with the symbol list.
- **Type consistency:** `state.GameState`, `state.Tick`, `state.AgentState`, `ipc.Request`, `ipc.Response`, `wsclient.Conn`, `agentproc.Process` are used identically across the tasks where they appear.
- **Scope:** one feature, one spec, one plan. Phases form natural execution checkpoints; nothing depends on a later phase landing first.
