package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/tavernbench/cli/internal/sockconn"
)

func actCmd(args []string) {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "usage: tavernbench act VERB [ARGS...]")
		os.Exit(2)
	}
	verb := args[0]
	rest := args[1:]

	path, err := sockconn.ResolvePath("")
	if err != nil {
		die(err)
	}

	payload := map[string]any{"id": "1", "op": "act", "verb": verb}
	args2 := buildActionArgs(verb, rest)
	if args2 != nil {
		payload["args"] = args2
	}
	resp, err := sockconn.Send(path, payload)
	if err != nil {
		die(err)
	}
	fmt.Println(string(resp))
}

func buildActionArgs(verb string, rest []string) map[string]any {
	if len(rest) == 0 {
		return nil
	}
	switch verb {
	case "move":
		return map[string]any{"direction": rest[0]}
	case "use":
		joined := strings.Join(rest, " ")
		parts := strings.SplitN(joined, " on ", 2)
		if len(parts) == 2 {
			return map[string]any{"item": parts[0], "target": parts[1]}
		}
		return map[string]any{"item": parts[0]}
	case "reply":
		return map[string]any{"choice": rest[0]}
	default:
		return map[string]any{"target": rest[0]}
	}
}
