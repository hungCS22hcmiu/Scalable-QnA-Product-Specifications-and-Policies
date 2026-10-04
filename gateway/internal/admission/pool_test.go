package admission

import (
	"context"
	"errors"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func spinUntil(cond func() bool) {
	for !cond() {
	}
}

// The slot bound. If more than `permits` generations can be in flight at once, the surplus queues
// invisibly inside the model server, which serves only its fixed slots (ADR-003), and every shed
// rate then describes that hidden queue instead of the gateway.
func TestNeverAdmitsMoreThanPermits(t *testing.T) {
	const permits = 4
	p := New(permits, 64)

	var inFlight, peak atomic.Int64
	release := make(chan struct{})
	var wg sync.WaitGroup
	for range 32 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			permit, err := p.Acquire(context.Background())
			if err != nil {
				return
			}
			defer permit.Release()
			n := inFlight.Add(1)
			for {
				old := peak.Load()
				if n <= old || peak.CompareAndSwap(old, n) {
					break
				}
			}
			<-release
			inFlight.Add(-1)
		}()
	}
	spinUntil(func() bool { return inFlight.Load() == permits })
	close(release)
	wg.Wait()

	if got := peak.Load(); got > permits {
		t.Fatalf("%d generations were in flight at once, permits=%d", got, permits)
	}
}

// Shedding must happen rather than queueing without bound. An unbounded queue turns overload into
// a latency collapse with a zero shed count, which reads as "the system coped" in the results.
func TestShedsWhenPermitsAndQueueAreBothFull(t *testing.T) {
	p := New(1, 1)
	held, err := p.Acquire(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	defer held.Release()

	queued := make(chan struct{})
	go func() {
		close(queued)
		q, _ := p.Acquire(context.Background())
		q.Release()
	}()
	<-queued
	spinUntil(func() bool { return p.Queued() == 1 })

	if _, err := p.Acquire(context.Background()); !errors.Is(err, ErrShed) {
		t.Fatalf("third caller got %v, want ErrShed", err)
	}
}

// A client that disconnects while queued is NOT a shed. Counting it as one would inflate the
// graceful-degradation number with events the gateway did not cause.
func TestCancelledWaiterIsNotAShed(t *testing.T) {
	p := New(1, 4)
	held, _ := p.Acquire(context.Background())
	defer held.Release()

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { _, err := p.Acquire(ctx); done <- err }()
	spinUntil(func() bool { return p.Queued() == 1 })
	cancel()

	err := <-done
	if errors.Is(err, ErrShed) {
		t.Fatal("a cancelled waiter was reported as a shed")
	}
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("got %v, want context.Canceled", err)
	}
}

// A double release would silently RAISE capacity above the envelope, with no error anywhere --
// exactly the class of failure this package exists to prevent.
func TestDoubleReleaseDoesNotRaiseCapacity(t *testing.T) {
	p := New(1, 0)
	permit, _ := p.Acquire(context.Background())
	permit.Release()
	permit.Release()

	a, err := p.Acquire(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	defer a.Release()
	if _, err := p.Acquire(context.Background()); !errors.Is(err, ErrShed) {
		t.Fatalf("capacity leaked: a second permit was available, got %v", err)
	}
}

// permits <= 0 disables the pool. It must then admit everything rather than deadlock, so that
// "no backpressure" is a runnable configuration and not a hang.
func TestDisabledPoolAdmitsEverything(t *testing.T) {
	p := New(0, 0)
	if p.Enabled() {
		t.Fatal("New(0, ...) reported Enabled")
	}
	for range 100 {
		permit, err := p.Acquire(context.Background())
		if err != nil {
			t.Fatalf("disabled pool refused: %v", err)
		}
		permit.Release()
	}
}

func TestWaitedIsRecordedOnlyWhenTheCallerActuallyQueued(t *testing.T) {
	p := New(1, 4)
	fast, _ := p.Acquire(context.Background())
	if fast.Waited != 0 {
		t.Fatalf("uncontended acquire reported Waited=%v", fast.Waited)
	}

	done := make(chan *Permit, 1)
	go func() { permit, _ := p.Acquire(context.Background()); done <- permit }()
	spinUntil(func() bool { return p.Queued() == 1 })
	time.Sleep(2 * time.Millisecond) // make the wait measurably nonzero
	fast.Release()

	queuedPermit := <-done
	defer queuedPermit.Release()
	if queuedPermit.Waited == 0 {
		t.Fatal("a caller that queued reported Waited=0; t_permit_wait_ms would be wrong")
	}
	if queuedPermit.QueueDepth != 1 {
		t.Fatalf("QueueDepth = %d, want 1", queuedPermit.QueueDepth)
	}
}
