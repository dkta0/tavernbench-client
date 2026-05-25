package ipc

import (
	"bufio"
	"context"
	"encoding/json"
	"net"
	"os"
	"path/filepath"
	"sync"
)

type Handler interface {
	HandleRequest(ctx context.Context, req Request) Response
}

type Server struct {
	handler    Handler
	queueDepth int
	mu         sync.Mutex
	queue      chan struct{}
	listener   net.Listener
}

func NewServer(h Handler, queueDepth int) *Server {
	return &Server{
		handler:    h,
		queueDepth: queueDepth,
		queue:      make(chan struct{}, queueDepth),
	}
}

// Listen binds to the unix socket path. The caller is responsible for choosing
// a token-keyed path and ensuring 0600 permissions. Replaces a stale socket file.
func (s *Server) Listen(socketPath string) error {
	if err := os.MkdirAll(filepath.Dir(socketPath), 0o700); err != nil {
		return err
	}
	if _, err := os.Stat(socketPath); err == nil {
		// Try to connect; if no listener, remove and continue.
		c, err := net.Dial("unix", socketPath)
		if err != nil {
			_ = os.Remove(socketPath)
		} else {
			c.Close()
			return os.ErrExist
		}
	}
	l, err := net.Listen("unix", socketPath)
	if err != nil {
		return err
	}
	if err := os.Chmod(socketPath, 0o600); err != nil {
		l.Close()
		return err
	}
	s.listener = l
	return nil
}

func (s *Server) Accept(ctx context.Context) {
	for {
		conn, err := s.listener.Accept()
		if err != nil {
			return
		}
		go s.HandleConn(conn)
	}
}

func (s *Server) HandleConn(conn net.Conn) {
	defer conn.Close()
	reader := bufio.NewReader(conn)
	line, err := reader.ReadBytes('\n')
	if err != nil {
		return
	}

	var req Request
	if err := json.Unmarshal(line, &req); err != nil {
		s.writeResp(conn, Response{OK: false, Error: &ErrorBody{Code: "bad_request", Message: err.Error()}})
		return
	}

	select {
	case s.queue <- struct{}{}:
		defer func() { <-s.queue }()
	default:
		s.writeResp(conn, Response{ID: req.ID, OK: false, Error: &ErrorBody{Code: "action_in_flight", Message: "queue full"}})
		return
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	resp := s.handler.HandleRequest(context.Background(), req)
	s.writeResp(conn, resp)
}

func (s *Server) writeResp(conn net.Conn, r Response) {
	b, _ := json.Marshal(r)
	conn.Write(append(b, '\n'))
}

func (s *Server) Close() error {
	if s.listener != nil {
		return s.listener.Close()
	}
	return nil
}
