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

func NewHandler(s *state.GameState, zone, mode string) *Handler {
	return &Handler{
		state: s,
		zone:  zone,
		mode:  mode,
		tickC: make(chan state.Tick, 4),
	}
}

func (h *Handler) SetConn(c *wsclient.Conn) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.conn = c
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
		if h.conn == nil {
			return ipc.Response{ID: req.ID, OK: false,
				Error: &ipc.ErrorBody{Code: "no_connection", Message: "not connected to server"}}
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
	raw, _ := json.Marshal(args)
	msg, _ := wsclient.EncodeMsg("1", fmt.Sprintf("%d", h.ref), "zone:"+h.zone, "action:"+verb, json.RawMessage(raw))
	return h.conn.WriteText(msg)
}

// Heartbeat sends a phx_heartbeat to keep the WS alive. Run in its own goroutine.
func (h *Handler) Heartbeat(interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for range ticker.C {
		h.mu.Lock()
		if h.conn == nil {
			h.mu.Unlock()
			return
		}
		h.ref++
		msg, _ := wsclient.EncodeMsg(nil, fmt.Sprintf("%d", h.ref), "phoenix", "phx_heartbeat", json.RawMessage("{}"))
		err := h.conn.WriteText(msg)
		h.mu.Unlock()
		if err != nil {
			return
		}
	}
}

func (h *Handler) waitForTick(timeout time.Duration) {
	h.mu.Unlock()
	defer h.mu.Lock()
	select {
	case <-h.tickC:
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
				h.mu.Lock()
				state.Apply(s, t)
				h.mu.Unlock()
				select {
				case h.tickC <- t:
				default:
				}
			}
		case "quest_complete":
			var qc struct {
				FinalScore int    `json:"final_score"`
				Steps      int    `json:"steps_taken"`
				RunID      string `json:"run_id"`
			}
			if json.Unmarshal(arr[4], &qc) == nil {
				h.mu.Lock()
				state.Complete(s, qc.FinalScore, qc.Steps, qc.RunID)
				h.mu.Unlock()
			}
		}
	}
}
