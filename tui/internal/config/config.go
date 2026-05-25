package config

import (
	"bufio"
	"errors"
	"os"
	"path/filepath"
	"regexp"
)

var keyRe = regexp.MustCompile(`^\s*api_key\s*=\s*"([^"]+)"\s*$`)

func DefaultPath() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".config", "tavernbench", "config.toml")
}

func ReadAPIKey() (string, error) {
	return ReadAPIKeyFrom(DefaultPath())
}

func ReadAPIKeyFrom(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	s := bufio.NewScanner(f)
	for s.Scan() {
		if m := keyRe.FindStringSubmatch(s.Text()); m != nil {
			return m[1], nil
		}
	}
	return "", errors.New("api_key not found in " + path)
}
