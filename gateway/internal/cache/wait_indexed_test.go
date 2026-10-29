package cache

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
)

// waitIndexed decides when the gateway may start serving. These tests drive it with a fake FT.INFO,
// so the decision itself is pinned without Redis: complete means Indexing == 0 AND
// PercentIndexed >= 1, and anything else must end in a loud error, never in a quiet "ready".

func TestWaitIndexedReturnsWhenComplete(t *testing.T) {
	calls := 0
	info := func(context.Context) (redis.FTInfoResult, error) {
		calls++
		if calls < 3 {
			return redis.FTInfoResult{Indexing: 1, PercentIndexed: 0.5, NumDocs: calls * 100}, nil
		}
		return redis.FTInfoResult{Indexing: 0, PercentIndexed: 1, NumDocs: 1000}, nil
	}
	if err := waitIndexed(context.Background(), info, 5*time.Second, time.Millisecond); err != nil {
		t.Fatalf("waitIndexed: %v", err)
	}
	if calls != 3 {
		t.Fatalf("FT.INFO was read %d times, want 3: it must keep polling while Indexing is 1, and stop at the first complete answer", calls)
	}
}

func TestWaitIndexedTimesOut(t *testing.T) {
	info := func(context.Context) (redis.FTInfoResult, error) {
		return redis.FTInfoResult{Indexing: 1, PercentIndexed: 0.4, NumDocs: 7}, nil
	}
	const timeout = 60 * time.Millisecond
	start := time.Now()
	err := waitIndexed(context.Background(), info, timeout, 5*time.Millisecond)
	elapsed := time.Since(start)
	if err == nil {
		t.Fatal("a scan that never finishes returned success")
	}
	if elapsed < timeout {
		t.Fatalf("returned after %s, before the %s timeout", elapsed, timeout)
	}
	for _, want := range []string{"indexing=1", "percent_indexed=0.4", "num_docs=7"} {
		if !strings.Contains(err.Error(), want) {
			t.Errorf("the error should name the last values (%q), got: %v", want, err)
		}
	}
}

// Indexing 0 next to PercentIndexed 0 is what a misread FT.INFO looks like (a field that was not
// parsed). It must not count as ready.
func TestWaitIndexedIsNotFooledByZeroValues(t *testing.T) {
	info := func(context.Context) (redis.FTInfoResult, error) {
		return redis.FTInfoResult{Indexing: 0, PercentIndexed: 0, NumDocs: 0}, nil
	}
	const timeout = 40 * time.Millisecond
	start := time.Now()
	err := waitIndexed(context.Background(), info, timeout, 5*time.Millisecond)
	if err == nil {
		t.Fatal("zero Indexing with zero PercentIndexed was accepted as a complete index")
	}
	if elapsed := time.Since(start); elapsed < timeout {
		t.Fatalf("returned after %s, before the %s timeout: it must have waited, not given up on the first read", elapsed, timeout)
	}
}

func TestWaitIndexedReturnsReadErrors(t *testing.T) {
	boom := errors.New("connection refused")
	calls := 0
	info := func(context.Context) (redis.FTInfoResult, error) {
		calls++
		return redis.FTInfoResult{}, boom
	}
	err := waitIndexed(context.Background(), info, 5*time.Second, time.Millisecond)
	if !errors.Is(err, boom) {
		t.Fatalf("waitIndexed returned %v, want an error wrapping the read error", err)
	}
	if calls != 1 {
		t.Fatalf("FT.INFO was read %d times after a read error, want 1: a read error is not retried", calls)
	}
}
