// Package coalesce collapses concurrent duplicate work onto a single execution.
//
// Why the gateway needs it: N identical questions arriving together are N Tier-1 misses, and
// without coalescing each one takes a generation permit and runs the LLM. On a machine whose
// whole thesis is that generation is the scarce resource, that is the worst possible way to spend
// it -- and it also corrupts the measurement, because the no-cache baseline's generation count
// then depends on the load generator's concurrency rather than on the workload's redundancy.
//
// Hand-rolled rather than golang.org/x/sync/singleflight: a new dependency requires sign-off
// for a new dependency, and the shape is forty lines.
package coalesce

import (
	"fmt"
	"sync"
)

// Group runs one function per key at a time. The zero value is ready to use.
type Group[T any] struct {
	mu sync.Mutex
	m  map[string]*call[T]
}

type call[T any] struct {
	done chan struct{}
	val  T
	err  error

	// waiting counts callers that joined this execution instead of starting their own. It is
	// guarded by Group.mu, and it is the raw signal for "generations avoided by coalescing" --
	// a quantity distinct from cache hits and not derivable from them.
	waiting int
}

// Do runs fn for key, or waits for an in-flight call with the same key and returns its result.
// shared reports whether this caller waited on someone else's execution rather than running fn --
// it is what lets a run count generations avoided by coalescing separately from cache hits.
//
// ⚠️ fn runs under the LEADER's context, so a leader that is cancelled fails every follower.
// This matches golang.org/x/sync/singleflight and is the reason to keep the shared work short of
// anything a client timeout should not abort. Followers do not re-elect a new leader.
func (g *Group[T]) Do(key string, fn func() (T, error)) (val T, err error, shared bool) {
	g.mu.Lock()
	if c, ok := g.m[key]; ok {
		c.waiting++
		g.mu.Unlock()
		<-c.done
		return c.val, c.err, true
	}
	c := &call[T]{done: make(chan struct{})}
	if g.m == nil {
		g.m = make(map[string]*call[T])
	}
	g.m[key] = c
	g.mu.Unlock()

	// The key is removed BEFORE the waiters are released. Releasing first would let a waiter
	// wake, issue the same key, find the finished call still in the map and block on a channel
	// that is already closed -- returning a stale result forever after.
	defer func() {
		// A panic in fn must not hand every follower a zero value with a nil error -- they would
		// serve it as a successful answer. Convert it to an error for them, then re-panic so the
		// leader's own request still fails loudly.
		if r := recover(); r != nil {
			c.err = fmt.Errorf("coalesce: shared call panicked: %v", r)
			g.release(key, c)
			panic(r)
		}
		g.release(key, c)
	}()

	c.val, c.err = fn()
	return c.val, c.err, false
}

// release removes the key BEFORE waking the waiters. Waking first would let a waiter re-issue the
// same key, find the finished call still in the map, and block on a channel that is already
// closed -- returning that one stale result to every future caller of the key.
func (g *Group[T]) release(key string, c *call[T]) {
	g.mu.Lock()
	delete(g.m, key)
	g.mu.Unlock()
	close(c.done)
}

// inflight reports how many keys are currently executing. Test seam: it is what lets a test wait
// for the leader to be registered rather than sleep and hope.
func (g *Group[T]) inflight() int {
	g.mu.Lock()
	defer g.mu.Unlock()
	return len(g.m)
}

// Waiters reports how many callers are blocked on key's in-flight call. A test seam for packages
// that coalesce through a Group (httpapi's coalescing test); never call it on a request path,
// since it takes the group's lock.
func (g *Group[T]) Waiters(key string) int { return g.waiters(key) }

// waiters reports how many callers are blocked on key. Test seam, same reason.
func (g *Group[T]) waiters(key string) int {
	g.mu.Lock()
	defer g.mu.Unlock()
	if c, ok := g.m[key]; ok {
		return c.waiting
	}
	return 0
}
