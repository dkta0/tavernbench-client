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
