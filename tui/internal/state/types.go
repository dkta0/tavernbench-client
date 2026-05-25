package state

type Pos struct {
	X int `json:"x"`
	Y int `json:"y"`
}

type Entity struct {
	ID       string `json:"id"`
	Type     string `json:"type"`
	Position Pos    `json:"position"`
	Display  string `json:"display,omitempty"`
}

type Quest struct {
	ID         string `json:"id"`
	Title      string `json:"title"`
	Objectives []struct {
		Description string `json:"description"`
		Done        bool   `json:"done"`
	} `json:"objectives"`
}

type Tick struct {
	Tick     int      `json:"tick"`
	ZoneID   string   `json:"zone_id"`
	Position *Pos     `json:"position"`
	Entities []Entity `json:"entities"`
	Quests   []Quest  `json:"quest_log"`
	Score    int      `json:"score"`
	Steps    int      `json:"steps"`
}

type AgentState int

const (
	AgentDetached AgentState = iota
	AgentAttached
)

type GameState struct {
	Tick        Tick
	AgentState  AgentState
	AgentName   string
	RunComplete bool
	FinalScore  int
	FinalSteps  int
	ServerRunID string
	LogLines    []string
}
