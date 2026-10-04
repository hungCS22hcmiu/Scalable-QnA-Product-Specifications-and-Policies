package coalesce

import (
	"errors"
	"sync"
	"sync/atomic"
	"testing"
)

// spinUntil busy-waits on a condition the other goroutine will make true. A sleep would make
// these tests either flaky or slow; the conditions here flip in microseconds.
func spinUntil(cond func() bool) {
	for !cond() {
	}
}

// THE property. Without it, N concurrent duplicates each run a generation, and the no-cache
// baseline's generation count becomes a function of the load generator's concurrency rather than
// of the workload's redundancy -- which would make every configuration comparison meaningless.
func TestConcurrentDuplicatesRunTheFunctionOnce(t *testing.T) {
	var g Group[string]
	var calls atomic.Int64
	release := make(chan struct{})

	const n = 32
	var wg sync.WaitGroup
	results := make([]string, n)
	var sharedCount atomic.Int64

	wg.Add(1)
	go func() {
		defer wg.Done()
		v, err, shared := g.Do("k", func() (string, error) {
			calls.Add(1)
			<-release
			return "answer", nil
		})
		if err != nil || shared {
			t.Errorf("leader: err=%v shared=%v", err, shared)
		}
		results[0] = v
	}()
	spinUntil(func() bool { return g.inflight() == 1 })

	for i := 1; i < n; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			v, err, shared := g.Do("k", func() (string, error) {
				calls.Add(1)
				return "SECOND EXECUTION", nil
			})
			if err != nil {
				t.Errorf("follower %d: %v", i, err)
			}
			results[i] = v
			if shared {
				sharedCount.Add(1)
			}
		}()
	}
	spinUntil(func() bool { return g.waiters("k") == n-1 })
	close(release)
	wg.Wait()

	if got := calls.Load(); got != 1 {
		t.Fatalf("fn ran %d times, want exactly 1 -- duplicates are not being collapsed", got)
	}
	if got := sharedCount.Load(); got != n-1 {
		t.Fatalf("shared reported for %d callers, want %d (everyone but the leader)", got, n-1)
	}
	for i, r := range results {
		if r != "answer" {
			t.Fatalf("caller %d got %q, want the leader's result", i, r)
		}
	}
}

// Distinct keys must not share. Collapsing two different questions onto one answer would be a
// false hit with no rule involved and no bucket in the evaluation's two-cause split.
func TestDifferentKeysDoNotShare(t *testing.T) {
	var g Group[string]
	var wg sync.WaitGroup
	got := make([]string, 2)
	for i, k := range []string{"a", "b"} {
		wg.Add(1)
		go func() {
			defer wg.Done()
			got[i], _, _ = g.Do(k, func() (string, error) { return k, nil })
		}()
	}
	wg.Wait()
	if got[0] != "a" || got[1] != "b" {
		t.Fatalf("keys crossed: %q, %q", got[0], got[1])
	}
}

// The key must be gone once the call completes. If it survived, the next wave of a repeated
// question would be served the first wave's result forever -- a permanent stale answer that no
// cache invalidation could reach, because it is not in the cache.
func TestKeyIsReleasedSoLaterCallersReRun(t *testing.T) {
	var g Group[int]
	calls := 0
	for range 3 {
		if _, _, shared := g.Do("k", func() (int, error) { calls++; return calls, nil }); shared {
			t.Fatal("a sequential caller was told it shared an in-flight call")
		}
	}
	if calls != 3 {
		t.Fatalf("fn ran %d times across three sequential calls, want 3", calls)
	}
	if g.inflight() != 0 {
		t.Fatal("a completed call is still registered")
	}
}

func TestErrorReachesEveryWaiter(t *testing.T) {
	var g Group[int]
	want := errors.New("generation failed")
	release := make(chan struct{})
	var wg sync.WaitGroup
	errs := make([]error, 8)

	wg.Add(1)
	go func() {
		defer wg.Done()
		_, errs[0], _ = g.Do("k", func() (int, error) { <-release; return 0, want })
	}()
	spinUntil(func() bool { return g.inflight() == 1 })
	for i := 1; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, errs[i], _ = g.Do("k", func() (int, error) { return 0, nil })
		}()
	}
	spinUntil(func() bool { return g.waiters("k") == 7 })
	close(release)
	wg.Wait()

	for i, err := range errs {
		if !errors.Is(err, want) {
			t.Fatalf("waiter %d got %v, want the leader's error", i, err)
		}
	}
}

// A panic must not reach followers as a zero value with a nil error -- they would serve it as a
// successful answer, which is exactly the silent-failure class this repo exists to avoid.
func TestPanicBecomesAnErrorForWaiters(t *testing.T) {
	var g Group[string]
	release := make(chan struct{})
	var wg sync.WaitGroup
	var followerVal string
	var followerErr error

	wg.Add(1)
	go func() {
		defer wg.Done()
		defer func() {
			if recover() == nil {
				t.Error("the panic did not reach the leader; it must still fail loudly")
			}
		}()
		_, _, _ = g.Do("k", func() (string, error) { <-release; panic("boom") })
	}()
	spinUntil(func() bool { return g.inflight() == 1 })

	wg.Add(1)
	go func() {
		defer wg.Done()
		v, err, shared := g.Do("k", func() (string, error) { return "SECOND EXECUTION", nil })
		if !shared {
			t.Error("the follower ran its own fn instead of waiting")
		}
		followerVal, followerErr = v, err
	}()
	spinUntil(func() bool { return g.waiters("k") == 1 })
	close(release)
	wg.Wait()

	if followerErr == nil {
		t.Fatalf("panicking leader handed the follower (%q, nil) -- it would serve a zero value", followerVal)
	}
}
