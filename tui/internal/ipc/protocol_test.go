package ipc

import (
	"encoding/json"
	"testing"
)

func TestRequestRoundtrip(t *testing.T) {
	req := Request{ID: "abc", Op: OpAct, Verb: "move", Args: map[string]any{"direction": "north"}}
	b, err := json.Marshal(req)
	if err != nil {
		t.Fatal(err)
	}
	var back Request
	if err := json.Unmarshal(b, &back); err != nil {
		t.Fatal(err)
	}
	if back.ID != "abc" || back.Op != OpAct || back.Verb != "move" {
		t.Fatalf("roundtrip lost data: %+v", back)
	}
}

func TestResponseErrorShape(t *testing.T) {
	r := Response{ID: "abc", OK: false, Error: &ErrorBody{Code: "bad_request", Message: "x"}}
	b, _ := json.Marshal(r)
	if !contains(b, []byte(`"code":"bad_request"`)) {
		t.Fatalf("error body not serialized: %s", b)
	}
}

func contains(haystack, needle []byte) bool {
	for i := 0; i+len(needle) <= len(haystack); i++ {
		match := true
		for j := range needle {
			if haystack[i+j] != needle[j] {
				match = false
				break
			}
		}
		if match {
			return true
		}
	}
	return false
}
