package main

import (
	"fmt"

	"github.com/tavernbench/cli/internal/httpapi"
)

func scenariosCmd(args []string) {
	_ = args
	body, err := httpapi.Get("/api/scenarios")
	if err != nil {
		die(err)
	}
	fmt.Println(string(body))
}
