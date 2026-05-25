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
