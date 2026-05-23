// TavernBench Go TUI — Human Player Mode
// Connects to the arena as a real player via zone:* channel.
// Arrow keys or WASD to move, t=talk, a=attack, i=inventory, e=enter, q=quit.
//
// Usage:
//   ./play [host] [zone] [api_key]
//   ./play 127.0.0.1:4100 tavern_hall YOUR_KEY
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
func italic(s string) string { return esc + "3m" + s + esc + "0m" }
func color(c int, s string) string {
	return fmt.Sprintf("%s38;5;%dm%s%s0m", esc, c, s, esc)
}
func move(row, col int) string { return fmt.Sprintf("%s%d;%dH", esc, row, col) }
func yellow(s string) string   { return color(214, s) }
func cyan(s string) string     { return color(39, s) }
func red(s string) string      { return color(196, s) }
func green(s string) string    { return color(82, s) }
func orange(s string) string   { return color(214, s) }
func magenta(s string) string  { return color(201, s) }
func white(s string) string    { return color(255, s) }
func gray(s string) string     { return color(245, s) }

// ── Phoenix wire protocol ─────────────────────────────────────────────────────

type PhxMsg [5]json.RawMessage

func encodeMsg(joinRef, ref interface{}, topic, event string, payload interface{}) ([]byte, error) {
	msg := []interface{}{joinRef, ref, topic, event, payload}
	return json.Marshal(msg)
}

// ── Payload types ─────────────────────────────────────────────────────────────

type TickPayload struct {
	Tick      int           `json:"tick"`
	ZoneID    string        `json:"zone_id"`
	Zone      ZoneMeta      `json:"zone"`
	Position  Pos           `json:"position"`
	Entities  []Entity      `json:"entities"`
	Inventory []InvItem     `json:"inventory"`
	QuestLog  []Quest       `json:"quest_log"`
	Score     int           `json:"score"`
	Steps     int           `json:"steps"`
}

type ZoneMeta struct {
	ID     string `json:"id"`
	Width  int    `json:"width"`
	Height int    `json:"height"`
}

type Entity struct {
	Type     string  `json:"type"`
	ID       string  `json:"id"`
	Name     string  `json:"name"`
	Position Pos     `json:"position"`
	Distance float64 `json:"distance"`
	Health   *int    `json:"health"`
	MaxHP    *int    `json:"max_health"`
}

type InvItem struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	Quantity int    `json:"quantity"`
}

type Pos struct {
	X int `json:"x"`
	Y int `json:"y"`
}

type Quest struct {
	ID         string      `json:"id"`
	Name       string      `json:"name"`
	Description string     `json:"description"`
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
	ToZone     string `json:"to_zone"`
}

type DialoguePayload struct {
	NPC     string          `json:"npc"`
	Name    string          `json:"name"`
	Text    string          `json:"text"`
	Choices []DialogChoice  `json:"choices"`
}

type DialogChoice struct {
	ID   int    `json:"id"`
	Text string `json:"text"`
}

type QuestCompletePayload struct {
	QuestName  string `json:"quest_name"`
	FinalScore int    `json:"final_score"`
	Steps      int    `json:"steps_taken"`
}

// ── WebSocket (minimal RFC 6455 client) ──────────────────────────────────────

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

func (w *wsConn) WriteText(data []byte) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	mask := make([]byte, 4)
	rand.Read(mask)

	header := []byte{0x81}
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

