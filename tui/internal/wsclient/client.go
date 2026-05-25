// Package wsclient provides a minimal hand-rolled RFC 6455 WebSocket client
// and the Phoenix 5-tuple wire-protocol encoder used by the TavernBench TUI.
// Stdlib only — no third-party deps.
package wsclient

import (
	"bufio"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

// PhxMsg is the Phoenix Channels 5-tuple wire format:
//
//	[join_ref, ref, topic, event, payload]
type PhxMsg [5]json.RawMessage

// EncodeMsg marshals a Phoenix Channels 5-tuple into JSON.
func EncodeMsg(joinRef, ref interface{}, topic, event string, payload interface{}) ([]byte, error) {
	msg := []interface{}{joinRef, ref, topic, event, payload}
	return json.Marshal(msg)
}

// Conn is a minimal RFC 6455 WebSocket client connection.
type Conn struct {
	conn net.Conn
	mu   sync.Mutex
}

// Connect dials the given ws:// URL and completes the RFC 6455 handshake.
func Connect(rawURL string) (*Conn, error) {
	u, err := url.Parse(rawURL)
	if err != nil {
		return nil, err
	}
	host := u.Host
	if !strings.Contains(host, ":") {
		host += ":80"
	}
	conn, err := net.DialTimeout("tcp", host, 10*time.Second)
	if err != nil {
		return nil, err
	}

	key := wsKey()
	path := u.Path
	if u.RawQuery != "" {
		path += "?" + u.RawQuery
	}
	req := fmt.Sprintf(
		"GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n",
		path, u.Host, key,
	)
	if _, err := conn.Write([]byte(req)); err != nil {
		conn.Close()
		return nil, err
	}
	resp, err := http.ReadResponse(bufio.NewReader(conn), nil)
	if err != nil {
		conn.Close()
		return nil, err
	}
	resp.Body.Close()
	if resp.StatusCode != 101 {
		conn.Close()
		return nil, fmt.Errorf("unexpected status %d", resp.StatusCode)
	}
	return &Conn{conn: conn}, nil
}

func wsKey() string {
	b := make([]byte, 16)
	rand.Read(b)
	return base64.StdEncoding.EncodeToString(b)
}

// WriteText sends a text frame (client-to-server, masked as required by RFC 6455).
func (w *Conn) WriteText(data []byte) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	mask := make([]byte, 4)
	rand.Read(mask)

	header := []byte{0x81} // FIN + opcode text
	l := len(data)
	switch {
	case l < 126:
		header = append(header, byte(l|0x80))
	case l < 65536:
		header = append(header, 0xFE, byte(l>>8), byte(l))
	default:
		header = append(header, 0xFF,
			byte(l>>56), byte(l>>48), byte(l>>40), byte(l>>32),
			byte(l>>24), byte(l>>16), byte(l>>8), byte(l))
	}
	header = append(header, mask...)

	masked := make([]byte, l)
	for i, b := range data {
		masked[i] = b ^ mask[i%4]
	}
	_, err := w.conn.Write(append(header, masked...))
	return err
}

// ReadMsg reads one WebSocket frame and returns its payload (text frames only).
func (w *Conn) ReadMsg() ([]byte, error) {
	hdr := make([]byte, 2)
	if _, err := readFull(w.conn, hdr); err != nil {
		return nil, err
	}
	// opcode
	opcode := hdr[0] & 0x0F
	// handle ping/close
	if opcode == 0x8 { // close
		return nil, fmt.Errorf("server closed connection")
	}

	masked := hdr[1]&0x80 != 0
	payLen := int(hdr[1] & 0x7F)
	switch payLen {
	case 126:
		ext := make([]byte, 2)
		readFull(w.conn, ext)
		payLen = int(ext[0])<<8 | int(ext[1])
	case 127:
		ext := make([]byte, 8)
		readFull(w.conn, ext)
		payLen = 0
		for _, b := range ext {
			payLen = payLen<<8 | int(b)
		}
	}

	var maskKey []byte
	if masked {
		maskKey = make([]byte, 4)
		readFull(w.conn, maskKey)
	}

	payload := make([]byte, payLen)
	readFull(w.conn, payload)

	if masked {
		for i := range payload {
			payload[i] ^= maskKey[i%4]
		}
	}

	// ignore non-text frames silently
	if opcode != 0x1 && opcode != 0x0 {
		return nil, nil
	}
	return payload, nil
}

// Close closes the underlying TCP connection.
func (w *Conn) Close() error {
	return w.conn.Close()
}

func readFull(conn net.Conn, buf []byte) (int, error) {
	total := 0
	for total < len(buf) {
		n, err := conn.Read(buf[total:])
		total += n
		if err != nil {
			return total, err
		}
	}
	return total, nil
}
