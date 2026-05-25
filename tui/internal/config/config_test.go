package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestReadAPIKey_ParsesTOMLLine(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "config.toml")
	os.WriteFile(path, []byte(`api_key = "abc123"`+"\n"), 0o600)

	k, err := ReadAPIKeyFrom(path)
	if err != nil {
		t.Fatal(err)
	}
	if k != "abc123" {
		t.Fatalf("got %q", k)
	}
}

func TestReadAPIKey_MissingFile(t *testing.T) {
	_, err := ReadAPIKeyFrom("/nonexistent/path/config.toml")
	if err == nil {
		t.Fatal("expected error")
	}
}
