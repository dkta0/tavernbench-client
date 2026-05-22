// TavernBench Go TUI Spectator
// Zero-dependency spectator that connects to the Phoenix spectate channel
// and renders a live 2D map, action log, quest status, score and step counter.
// Uses only Go stdlib — no external packages required.
//
// Usage:
//   ./spectator [host] [zone] [api_key]
//   ./spectator 127.0.0.1:4100 tavern_hall spectator
package main

import (
	"bufio"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"math"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"
)

// ── ANSI escape helpers ───────────────────────────────────────────────────────

const (
	esc    = "\033["
	clear  = "\033[2J\033[H"
	altOn  = "\033[?1049h\033[H"
	altOff = "\033[?1049l"
	hide   = "\033[?25l"
	show   = "\033[?25h"
)

func bold(s string) string  { return esc + "1m" + s + esc + "0m" }
func dim(s string) string   { return esc + "2m" + s + esc + "0m" }
func color(c int, s string) string {
	return fmt.Sprintf("%s38;5;%dm%s%s0m", esc, c, s, esc)
}
func move(row, col int) string { return fmt.Sprintf("%s%d;%dH", esc, row, col) }
func yellow(s string) string  { return color(214, s) }
func cyan(s string) string    { return color(39, s) }
func red(s string) string     { return color(196, s) }
func green(s string) string   { return color(82, s) }
func orange(s string) string  { return color(214, s) }

// ── Phoenix wire protocol ─────────────────────────────────────────────────────

type PhxMsg [5]json.RawMessage

func encodeMsg(joinRef, ref interface{}, topic, event string, payload interface{}) ([]byte, error) {
	msg := []interface{}{joinRef, ref, topic, event, payload}
	return json.Marshal(msg)
}

// ── Payload types ─────────────────────────────────────────────────────────────

type TickPayload struct {
	Tick     int      `json:"tick"`
	ZoneID   string   `json:"zone_id"`
	Zone     ZoneMeta `json:"zone"`
	Entities []Entity `json:"entities"`
	QuestLog []Quest  `json:"quest_log"`
	Score    int      `json:"score"`
	Steps    int      `json:"steps"`
}

type ZoneMeta struct {
	ID     string `json:"id"`
	Width  int    `json:"width"`
	Height int    `json:"height"`
}

type Entity struct {
	Type     string   `json:"type"`
	ID       string   `json:"id"`
	Name     string   `json:"name"`
	Position Pos      `json:"position"`
	Distance float64  `json:"distance"`
	Health   *int     `json:"health"`
	MaxHP    *int     `json:"max_health"`
}

type Pos struct {
	X int `json:"x"`
	Y int `json:"y"`
}

type Quest struct {
	ID         string      `json:"id"`
	Name       string      `json:"name"`
	Objectives []Objective `json:"objectives"`
	Complete   bool        `json:"complete"`
}

type Objective struct {
	Description string `json:"description"`
	Complete    bool   `json:"complete"`
}

type EventPayload struct {
	Type       string `json:"type"`
	Attacker   string `json:"attacker"`
	Target     string `json:"target"`
	Damage     int    `json:"damage"`
	EntityName string `json:"entity_name"`
	ScoreDelta int    `json:"score_delta"`
}

type QuestCompletePayload struct {
	QuestName  string `json:"quest_name"`
	FinalScore int    `json:"final_score"`
	Steps      int    `json:"steps_taken"`
}

// ── Minimal WebSocket client (RFC 6455) ───────────────────────────────────────

type wsConn struct {
	conn net.Conn
	mu   sync.Mutex
}

