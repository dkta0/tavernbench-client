package agentproc

import (
	"bufio"
	"io"
	"os"
	"os/exec"
	"sync"
	"syscall"
	"time"
)

const ringCap = 1000

type Process struct {
	cmd  *exec.Cmd
	ring *ring
}

func Spawn(argv []string, extraEnv []string) (*Process, error) {
	cmd := exec.Command(argv[0], argv[1:]...)
	cmd.Env = append(os.Environ(), extraEnv...)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return nil, err
	}
	if err := cmd.Start(); err != nil {
		return nil, err
	}

	p := &Process{cmd: cmd, ring: newRing(ringCap)}
	go p.pump(stdout)
	go p.pump(stderr)
	return p, nil
}

func (p *Process) pump(r io.Reader) {
	s := bufio.NewScanner(r)
	for s.Scan() {
		p.ring.push(s.Text())
	}
}

func (p *Process) Lines() []string {
	return p.ring.lines()
}

// Stop sends SIGTERM to the process group, waits 3s, then SIGKILL.
func (p *Process) Stop() {
	if p.cmd.Process == nil {
		return
	}
	pgid, err := syscall.Getpgid(p.cmd.Process.Pid)
	if err == nil {
		syscall.Kill(-pgid, syscall.SIGTERM)
	} else {
		p.cmd.Process.Signal(syscall.SIGTERM)
	}
	done := make(chan struct{})
	go func() { p.cmd.Wait(); close(done) }()
	select {
	case <-done:
	case <-time.After(3 * time.Second):
		if err == nil {
			syscall.Kill(-pgid, syscall.SIGKILL)
		} else {
			p.cmd.Process.Kill()
		}
		<-done
	}
}

type ring struct {
	mu    sync.Mutex
	buf   []string
	start int
	n     int
	cap   int
}

func newRing(cap int) *ring {
	return &ring{buf: make([]string, cap), cap: cap}
}

func (r *ring) push(line string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.n < r.cap {
		r.buf[(r.start+r.n)%r.cap] = line
		r.n++
	} else {
		r.buf[r.start] = line
		r.start = (r.start + 1) % r.cap
	}
}

func (r *ring) lines() []string {
	r.mu.Lock()
	defer r.mu.Unlock()
	out := make([]string, r.n)
	for i := 0; i < r.n; i++ {
		out[i] = r.buf[(r.start+i)%r.cap]
	}
	return out
}
