package state

func Apply(s *GameState, t Tick) {
	s.Tick = t
}

func Attach(s *GameState, name string) {
	s.AgentState = AgentAttached
	s.AgentName = name
}

func Detach(s *GameState) {
	s.AgentState = AgentDetached
	s.AgentName = ""
}

func Complete(s *GameState, score, steps int, serverRunID string) {
	s.RunComplete = true
	s.FinalScore = score
	s.FinalSteps = steps
	s.ServerRunID = serverRunID
}