func wsConnect(rawURL string) (*wsConn, error) {
	u, err := url.Parse(rawURL)
	if err != nil {
		return nil, err
	}
	host := u.Host
	if !strings.Contains(host, ":") {
		host += ":80"
	}
	conn, err := net.DialTimeout("tcp", host, 10*time.Second)
	if err != nil {
		return nil, err
	}

	key := wsKey()
	path := u.Path
	if u.RawQuery != "" {
		path += "?" + u.RawQuery
	}
	req := fmt.Sprintf(
		"GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n",
		path, u.Host, key,
	)
	if _, err := conn.Write([]byte(req)); err != nil {
		conn.Close()
		return nil, err
	}
	resp, err := http.ReadResponse(bufio.NewReader(conn), nil)
	if err != nil {
		conn.Close()
		return nil, err
	}
	resp.Body.Close()
	if resp.StatusCode != 101 {
		conn.Close()
		return nil, fmt.Errorf("unexpected status %d", resp.StatusCode)
	}
	return &wsConn{conn: conn}, nil
}

func wsKey() string {
	b := make([]byte, 16)
	rand.Read(b)
	return base64.StdEncoding.EncodeToString(b)
}

// WriteText sends a text frame (client-to-server, masked as required by RFC 6455).
func (w *wsConn) WriteText(data []byte) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	mask := make([]byte, 4)
	rand.Read(mask)

	header := []byte{0x81} // FIN + opcode text
	l := len(data)
	switch {
	case l < 126:
		header = append(header, byte(l|0x80))
	case l < 65536:
		header = append(header, 0xFE, byte(l>>8), byte(l))
	default:
		header = append(header, 0xFF,
			byte(l>>56), byte(l>>48), byte(l>>40), byte(l>>32),
			byte(l>>24), byte(l>>16), byte(l>>8), byte(l))
	}
	header = append(header, mask...)

	masked := make([]byte, l)
	for i, b := range data {
		masked[i] = b ^ mask[i%4]
	}
	_, err := w.conn.Write(append(header, masked...))
	return err
}

// ReadMsg reads one WebSocket frame and returns its payload (text frames only).
func (w *wsConn) ReadMsg() ([]byte, error) {
	hdr := make([]byte, 2)
	if _, err := readFull(w.conn, hdr); err != nil {
		return nil, err
	}
	// opcode
	opcode := hdr[0] & 0x0F
	// handle ping/close
	if opcode == 0x8 { // close
		return nil, fmt.Errorf("server closed connection")
	}

	masked := hdr[1]&0x80 != 0
	payLen := int(hdr[1] & 0x7F)
	switch payLen {
	case 126:
		ext := make([]byte, 2)
		readFull(w.conn, ext)
		payLen = int(ext[0])<<8 | int(ext[1])
	case 127:
		ext := make([]byte, 8)
		readFull(w.conn, ext)
		payLen = 0
		for _, b := range ext {
			payLen = payLen<<8 | int(b)
		}
	}

	var maskKey []byte
	if masked {
		maskKey = make([]byte, 4)
		readFull(w.conn, maskKey)
	}

	payload := make([]byte, payLen)
	readFull(w.conn, payload)

	if masked {
		for i := range payload {
			payload[i] ^= maskKey[i%4]
		}
	}

	// ignore non-text frames silently
	if opcode != 0x1 && opcode != 0x0 {
		return nil, nil
	}
	return payload, nil
}

func readFull(conn net.Conn, buf []byte) (int, error) {
	total := 0
	for total < len(buf) {
		n, err := conn.Read(buf[total:])
		total += n
		if err != nil {
			return total, err
		}
	}
	return total, nil
}

// ── Spectator state ───────────────────────────────────────────────────────────

type State struct {
	mu        sync.Mutex
	tick      TickPayload
	log       []string
	questDone *QuestCompletePayload
	lastTick  time.Time
	err       string
	connected bool
}

func (s *State) appendLog(line string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.log = append(s.log, line)
	if len(s.log) > 200 {
		s.log = s.log[len(s.log)-200:]
	}
}

// ── Rendering ─────────────────────────────────────────────────────────────────

// termSize tries to get terminal size; falls back to 80x24.
func termSize() (int, int) {
	// Try stty
	return 80, 24
}

