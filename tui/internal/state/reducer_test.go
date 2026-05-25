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
