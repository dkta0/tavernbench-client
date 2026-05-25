package httpapi

import (
	"io"
	"net/http"
	"os"
)

func DefaultHost() string {
	if h := os.Getenv("TAVERNBENCH_HOST"); h != "" {
		return h
	}
	return "http://127.0.0.1:4100"
}

func Get(path string) ([]byte, error) {
	resp, err := http.Get(DefaultHost() + path)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	return io.ReadAll(resp.Body)
}
