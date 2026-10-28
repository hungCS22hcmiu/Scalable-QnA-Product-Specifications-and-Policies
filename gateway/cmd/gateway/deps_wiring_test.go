package main

import (
	"os"
	"strings"
	"testing"
)

// TestMainWiresDeps reads main.go as text, because main() has no seam a test can run: it opens Redis,
// dials the RAG service and listens. The failure it guards is silent. A gateway built without the
// dependency map registers nothing (httpapi treats a nil Deps as "off", so that existing tests still
// work), and then no purge can ever reach an entry it wrote -- invalidation completeness falls below
// 1 with no error anywhere.
//
// Comment lines are dropped first, so a needle that appears only in a comment does not count.
func TestMainWiresDeps(t *testing.T) {
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

	index("deps.New(")
	build := index("depMap := deps.New(")
	newHandler := index("httpapi.NewHandler(")
	assign := index("handler.Deps = depMap")
	if assign < newHandler {
		t.Fatalf("handler.Deps = depMap (at %d) comes before httpapi.NewHandler( (at %d): the handler does not exist yet", assign, newHandler)
	}
	if build > assign {
		t.Fatalf("depMap is built at %d, after it is assigned to the handler at %d", build, assign)
	}

	shutdown := index("srv.Shutdown(")
	closeMap := index("depMap.Close(")
	finish := index("finishRun(evalLog)")
	if !(shutdown < closeMap && closeMap < finish) {
		t.Fatalf("want srv.Shutdown( (%d) < depMap.Close( (%d) < finishRun(evalLog) (%d): the map must drain after the server stops taking requests and before the evaluation log closes",
			shutdown, closeMap, finish)
	}
}