func render(s *State, logOffset int) string {
	s.mu.Lock()
	tick := s.tick
	logLines := make([]string, len(s.log))
	copy(logLines, s.log)
	qd := s.questDone
	connected := s.connected
	errStr := s.err
	lastTick := s.lastTick
	s.mu.Unlock()

	w, h := termSize()

	if !connected {
		msg := "Connecting..."
		if errStr != "" {
			msg = red("Error: "+errStr) + "\nRetrying..."
		}
		return clear + move(1, 1) + msg
	}

	var sb strings.Builder
	sb.WriteString(altOn)
	sb.WriteString(hide)

	row := 1

	// ── Title bar ──
	lag := int64(0)
	if !lastTick.IsZero() {
		lag = time.Since(lastTick).Milliseconds()
	}
	title := bold(yellow("╔ TavernBench Spectator ╗")) +
		dim(fmt.Sprintf("  zone:%-12s  tick:%-5d  lag:%dms", tick.ZoneID, tick.Tick, lag))
	sb.WriteString(move(row, 1) + title)
	row++
	sb.WriteString(move(row, 1) + dim(strings.Repeat("─", w)))
	row++

	// ── Map panel (left) ──
	mapW := 35
	mapLines := renderMap(tick, mapW)
	for i, line := range mapLines {
		sb.WriteString(move(row+i, 1) + line)
	}

	// ── Action log panel (right) ──
	logPanelW := w - mapW - 2
	if logPanelW < 20 {
		logPanelW = 20
	}
	logCol := mapW + 3
	logPanelH := len(mapLines)
	logLines2 := renderLog(logLines, logOffset, logPanelW, logPanelH)
	for i, line := range logLines2 {
		sb.WriteString(move(row+i, logCol) + line)
	}

	row += int(math.Max(float64(len(mapLines)), float64(logPanelH))) + 1

	// ── Quest panel ──
	sb.WriteString(move(row, 1) + dim(strings.Repeat("─", w)))
	row++
	questLines := renderQuests(tick, qd, w)
	for _, line := range questLines {
		sb.WriteString(move(row, 1) + line)
		row++
	}

	// ── Status bar ──
	if row < h {
		sb.WriteString(move(h, 1) + dim(strings.Repeat("─", w)))
		status := fmt.Sprintf("Score:%-4d  Steps:%-4d  Entities:%-3d  q=quit  ↑↓=scroll log",
			tick.Score, tick.Steps, len(tick.Entities))
		sb.WriteString(move(h-1, 1) + green(status))
	}

	return sb.String()
}

func renderMap(tick TickPayload, w int) []string {
	zone := tick.Zone
	gw, gh := zone.Width, zone.Height
	if gw == 0 {
		gw, gh = 8, 6
	}

	// Build grid
	grid := make([][]string, gh)
	for y := range grid {
		grid[y] = make([]string, gw)
		for x := range grid[y] {
			grid[y][x] = dim("·")
		}
	}
	for _, e := range tick.Entities {
		x, y := e.Position.X, e.Position.Y
		if x < 0 || y < 0 || x >= gw || y >= gh {
			continue
		}
		switch e.Type {
		case "player":
			grid[y][x] = bold(yellow("@"))
		case "npc":
			grid[y][x] = cyan("N")
		case "enemy":
			grid[y][x] = bold(red("E"))
		case "item":
			grid[y][x] = green("i")
		case "exit":
			grid[y][x] = orange(">")
		default:
			grid[y][x] = "?"
		}
	}

	var lines []string
	header := bold(cyan(fmt.Sprintf(" Map: %s (%dx%d)", zone.ID, gw, gh)))
	lines = append(lines, padRight(header, w))

	border := "┌" + strings.Repeat("─", gw*2+1) + "┐"
	lines = append(lines, padRight(border, w))

	for y := 0; y < gh; y++ {
		var row strings.Builder
		row.WriteString("│ ")
		for x := 0; x < gw; x++ {
			row.WriteString(grid[y][x])
			if x < gw-1 {
				row.WriteString(" ")
			}
		}
		row.WriteString(" │")
		lines = append(lines, padRight(row.String(), w))
	}

	lines = append(lines, padRight("└"+strings.Repeat("─", gw*2+1)+"┘", w))

	legend := bold(yellow("@")) + dim("=player ") +
		cyan("N") + dim("=npc ") +
		bold(red("E")) + dim("=enemy ") +
		orange(">") + dim("=exit")
	lines = append(lines, padRight(legend, w))

	return lines
}

