package main

import (
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

func playCmd(args []string) {
	fs := flag.NewFlagSet("play", flag.ExitOnError)
	scenario := fs.String("scenario", "tavern_hall", "Scenario id")
	agent := fs.String("agent", "", "Optional agent command to spawn")
	host := fs.String("host", "127.0.0.1:4100", "Phoenix host")
	fs.Parse(args)

	tuiPath := findTUIBinary()
	cmd := exec.Command(tuiPath,
		"--mode=play",
		"--zone="+*scenario,
		"--host="+*host,
	)
	if *agent != "" {
		cmd.Args = append(cmd.Args, "--agent="+*agent)
	}
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		if ee, ok := err.(*exec.ExitError); ok {
			os.Exit(ee.ExitCode())
		}
		die(err)
	}
}

func findTUIBinary() string {
	// 1) env override
	if p := os.Getenv("TAVERNBENCH_TUI_BIN"); p != "" {
		return p
	}
	// 2) sibling of the CLI binary
	self, err := os.Executable()
	if err == nil {
		candidate := filepath.Join(filepath.Dir(self), "tavernbench-tui")
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}
	// 3) PATH lookup
	if p, err := exec.LookPath("tavernbench-tui"); err == nil {
		return p
	}
	fmt.Fprintln(os.Stderr, "tavernbench: cannot find tavernbench-tui binary on PATH")
	os.Exit(2)
	return ""
}
