package main

import (
	"fmt"

	"github.com/tavernbench/cli/internal/sockconn"
)

func observeCmd(args []string) {
	_ = args
	path, err := sockconn.ResolvePath("")
	if err != nil {
		die(err)
	}
	resp, err := sockconn.Send(path, map[string]any{"id": "1", "op": "observe"})
	if err != nil {
		die(err)
	}
	fmt.Println(string(resp))
}
