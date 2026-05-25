package wsclient

import (
	"encoding/json"
	"testing"
)

func TestEncodeMsg_ShapesPhoenixFiveTuple(t *testing.T) {
	raw, err := EncodeMsg("1", "r1", "zone:t", "action", map[string]any{"a": "b"})
	if err != nil {
		t.Fatal(err)
	}
	var parsed []json.RawMessage
	if err := json.Unmarshal(raw, &parsed); err != nil {
		t.Fatal(err)
	}
	if len(parsed) != 5 {
		t.Fatalf("expected 5-element message, got %d", len(parsed))
	}
}

func TestWSKey_IsBase64_24Chars(t *testing.T) {
	k := wsKey()
	if len(k) != 24 { // base64 of 16 bytes is 24 chars
		t.Fatalf("unexpected key length: %d", len(k))
	}
}
