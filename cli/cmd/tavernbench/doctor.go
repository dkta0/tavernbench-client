package main

import (
	"flag"
	"fmt"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"time"
)

func doctorCmd(args []string) {
	fs := flag.NewFlagSet("doctor", flag.ExitOnError)
	_ = fs.Bool("fix", false, "Reserved for future auto-repair")
	fs.Parse(args)

	home, _ := os.UserHomeDir()
	cfg := filepath.Join(home, ".config", "tavernbench", "config.toml")

	fmt.Print("checking config.toml... ")
	if _, err := os.Stat(cfg); err != nil {
		fmt.Println("MISSING — run `tavernbench auth`")
		os.Exit(1)
	}
	fmt.Println("ok")

	fmt.Print("checking server reachability... ")
	client := &http.Client{Timeout: 2 * time.Second}
	resp, err := client.Get("http://127.0.0.1:4100/health")
	if err != nil || resp.StatusCode != 200 {
		fmt.Println("UNREACHABLE")
		os.Exit(1)
	}
	resp.Body.Close()
	fmt.Println("ok")

	fmt.Print("checking for active TUI socket... ")
	base := os.Getenv("XDG_RUNTIME_DIR")
	if base == "" {
		base = "/tmp"
	}
	entries, _ := os.ReadDir(filepath.Join(base, "tavernbench"))
	found := 0
	for _, e := range entries {
		if filepath.Ext(e.Name()) == ".sock" {
			sock := filepath.Join(base, "tavernbench", e.Name())
			c, err := net.DialTimeout("unix", sock, 200*time.Millisecond)
			if err == nil {
				c.Close()
				found++
			}
		}
	}
	fmt.Printf("%d active\n", found)
}
