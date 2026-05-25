package ipc

type Op string

const (
	OpAttach  Op = "attach"
	OpAct     Op = "act"
	OpObserve Op = "observe"
	OpAbort   Op = "abort"
)

type Request struct {
	ID   string         `json:"id"`
	Op   Op             `json:"op"`
	Name string         `json:"name,omitempty"` // for attach
	Verb string         `json:"verb,omitempty"` // for act
	Args map[string]any `json:"args,omitempty"`
}

type ErrorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type Response struct {
	ID          string         `json:"id"`
	OK          bool           `json:"ok"`
	Observation map[string]any `json:"observation,omitempty"`
	Events      []any          `json:"events,omitempty"`
	RunComplete bool           `json:"run_complete,omitempty"`
	FinalResult map[string]any `json:"final_result,omitempty"`
	Error       *ErrorBody     `json:"error,omitempty"`
}