func (w *wsConn) ReadMsg() ([]byte, error) {
	hdr := make([]byte, 2)
	if _, err := readFull(w.conn, hdr); err != nil {
		return nil, err
	}
	opcode := hdr[0] & 0x0F
	if opcode == 0x8 {
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

// ── Player state ──────────────────────────────────────────────────────────────

type Mode int

const (
	ModePlay Mode = iota
	ModeDialogue
	ModeInventory
	ModeQuests
)

type State struct {
	mu        sync.Mutex
	tick      TickPayload
	log       []string
	questDone *QuestCompletePayload
	dialogue  *DialoguePayload
	mode      Mode
	logOffset int
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

// ── Actions sent to server ────────────────────────────────────────────────────

var (
	wsMu      sync.Mutex
	wsGlobal  *wsConn
	zoneID    string
	refCount  int
)

func sendAction(event string, payload map[string]interface{}) {
	wsMu.Lock()
	ws := wsGlobal
	wsMu.Unlock()
	if ws == nil {
		return
	}
	refCount++
	msg, err := encodeMsg("1", fmt.Sprintf("%d", refCount), "zone:"+zoneID, event, payload)
	if err != nil {
		return
	}
	ws.WriteText(msg)
}

// ── Rendering ─────────────────────────────────────────────────────────────────

func termSize() (int, int) {
	return 80, 24
}

func render(s *State) string {
	s.mu.Lock()
	tick := s.tick
	logLines := make([]string, len(s.log))
	copy(logLines, s.log)
	qd := s.questDone
	dialogue := s.dialogue
	mode := s.mode
	connected := s.connected
	errStr := s.err
	lastTick := s.lastTick
	logOffset := s.logOffset
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
	title := bold(magenta("╔ TavernBench ╗")) + bold(yellow(" ► PLAYER MODE")) +
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

	// ── Side panel (right) ──
	sideW := w - mapW - 3
	if sideW < 20 {
		sideW = 20
	}
	sideCol := mapW + 3
	sideH := len(mapLines)

	switch mode {
	case ModeDialogue:
		if dialogue != nil {
			sideLines := renderDialogue(dialogue, sideW, sideH)
			for i, line := range sideLines {
				sb.WriteString(move(row+i, sideCol) + line)
			}
		}
	case ModeInventory:
		sideLines := renderInventory(tick.Inventory, sideW, sideH)
		for i, line := range sideLines {
			sb.WriteString(move(row+i, sideCol) + line)
		}
	case ModeQuests:
		sideLines := renderQuestPanel(tick.QuestLog, sideW, sideH)
		for i, line := range sideLines {
			sb.WriteString(move(row+i, sideCol) + line)
		}
	default:
		// Action log
		logLines2 := renderLog(logLines, logOffset, sideW, sideH)
		for i, line := range logLines2 {
			sb.WriteString(move(row+i, sideCol) + line)
		}
	}

	row += int(math.Max(float64(len(mapLines)), float64(sideH))) + 1

	// ── Quest panel ──
	sb.WriteString(move(row, 1) + dim(strings.Repeat("─", w)))
	row++
	questLines := renderQuestsInline(tick, qd, w)
	for _, line := range questLines {
		if row >= h-3 {
			break
		}
		sb.WriteString(move(row, 1) + line)
		row++
	}

	// ── Status bar & keybinds ──
	if h > 3 {
		var controls string
		switch mode {
		case ModeDialogue:
			controls = magenta("DIALOGUE ") + dim("1-9=choose  ESC=cancel")
		case ModeInventory:
			controls = cyan("INVENTORY ") + dim("i=close")
		case ModeQuests:
			controls = yellow("QUESTS ") + dim("p=close")
		default:
			controls = dim("←↑↓→/WASD=move  t=talk  a=attack  e=enter  i=inv  p=quests  f=flee  ↑↓=scroll  q=quit")
		}
		sb.WriteString(move(h-1, 1) + dim(strings.Repeat("─", w)))
		statusLine := fmt.Sprintf(" %s Score:%-4d  Steps:%-4d  HP:%s",
			controls,
			tick.Score, tick.Steps, hpString(tick, tick.Position),
		)
		sb.WriteString(move(h, 1) + green(padRight(statusLine, w)))
	}

	return sb.String()
}

func hpString(tick TickPayload, pos Pos) string {
	// Find player entity
	for _, e := range tick.Entities {
		if e.Type == "player" && e.Position.X == pos.X && e.Position.Y == pos.Y {
			if e.Health != nil && e.MaxHP != nil {
				return fmt.Sprintf("%d/%d", *e.Health, *e.MaxHP)
			}
			if e.Health != nil {
				return fmt.Sprintf("%d", *e.Health)
			}
		}
	}
	return "?"
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

	// Player position (self)
	px, py := tick.Position.X, tick.Position.Y

	for _, e := range tick.Entities {
		x, y := e.Position.X, e.Position.Y
		if x < 0 || y < 0 || x >= gw || y >= gh {
			continue
		}
		// Own player gets special glyph
		if e.Type == "player" && x == px && y == py {
			grid[y][x] = bold(magenta("@"))
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

	legend := bold(magenta("@")) + dim("=you ") +
		bold(yellow("@")) + dim("=other ") +
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
		case strings.HasPrefix(entry, "[dialogue]"):
			colored = cyan(entry)
		case strings.HasPrefix(entry, "[moved]"):
			colored = dim(entry)
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

func renderDialogue(d *DialoguePayload, w, h int) []string {
	var lines []string
	lines = append(lines, bold(cyan(fmt.Sprintf(" ┌─ %s ─┐", d.Name))))
	lines = append(lines, "")

	// Wrap text
	words := strings.Fields(d.Text)
	lineW := w - 2
	var current string
	for _, word := range words {
		if current == "" {
			current = word
		} else if len(current)+1+len(word) <= lineW {
			current += " " + word
		} else {
			lines = append(lines, padRight(" "+italic(current), w))
			current = word
		}
	}
	if current != "" {
		lines = append(lines, padRight(" "+italic(current), w))
	}

	lines = append(lines, "")
	lines = append(lines, bold(yellow(" Choices:")))
	for _, c := range d.Choices {
		line := fmt.Sprintf(" %s %s", bold(fmt.Sprintf("[%d]", c.ID)), c.Text)
		lines = append(lines, padRight(line, w))
	}

	for len(lines) < h {
		lines = append(lines, strings.Repeat(" ", w))
	}
	return lines
}

func renderInventory(inv []InvItem, w, h int) []string {
	var lines []string
	lines = append(lines, bold(cyan(" ┌─ Inventory ─┐")))
	if len(inv) == 0 {
		lines = append(lines, dim("  (empty)"))
	} else {
		for _, item := range inv {
			line := fmt.Sprintf("  %s x%d", white(item.Name), item.Quantity)
			lines = append(lines, padRight(line, w))
		}
	}
	for len(lines) < h {
		lines = append(lines, strings.Repeat(" ", w))
	}
	return lines
}

func renderQuestPanel(quests []Quest, w, h int) []string {
	var lines []string
	lines = append(lines, bold(cyan(" ┌─ Quests ─┐")))
	if len(quests) == 0 {
		lines = append(lines, dim("  (none)"))
	} else {
		for _, q := range quests {
			sym := dim("[ ]")
			name := q.Name
			if q.Complete {
				sym = green("[✓]")
				name = green(name)
			}
			lines = append(lines, fmt.Sprintf("  %s %s", sym, name))
			for _, obj := range q.Objectives {
				osym := dim("  ○")
				odesc := dim(obj.Description)
				if obj.Complete {
					osym = green("  ✓")
					odesc = green(obj.Description)
				}
				lines = append(lines, fmt.Sprintf("    %s %s", osym, odesc))
			}
		}
	}
	for len(lines) < h {
		lines = append(lines, strings.Repeat(" ", w))
	}
	return lines
}

func renderQuestsInline(tick TickPayload, qd *QuestCompletePayload, w int) []string {
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
	}

	return lines
}

func padRight(s string, w int) string {
	visible := visibleLen(s)
	if visible < w {
		return s + strings.Repeat(" ", w-visible)
	}
	return s
}

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

// ── Terminal raw mode helpers ─────────────────────────────────────────────────

func setRawMode() ([]byte, error) {
	// Read current termios
	out, err := runStty("-g")
	if err != nil {
		return nil, err
	}
	saved := []byte(strings.TrimSpace(string(out)))
	// Set raw mode
	runStty("raw", "-echo")
	return saved, nil
}

func restoreTermios(saved []byte) {
	if len(saved) > 0 {
		runStty(string(saved))
	}
}

func runStty(args ...string) ([]byte, error) {
	// Use syscall.Exec approach: just write to /dev/tty via shell.
	// We implement raw mode by writing to /dev/tty directly.
	// stty is available everywhere on Linux.
	f, err := os.OpenFile("/dev/tty", os.O_RDWR, 0)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	fullArgs := append([]string{"stty"}, args...)
	cmd := strings.Join(fullArgs, " ")
	// We shell out via /bin/sh
	pipe_r, pipe_w, _ := os.Pipe()
	defer pipe_r.Close()

	attr := &syscall.ProcAttr{
		Files: []uintptr{f.Fd(), pipe_w.Fd(), 2},
	}
	pid, err := syscall.ForkExec("/bin/sh", []string{"/bin/sh", "-c", cmd}, attr)
	if err != nil {
		pipe_w.Close()
		return nil, err
	}
	pipe_w.Close()
	var buf []byte
	tmp := make([]byte, 256)
	for {
		n, err := pipe_r.Read(tmp)
		if n > 0 {
			buf = append(buf, tmp[:n]...)
		}
		if err != nil {
			break
		}
	}
	syscall.Wait4(pid, nil, 0, nil)
	return buf, nil
}

// ── Main loop ─────────────────────────────────────────────────────────────────

func main() {
	host := "127.0.0.1:4100"
	zone := "tavern_hall"
	apiKey := ""

	if len(os.Args) > 1 {
		host = os.Args[1]
	}
	if len(os.Args) > 2 {
		zone = os.Args[2]
	}
	if len(os.Args) > 3 {
		apiKey = os.Args[3]
	}
	zoneID = zone

	state := &State{}

	// Enter alt screen, hide cursor
	fmt.Print(altOn + hide)

	// Set terminal raw mode
	saved, err := setRawMode()
	cleanup := func() {
		fmt.Print(show + altOff)
		if err == nil {
			restoreTermios(saved)
		}
	}
	defer cleanup()

	// Catch signals
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		<-sig
		cleanup()
		os.Exit(0)
	}()

	// Input goroutine
	go readInput(state)

	// WebSocket goroutine
	go runWS(state, host, apiKey)

	// Render loop — 10 fps
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	for range ticker.C {
		fmt.Print(render(state))
	}
}

func readInput(state *State) {
	buf := make([]byte, 8)
	for {
		n, err := os.Stdin.Read(buf)
		if err != nil || n == 0 {
			continue
		}

		state.mu.Lock()
		mode := state.mode
		dialogue := state.dialogue
		state.mu.Unlock()

		b := buf[0]

		// ESC sequences (arrow keys)
		if n >= 3 && b == 0x1b && buf[1] == '[' {
			switch buf[2] {
			case 'A': // up
				if mode == ModePlay {
					sendAction("action:move", map[string]interface{}{"direction": "north"})
					state.appendLog("[moved]  north")
				}
			case 'B': // down
				if mode == ModePlay {
					sendAction("action:move", map[string]interface{}{"direction": "south"})
					state.appendLog("[moved]  south")
				}
			case 'C': // right
				if mode == ModePlay {
					sendAction("action:move", map[string]interface{}{"direction": "east"})
					state.appendLog("[moved]  east")
				}
			case 'D': // left
				if mode == ModePlay {
					sendAction("action:move", map[string]interface{}{"direction": "west"})
					state.appendLog("[moved]  west")
				}
			}
			continue
		}

		// ESC alone
		if b == 0x1b && n == 1 {
			state.mu.Lock()
			state.mode = ModePlay
			state.dialogue = nil
			state.mu.Unlock()
			continue
		}

		switch mode {
		case ModeDialogue:
			if dialogue != nil && b >= '1' && b <= '9' {
				choiceID := int(b - '0')
				sendAction("action:reply", map[string]interface{}{"choice": choiceID})
				state.appendLog(fmt.Sprintf("[dialogue] replied %d", choiceID))
				state.mu.Lock()
				state.mode = ModePlay
				state.dialogue = nil
				state.mu.Unlock()
			} else if b == 'q' || b == 3 {
				state.mu.Lock()
				state.mode = ModePlay
				state.dialogue = nil
				state.mu.Unlock()
			}

		case ModeInventory:
			switch b {
			case 'i', 'I', 'q', 3:
				state.mu.Lock()
				state.mode = ModePlay
				state.mu.Unlock()
			}

		case ModeQuests:
			switch b {
			case 'p', 'P', 'q', 3:
				state.mu.Lock()
				state.mode = ModePlay
				state.mu.Unlock()
			}

		default: // ModePlay
			switch b {
			case 'q', 'Q', 3: // quit
				fmt.Print(show + altOff)
				os.Exit(0)

			// Movement: WASD + vi keys
			case 'w', 'W', 'k':
				sendAction("action:move", map[string]interface{}{"direction": "north"})
				state.appendLog("[moved]  north")
			case 's', 'S', 'j':
				sendAction("action:move", map[string]interface{}{"direction": "south"})
				state.appendLog("[moved]  south")
			case 'd', 'D', 'l':
				sendAction("action:move", map[string]interface{}{"direction": "east"})
				state.appendLog("[moved]  east")
			case 'a', 'A', 'h':
				sendAction("action:move", map[string]interface{}{"direction": "west"})
				state.appendLog("[moved]  west")

			// Talk to nearest NPC
			case 't', 'T':
				state.mu.Lock()
				tick := state.tick
				state.mu.Unlock()
				nearest := nearestEntity(tick.Entities, "npc")
				if nearest != nil {
					sendAction("action:speak", map[string]interface{}{"target": nearest.ID})
					state.appendLog(fmt.Sprintf("[dialogue] speaking to %s", nearest.Name))
				} else {
					state.appendLog("[info]  no NPC nearby")
				}

			// Attack nearest enemy
			case 'a' + 32: // handled above as 'a'=west, but uppercase A=attack
			// use 'x' for attack to avoid conflict
			case 'x', 'X':
				state.mu.Lock()
				tick := state.tick
				state.mu.Unlock()
				nearest := nearestEntity(tick.Entities, "enemy")
				if nearest != nil {
					sendAction("action:attack", map[string]interface{}{"target": nearest.ID})
					state.appendLog(fmt.Sprintf("[combat] attacking %s", nearest.Name))
				} else {
					state.appendLog("[info]  no enemy nearby")
				}

			// Enter exit
			case 'e', 'E':
				state.mu.Lock()
				tick := state.tick
				state.mu.Unlock()
				nearest := nearestEntity(tick.Entities, "exit")
				if nearest != nil {
					sendAction("action:enter", map[string]interface{}{"target": nearest.ID})
					state.appendLog(fmt.Sprintf("[event]  entering %s", nearest.Name))
				} else {
					state.appendLog("[info]  no exit nearby")
				}

			// Pickup item
			case 'g', 'G':
				state.mu.Lock()
				tick := state.tick
				state.mu.Unlock()
				nearest := nearestEntity(tick.Entities, "item")
				if nearest != nil {
					sendAction("action:pickup", map[string]interface{}{"target": nearest.ID})
					state.appendLog(fmt.Sprintf("[event]  picking up %s", nearest.Name))
				} else {
					state.appendLog("[info]  no item nearby")
				}

			// Inventory
			case 'i', 'I':
				state.mu.Lock()
				state.mode = ModeInventory
				state.mu.Unlock()

			// Quest log
			case 'p', 'P':
				state.mu.Lock()
				state.mode = ModeQuests
				state.mu.Unlock()

			// Flee
			case 'f', 'F':
				sendAction("action:flee", map[string]interface{}{})
				state.appendLog("[event]  fleeing!")

			// Wait / rest
			case '.':
				sendAction("action:wait", map[string]interface{}{})
				state.appendLog("[event]  waiting")

			// Scroll log up/down
			case 'K':
				state.mu.Lock()
				state.logOffset++
				state.mu.Unlock()
			case 'J':
				state.mu.Lock()
				if state.logOffset > 0 {
					state.logOffset--
				}
				state.mu.Unlock()
			}
		}
	}
}

func nearestEntity(entities []Entity, typ string) *Entity {
	var nearest *Entity
	minDist := math.MaxFloat64
	for i := range entities {
		e := &entities[i]
		if e.Type == typ && e.Distance < minDist {
			minDist = e.Distance
			nearest = e
		}
	}
	return nearest
}

// ── WebSocket goroutine ───────────────────────────────────────────────────────

func runWS(state *State, host, apiKey string) {
	wsURL := fmt.Sprintf("ws://%s/socket/websocket?api_key=%s&protocol_version=1.0", host, url.QueryEscape(apiKey))
	refC := 1

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

		wsMu.Lock()
		wsGlobal = ws
		refCount = 1
		wsMu.Unlock()

		// Join zone channel as player
		joinMsg, _ := encodeMsg("1", fmt.Sprintf("%d", refC), "zone:"+zoneID, "phx_join",
			map[string]string{"protocol_version": "1.0"})
		refC++
		if err := ws.WriteText(joinMsg); err != nil {
			ws.conn.Close()
			time.Sleep(2 * time.Second)
			continue
		}

		state.mu.Lock()
		state.connected = true
		state.err = ""
		state.mu.Unlock()

		state.appendLog("[info]  connected — use arrows/WASD to move")

		// Heartbeat goroutine
		stopHB := make(chan struct{})
		go func() {
			t := time.NewTicker(30 * time.Second)
			defer t.Stop()
			for {
				select {
				case <-t.C:
					refC++
					hb, _ := encodeMsg(nil, fmt.Sprintf("hb-%d", refC), "phoenix", "heartbeat", map[string]string{})
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
		wsMu.Lock()
		wsGlobal = nil
		wsMu.Unlock()
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

	case "dialogue":
		var d DialoguePayload
		if err := json.Unmarshal(msg[4], &d); err == nil {
			state.mu.Lock()
			state.dialogue = &d
			state.mode = ModeDialogue
			state.mu.Unlock()
			state.appendLog(fmt.Sprintf("[dialogue] %s: %s", d.Name, truncate(d.Text, 60)))
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
		case "zone_entered":
			state.appendLog(fmt.Sprintf("[event]  entered zone: %s", e.ToZone))
			// Update zone tracking
			wsMu.Lock()
			zoneID = e.ToZone
			wsMu.Unlock()
		default:
			if e.Type != "" {
				state.appendLog(fmt.Sprintf("[event]  %s", e.Type))
			}
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

	case "phx_reply":
		// Action acks — mostly ignore, but could surface errors
		var reply struct {
			Status   string          `json:"status"`
			Response json.RawMessage `json:"response"`
		}
		if err := json.Unmarshal(msg[4], &reply); err == nil && reply.Status == "error" {
			state.appendLog(fmt.Sprintf("[error]  %s", string(reply.Response)))
		}
	}
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n-3] + "..."
}
