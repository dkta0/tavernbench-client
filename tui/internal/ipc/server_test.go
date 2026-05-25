package ipc

import (
	"bufio"
	"context"
	"encoding/json"
	"net"
	"testing"
	"time"
)

type stubHandler struct{}

func (stubHandler) HandleRequest(ctx context.Context, req Request) Response {
	return Response{ID: req.ID, OK: true}
}

func TestServerHandlesOneRequest(t *testing.T) {
	a, b := net.Pipe()
	defer a.Close()
	defer b.Close()

	s := NewServer(stubHandler{}, 4)
	go s.HandleConn(b)

	req := Request{ID: "x", Op: OpObserve}
	payload, _ := json.Marshal(req)
	a.Write(append(payload, '\n'))

	a.SetReadDeadline(time.Now().Add(1 * time.Second))
	line, err := bufio.NewReader(a).ReadBytes('\n')
	if err != nil {
		t.Fatal(err)
	}
	var resp Response
	if err := json.Unmarshal(line, &resp); err != nil {
		t.Fatal(err)
	}
	if resp.ID != "x" || !resp.OK {
		t.Fatalf("bad response: %+v", resp)
	}
}

func TestServerRejectsBadJSON(t *testing.T) {
	a, b := net.Pipe()
	defer a.Close()
	defer b.Close()

	s := NewServer(stubHandler{}, 4)
	go s.HandleConn(b)

	a.Write([]byte("{not json}\n"))

	a.SetReadDeadline(time.Now().Add(1 * time.Second))
	line, err := bufio.NewReader(a).ReadBytes('\n')
	if err != nil {
		t.Fatal(err)
	}
	var resp Response
	json.Unmarshal(line, &resp)
	if resp.OK || resp.Error == nil || resp.Error.Code != "bad_request" {
		t.Fatalf("expected bad_request error: %+v", resp)
	}
}
