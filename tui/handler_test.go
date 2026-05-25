package main

import (
	"context"
	"testing"

	"github.com/tavernbench/tui/internal/ipc"
	"github.com/tavernbench/tui/internal/state"
)

func TestHandler_Attach_SetsAgentName(t *testing.T) {
	s := &state.GameState{}
	h := NewHandler(s, "tavern_hall", "play")
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
	h := NewHandler(s, "tavern_hall", "play")
	resp := h.HandleRequest(context.Background(), ipc.Request{ID: "2", Op: ipc.OpAttach, Name: "second"})
	if resp.OK || resp.Error == nil || resp.Error.Code != "already_attached" {
		t.Fatalf("expected already_attached: %+v", resp)
	}
}

func TestHandler_ObserveReturnsState(t *testing.T) {
	s := &state.GameState{Tick: state.Tick{Score: 5, Steps: 2}}
	h := NewHandler(s, "tavern_hall", "play")
	resp := h.HandleRequest(context.Background(), ipc.Request{ID: "3", Op: ipc.OpObserve})
	if !resp.OK || resp.Observation["score"] != 5 {
		t.Fatalf("bad observe response: %+v", resp)
	}
}
