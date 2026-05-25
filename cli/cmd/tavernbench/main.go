package main

import (
	"fmt"
	"os"
)

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	switch os.Args[1] {
	case "attach":
		attachCmd(os.Args[2:])
	case "act":
		actCmd(os.Args[2:])
	case "observe":
		observeCmd(os.Args[2:])
	case "scenarios":
		scenariosCmd(os.Args[2:])
	case "leaderboard":
		leaderboardCmd(os.Args[2:])
	case "play":
		playCmd(os.Args[2:])
	case "auth":
		authCmd(os.Args[2:])
	case "doctor":
		doctorCmd(os.Args[2:])
	case "-h", "--help", "help":
		usage()
	default:
		fmt.Fprintf(os.Stderr, "tavernbench: unknown subcommand %q\n", os.Args[1])
		usage()
		os.Exit(2)
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, `tavernbench — agent benchmarking arena

Usage:
  tavernbench play [--scenario X] [--agent CMD]   Launch TUI
  tavernbench attach TOKEN                         Attach as the active agent
  tavernbench act VERB [ARGS...]                   Send an action
  tavernbench observe                              Print current observation
  tavernbench scenarios                            List scenarios (HTTP)
  tavernbench leaderboard --scenario X             Show leaderboard (HTTP)
  tavernbench auth [--key K]                       Store API key
  tavernbench doctor [--fix]                       Pre-flight checks`)
}
