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
	"unsafe"

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
	handler := NewHandler(s, *zone, *mode)
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

	conn, err := wsclient.Connect(fmt.Sprintf("ws://%s/socket/websocket?api_key=%s", *host, apiKey))
	if err != nil {
		fmt.Fprintf(os.Stderr, "tavernbench: ws connect failed: %v\n", err)
		os.Exit(2)
	}
	handler.SetConn(conn)

	if err := handler.Join(); err != nil {
		fmt.Fprintf(os.Stderr, "tavernbench: join failed: %v\n", err)
		os.Exit(2)
	}
	go handler.ReadLoop(s)

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

func termWidth() int  { w, _ := termSize(); return w }
func termHeight() int { _, h := termSize(); return h }

// termSize returns the current terminal width and height, defaulting to 80x24
// if the syscall fails (e.g., not a TTY).
func termSize() (int, int) {
	type winsize struct {
		Rows, Cols, X, Y uint16
	}
	ws := &winsize{}
	_, _, errno := syscall.Syscall(
		syscall.SYS_IOCTL,
		uintptr(os.Stdout.Fd()),
		uintptr(syscall.TIOCGWINSZ),
		uintptr(unsafe.Pointer(ws)),
	)
	if errno != 0 {
		return 80, 24
	}
	return int(ws.Cols), int(ws.Rows)
}
