package main

import (
	"errors"
	"net/http"
	"os"
	"strings"
	"testing"
)

// TestRunEndClean pins when the gateway may print runEndedLine, the only line rule 6 accepts from a
// gateway after `29da622` (interfaces.md §I). Each way to lose a record or a registration must make
// it false; a clean Shutdown with nothing lost must make it true.
func TestRunEndClean(t *testing.T) {
	ok := runEnd{ServeErr: http.ErrServerClosed}
	if !ok.clean() {
		t.Fatal("a Shutdown with nothing lost is not clean")
	}
	bad := errors.New("x")
	cases := map[string]func(*runEnd){
		"ListenAndServe failed (port in use)": func(e *runEnd) { e.ServeErr = bad },
		"ListenAndServe returned nil":         func(e *runEnd) { e.ServeErr = nil },
		"requests still in flight":            func(e *runEnd) { e.ShutdownErr = bad },
		"dependency map close failed":         func(e *runEnd) { e.DepCloseErr = bad },
		"registration dropped":                func(e *runEnd) { e.DepDropped = 1 },
		"registration write failed":           func(e *runEnd) { e.DepRegisterErrors = 1 },
		"purge call failed":                   func(e *runEnd) { e.DepPurgeErrors = 1 },
		"evaluation log close failed":         func(e *runEnd) { e.CloseErr = bad },
		"run incomplete":                      func(e *runEnd) { e.Verdict = bad },
	}
	for name, spoil := range cases {
		e := ok
		spoil(&e)
		if e.clean() {
			t.Errorf("%s: clean() = true, want false", name)
		}
	}
}

// TestMainPrintsRunEndedLast reads main.go as text, as TestMainWiresDeps does: main() has no seam a
// test can run. The line must come after the log is judged (finishRun and the INCOMPLETE exit), be
// guarded by clean(), and clean() must see Shutdown's error.
func TestMainPrintsRunEndedLast(t *testing.T) {
	raw, err := os.ReadFile("main.go")
	if err != nil {
		t.Fatal(err)
	}
	var code []string
	for _, line := range strings.Split(string(raw), "\n") {
		if strings.HasPrefix(strings.TrimSpace(line), "//") {
			continue
		}
		code = append(code, line)
	}
	src := strings.Join(code, "\n")
	index := func(needle string) int {
		t.Helper()
		i := strings.Index(src, needle)
		if i < 0 {
			t.Fatalf("main.go (comments dropped) has no %q", needle)
		}
		return i
	}

	shutdown := index("srv.Shutdown(")
	keep := index("shutdownErr = err")
	wait := index("<-shutdownDone")
	read := index("end.ShutdownErr = shutdownErr")
	finish := index("finishRun(evalLog)")
	fatal := index(`log.Fatalf("gateway: THIS RUN IS INCOMPLETE`)
	guard := index("if end.clean() {")
	line := index("runEndedLine)")
	if !(shutdown < keep && wait < read && read < finish && finish < fatal && fatal < guard && guard < line) {
		t.Fatalf("want srv.Shutdown( (%d) < shutdownErr = err (%d); <-shutdownDone (%d) < end.ShutdownErr (%d) "+
			"< finishRun (%d) < INCOMPLETE exit (%d) < if end.clean() (%d) < the runEndedLine print (%d)",
			shutdown, keep, wait, read, finish, fatal, guard, line)
	}
	if strings.Count(src, "runEndedLine)") != 1 {
		t.Fatal("runEndedLine is printed more than once: only the clean end may print it")
	}
}
