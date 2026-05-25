package sockconn

import (
	"os"
	"testing"
)

func TestResolvePath_PrefersSockEnv(t *testing.T) {
	os.Setenv("TAVERNBENCH_SOCK", "/tmp/x.sock")
	os.Setenv("TAVERNBENCH_TOKEN", "TOK")
	defer os.Unsetenv("TAVERNBENCH_SOCK")
	defer os.Unsetenv("TAVERNBENCH_TOKEN")

	got, err := ResolvePath("")
	if err != nil || got != "/tmp/x.sock" {
		t.Fatalf("got %q, err %v", got, err)
	}
}

func TestResolvePath_FallsBackToToken(t *testing.T) {
	os.Unsetenv("TAVERNBENCH_SOCK")
	os.Setenv("TAVERNBENCH_TOKEN", "TAVERN-FOO")
	defer os.Unsetenv("TAVERNBENCH_TOKEN")

	got, err := ResolvePath("")
	if err != nil {
		t.Fatal(err)
	}
	if got == "" {
		t.Fatal("got empty path")
	}
}

func TestResolvePath_NoneAvailableErrors(t *testing.T) {
	os.Unsetenv("TAVERNBENCH_SOCK")
	os.Unsetenv("TAVERNBENCH_TOKEN")
	_, err := ResolvePath("")
	if err == nil {
		t.Fatal("expected error")
	}
}