func renderLog(logLines []string, offset, w, h int) []string {
	header := bold(cyan(" Action Log")) + dim(fmt.Sprintf(" (%d entries)", len(logLines)))

	visible := h - 2
	if visible < 1 {
		visible = 1
	}

	start := 0
	if len(logLines) > visible {
		tailStart := len(logLines) - visible
		start = tailStart - offset
		if start < 0 {
			start = 0
		}
	}
	end := start + visible
	if end > len(logLines) {
		end = len(logLines)
	}

	var lines []string
	lines = append(lines, padRight(header, w))

	for i := start; i < end; i++ {
		entry := logLines[i]
		var colored string
		switch {
		case strings.HasPrefix(entry, "[combat]"):
			colored = red(entry)
		case strings.HasPrefix(entry, "[quest]"):
			colored = green(entry)
		case strings.HasPrefix(entry, "[died]"):
			colored = red(entry)
		default:
			colored = dim(entry)
		}
		lines = append(lines, padRight(colored, w))
	}

	for len(lines) < h {
		lines = append(lines, strings.Repeat(" ", w))
	}

	return lines
}

func renderQuests(tick TickPayload, qd *QuestCompletePayload, w int) []string {
	var lines []string
	lines = append(lines, bold(cyan(" Quests")))

	if qd != nil {
		lines = append(lines, green(fmt.Sprintf(
			"  ★ %s  COMPLETE  score:%d  steps:%d",
			qd.QuestName, qd.FinalScore, qd.Steps,
		)))
	}

	if len(tick.QuestLog) == 0 {
		if qd == nil {
			lines = append(lines, dim("  (none)"))
		}
		return lines
	}

	for _, q := range tick.QuestLog {
		status := dim("[ ]")
		name := q.Name
		if q.Complete {
			status = green("[✓]")
			name = green(name)
		}
		lines = append(lines, fmt.Sprintf("  %s %s", status, name))
		for _, obj := range q.Objectives {
			sym := dim("  ○")
			desc := dim(obj.Description)
			if obj.Complete {
				sym = green("  ✓")
				desc = green(obj.Description)
			}
			lines = append(lines, fmt.Sprintf("    %s %s", sym, desc))
		}
	}

	return lines
}

// padRight pads a string to width w (visual width — naively counts bytes,
// ANSI escapes skew this but it's good enough for the game map).
func padRight(s string, w int) string {
	visible := visibleLen(s)
	if visible < w {
		return s + strings.Repeat(" ", w-visible)
	}
	return s
}

// visibleLen strips ANSI escapes and returns rune count.
func visibleLen(s string) int {
	inEsc := false
	count := 0
	for _, r := range s {
		switch {
		case r == '\033':
			inEsc = true
		case inEsc && r == 'm':
			inEsc = false
		case !inEsc:
			count++
		}
	}
	return count
}

// ── Main loop ─────────────────────────────────────────────────────────────────

