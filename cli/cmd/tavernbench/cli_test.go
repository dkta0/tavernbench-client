package main

import (
	"bytes"
	"encoding/json"
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
	if !bytes.Contains(out, []byte(`"echo":"observe"`)) {
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
