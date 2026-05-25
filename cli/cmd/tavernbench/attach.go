package main

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/tavernbench/cli/internal/sockconn"
)

func attachCmd(args []string) {
	if len(args) < 1 {
		fmt.Fprintln(os.Stderr, "usage: tavernbench attach TOKEN")
		os.Exit(2)
	}
	token := args[0]
	os.Setenv("TAVERNBENCH_TOKEN", token)
	path, err := sockconn.ResolvePath(token)
	if err != nil {
		die(err)
	}
	name := os.Getenv("TAVERNBENCH_AGENT_NAME")
	if name == "" {
		name = filepath.Base(os.Args[0])
	}
	resp, err := sockconn.Send(path, map[string]any{"id": "1", "op": "attach", "name": name})
	if err != nil {
		die(err)
	}
	fmt.Println(string(resp))
}

func die(err error) {
	fmt.Fprintln(os.Stderr, "tavernbench: "+err.Error())
	os.Exit(1)
}
