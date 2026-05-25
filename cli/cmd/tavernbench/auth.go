package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"golang.org/x/term"
)

func authCmd(args []string) {
	fs := flag.NewFlagSet("auth", flag.ExitOnError)
	key := fs.String("key", "", "API key (omit for hidden prompt)")
	fs.Parse(args)

	var apiKey string
	if *key != "" {
		apiKey = *key
	} else {
		fmt.Print("Paste API key (input hidden): ")
		b, err := term.ReadPassword(int(os.Stdin.Fd()))
		fmt.Println()
		if err != nil {
			// Fallback: visible read (e.g., when stdin is not a TTY).
			r := bufio.NewReader(os.Stdin)
			line, _ := r.ReadString('\n')
			b = []byte(strings.TrimSpace(line))
		}
		apiKey = strings.TrimSpace(string(b))
	}
	if apiKey == "" {
		fmt.Fprintln(os.Stderr, "tavernbench: no key entered")
		os.Exit(1)
	}
	home, _ := os.UserHomeDir()
	dir := filepath.Join(home, ".config", "tavernbench")
	os.MkdirAll(dir, 0o700)
	path := filepath.Join(dir, "config.toml")
	content := fmt.Sprintf(`api_key = "%s"`+"\n", apiKey)
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		die(err)
	}
	fmt.Printf("✓ Key saved to %s\n", path)
}
