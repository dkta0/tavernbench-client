package sockconn

import (
	"bufio"
	"encoding/json"
	"errors"
	"net"
	"os"
	"path/filepath"
)

func ResolvePath(explicitToken string) (string, error) {
	if p := os.Getenv("TAVERNBENCH_SOCK"); p != "" {
		return p, nil
	}
	token := explicitToken
	if token == "" {
		token = os.Getenv("TAVERNBENCH_TOKEN")
	}
	if token != "" {
		base := os.Getenv("XDG_RUNTIME_DIR")
		if base == "" {
			base = "/tmp"
		}
		return filepath.Join(base, "tavernbench", token+".sock"), nil
	}
	return "", errors.New("no active run (is the TUI running? Set TAVERNBENCH_TOKEN or pass --token)")
}

func Send(path string, req any) (json.RawMessage, error) {
	conn, err := net.Dial("unix", path)
	if err != nil {
		return nil, err
	}
	defer conn.Close()
	raw, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}
	conn.Write(append(raw, '\n'))
	return bufio.NewReader(conn).ReadBytes('\n')
}
