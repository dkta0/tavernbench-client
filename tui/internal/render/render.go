// Package render is the spectator frame renderer for TavernBench TUI.
//
// It is intentionally pure: given a state.GameState snapshot and the terminal
// dimensions, Render returns the entire frame as a string. The legacy renderer
// in tui/main.go (the spectator monolith) is being replaced piece by piece;
// this package is the visual half of that work.
package render

import (
	"fmt"
	"strings"

	"github.com/tavernbench/tui/internal/state"
)

const esc = "\x1b["

// ── ANSI helpers — lifted from tui/main.go. Keep behavior identical. ──

func bold(s string) string { return esc + "1m" + s + esc + "0m" }
func dim(s string) string  { return esc + "2m" + s + esc + "0m" }

func color(c int, s string) string {
	return fmt.Sprintf("%s38;5;%dm%s%s0m", esc, c, s, esc)
}

func yellow(s string) string { return color(214, s) }
func cyan(s string) string   { return color(39, s) }
func red(s string) string    { return color(196, s) }
func green(s string) string  { return color(82, s) }
func orange(s string) string { return color(214, s) }

// Render returns the full frame for the current GameState, sized to w x h.
func Render(s *state.GameState, w, h int) string {
	var sb strings.Builder

	// ── Title bar (with agent badge) ──
	sb.WriteString(renderTitle(s, w))
	sb.WriteString("\n")
	sb.WriteString(dim(strings.Repeat("─", w)))
	sb.WriteString("\n")

	// ── Map panel ──
	mapW := 35
	mapLines := renderMap(s.Tick, mapW)
	logPanelW := w - mapW - 2
	if logPanelW < 20 {
		logPanelW = 20
	}
	logPanelH := len(mapLines)
	logLines := renderLog(s.LogLines, 0, logPanelW, logPanelH)

	// Compose map + log side-by-side row by row.
	rows := len(mapLines)
	if len(logLines) > rows {
		rows = len(logLines)
	}
	for i := 0; i < rows; i++ {
		var left, right string
		if i < len(mapLines) {
			left = mapLines[i]
		} else {
			left = strings.Repeat(" ", mapW)
		}
		if i < len(logLines) {
			right = logLines[i]
		} else {
			right = strings.Repeat(" ", logPanelW)
		}
		sb.WriteString(left)
		sb.WriteString("  ")
		sb.WriteString(right)
		sb.WriteString("\n")
	}

	sb.WriteString(dim(strings.Repeat("─", w)))
	sb.WriteString("\n")

	// ── Quest panel ──
	for _, line := range renderQuests(s, w) {
		sb.WriteString(line)
		sb.WriteString("\n")
	}

	// ── Status bar ──
	status := fmt.Sprintf("Score:%-4d  Steps:%-4d  Entities:%-3d  q=quit  ↑↓=scroll log",
		s.Tick.Score, s.Tick.Steps, len(s.Tick.Entities))
	sb.WriteString(green(status))

	return sb.String()
}

// renderTitle draws the top status row, including the agent attach badge —
// this is the one intentional visual addition relative to the legacy renderer.
func renderTitle(s *state.GameState, w int) string {
	badge := dim("Awaiting agent…")
	if s.AgentState == state.AgentAttached {
		badge = color(214, fmt.Sprintf("[ AGENT • %s ]", s.AgentName))
	}
	title := bold(yellow("╔ TavernBench Spectator ╗")) +
		dim(fmt.Sprintf("  zone:%-12s  tick:%-5d", s.Tick.ZoneID, s.Tick.Tick)) +
		"  " + badge
	return padRight(title, w)
}

// renderMap renders the zone grid + entity layer.
//
// Legacy renderer pulled grid dimensions from tick.Zone.{Width,Height}.
// state.Tick has no zone metadata, so we fall back to the same default the
// legacy code used when zone was empty (8x6) and grow it to fit any entity
// positions we see. The visual shape is unchanged.
func renderMap(tick state.Tick, w int) []string {
	gw, gh := 8, 6
	for _, e := range tick.Entities {
		if e.Position.X+1 > gw {
			gw = e.Position.X + 1
		}
		if e.Position.Y+1 > gh {
			gh = e.Position.Y + 1
		}
	}
	if tick.Position != nil {
		if tick.Position.X+1 > gw {
			gw = tick.Position.X + 1
		}
		if tick.Position.Y+1 > gh {
			gh = tick.Position.Y + 1
		}
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
	// Player position (if provided separately) overlays as @.
	if tick.Position != nil {
		x, y := tick.Position.X, tick.Position.Y
		if x >= 0 && y >= 0 && x < gw && y < gh {
			grid[y][x] = bold(yellow("@"))
		}
	}

	var lines []string
	header := bold(cyan(fmt.Sprintf(" Map: %s (%dx%d)", tick.ZoneID, gw, gh)))
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

// renderQuests draws the quest list, plus the run-complete banner when set.
//
// In the legacy renderer, completion data came from QuestCompletePayload
// (quest_name + final_score + steps_taken). In state.GameState, completion is
// stored as a boolean + FinalScore + FinalSteps with no quest name field, so
// we use a generic "Run Complete" label.
func renderQuests(s *state.GameState, w int) []string {
	_ = w // reserved for future right-padding; current callers wrap with newlines

	var lines []string
	lines = append(lines, bold(cyan(" Quests")))

	if s.RunComplete {
		lines = append(lines, green(fmt.Sprintf(
			"  ★ Run Complete  score:%d  steps:%d",
			s.FinalScore, s.FinalSteps,
		)))
	}

	if len(s.Tick.Quests) == 0 {
		if !s.RunComplete {
			lines = append(lines, dim("  (none)"))
		}
		return lines
	}

	for _, q := range s.Tick.Quests {
		// Derive completion: a quest is complete iff every objective is done.
		// (state.Quest has no top-level Complete flag — the legacy
		// payload's Quest.Complete is not represented in the new types.)
		complete := len(q.Objectives) > 0
		for _, obj := range q.Objectives {
			if !obj.Done {
				complete = false
				break
			}
		}

		status := dim("[ ]")
		name := q.Title
		if complete {
			status = green("[✓]")
			name = green(name)
		}
		lines = append(lines, fmt.Sprintf("  %s %s", status, name))
		for _, obj := range q.Objectives {
			sym := dim("  ○")
			desc := dim(obj.Description)
			if obj.Done {
				sym = green("  ✓")
				desc = green(obj.Description)
			}
			lines = append(lines, fmt.Sprintf("    %s %s", sym, desc))
		}
	}

	return lines
}

// padRight pads a string to width w (visual width — strips ANSI escapes
// before counting).
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
		case r == '\x1b':
			inEsc = true
		case inEsc && r == 'm':
			inEsc = false
		case !inEsc:
			count++
		}
	}
	return count
}