func main() {
	host := "127.0.0.1:4100"
	zone := "tavern_hall"
	apiKey := "spectator"

	if len(os.Args) > 1 {
		host = os.Args[1]
	}
	if len(os.Args) > 2 {
		zone = os.Args[2]
	}
	if len(os.Args) > 3 {
		apiKey = os.Args[3]
	}

	state := &State{}

	// Enter alt screen, hide cursor
	fmt.Print(altOn + hide)
	defer func() {
		fmt.Print(show + altOff)
	}()

	// Catch signals
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		<-sig
		fmt.Print(show + altOff)
		os.Exit(0)
	}()

	// Input: keyboard
	logOffset := 0
	go func() {
		buf := make([]byte, 1)
		for {
			n, err := os.Stdin.Read(buf)
			if err != nil || n == 0 {
				continue
			}
			switch buf[0] {
			case 'q', 'Q', 3: // q, Q, ctrl+c
				fmt.Print(show + altOff)
				os.Exit(0)
			case 'A': // up arrow (ESC [ A)
				logOffset++
			case 'B': // down arrow
				if logOffset > 0 {
					logOffset--
				}
			case 'k':
				logOffset++
			case 'j':
				if logOffset > 0 {
					logOffset--
				}
			}
		}
	}()

	// WebSocket goroutine
	go runWS(state, host, zone, apiKey)

	// Render loop — 10 fps
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	for range ticker.C {
		fmt.Print(render(state, logOffset))
	}
}

func runWS(state *State, host, zone, apiKey string) {
	wsURL := fmt.Sprintf("ws://%s/socket/websocket?api_key=%s&protocol_version=1.0", host, apiKey)
	refCounter := 1

	for {
		state.mu.Lock()
		state.connected = false
		state.err = ""
		state.mu.Unlock()

		ws, err := wsConnect(wsURL)
		if err != nil {
			state.mu.Lock()
			state.err = err.Error()
			state.mu.Unlock()
			time.Sleep(2 * time.Second)
			continue
		}

		// Join spectate channel
		joinMsg, _ := encodeMsg("1", "1", "spectate:"+zone, "phx_join",
			map[string]string{"protocol_version": "1.0"})
		if err := ws.WriteText(joinMsg); err != nil {
			ws.conn.Close()
			time.Sleep(2 * time.Second)
			continue
		}

		state.mu.Lock()
		state.connected = true
		state.err = ""
		state.mu.Unlock()

		// Heartbeat goroutine
		stopHB := make(chan struct{})
		go func() {
			t := time.NewTicker(30 * time.Second)
			defer t.Stop()
			for {
				select {
				case <-t.C:
					refCounter++
					hb, _ := encodeMsg(nil, fmt.Sprintf("hb-%d", refCounter), "phoenix", "heartbeat", map[string]string{})
					ws.WriteText(hb)
				case <-stopHB:
					return
				}
			}
		}()

		// Read loop
		for {
			raw, err := ws.ReadMsg()
			if err != nil {
				break
			}
			if raw == nil {
				continue
			}
			handleMsg(state, raw)
		}

		close(stopHB)
		ws.conn.Close()

		state.mu.Lock()
		state.connected = false
		state.err = "disconnected — reconnecting"
		state.mu.Unlock()
		time.Sleep(2 * time.Second)
	}
}

func handleMsg(state *State, raw []byte) {
	var msg PhxMsg
	if err := json.Unmarshal(raw, &msg); err != nil {
		return
	}
	var event string
	json.Unmarshal(msg[3], &event)

	switch event {
	case "tick":
		var t TickPayload
		if err := json.Unmarshal(msg[4], &t); err == nil {
			state.mu.Lock()
			state.tick = t
			state.lastTick = time.Now()
			state.mu.Unlock()
		}

	case "event":
		var e EventPayload
		if err := json.Unmarshal(msg[4], &e); err != nil {
			return
		}
		switch e.Type {
		case "combat":
			state.appendLog(fmt.Sprintf("[combat] %s → %s  dmg:%d", e.Attacker, e.Target, e.Damage))
		case "entity_died":
			state.appendLog(fmt.Sprintf("[died]   %s  score_delta:%+d", e.EntityName, e.ScoreDelta))
		case "fled":
			state.appendLog("[event]  player fled")
		}

	case "quest_complete":
		var qc QuestCompletePayload
		if err := json.Unmarshal(msg[4], &qc); err == nil {
			state.mu.Lock()
			state.questDone = &qc
			state.mu.Unlock()
			state.appendLog(fmt.Sprintf("[quest]  %s COMPLETE  score:%d  steps:%d",
				qc.QuestName, qc.FinalScore, qc.Steps))
		}
	}
}
