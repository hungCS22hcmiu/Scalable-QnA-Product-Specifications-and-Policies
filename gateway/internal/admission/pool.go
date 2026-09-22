// Package admission bounds in-flight generations to what the memory envelope can hold, and sheds
// the rest rather than admitting work that would swap or OOM.
//
// This is the 60 %-weighted contribution's mechanism (proposal 6.1/6.2, ADR-022): the gateway is
// an active resource governor, not a proxy. A request that cannot be admitted is answered
// `503 busy, retry` -- a graceful-degradation event the scalability eval counts, never an error
// (interfaces.md A).
//
// architecture-guardrails.md: this package must be the SOLE place a permit is acquired, and no
// miss path may bypass it. httpapi has exactly one call site for that reason.
package admission

import (
	"context"
	"errors"
	"sync/atomic"
	"time"
)

// ErrShed is returned when the pool and its queue budget are both exhausted. It is distinct from
// a cancelled context: a shed is a decision this gateway made and must be counted, a cancellation
// is the client leaving and must not be.
var ErrShed = errors.New("admission: generation pool saturated")

// Pool is a counting semaphore with a bounded wait queue.
//
// Two bounds, not one. Permits alone would make an overloaded gateway block callers indefinitely,
// which converts an overload into a latency collapse instead of a visible shed -- and a run whose
// p99 exploded with no shed count is one where the load generator, not the gateway, decided the
// operating point.
type Pool struct {
	permits chan struct{}
	queue   chan struct{}
	depth   atomic.Int64
}

// New builds a pool of size permits with room for queueBudget waiters. A permits value of 0 or
// less disables admission control entirely and is logged by the caller as such -- a run without
// backpressure is a valid thing to measure, but never a thing to measure by accident.
func New(permits, queueBudget int) *Pool {
	if permits <= 0 {
		return &Pool{}
	}
	if queueBudget < 0 {
		queueBudget = 0
	}
	return &Pool{
		permits: make(chan struct{}, permits),
		queue:   make(chan struct{}, queueBudget),
	}
}

// Enabled reports whether this pool bounds anything.
func (p *Pool) Enabled() bool { return p.permits != nil }

// Permit is a held generation slot. Release exactly once, and always.
type Permit struct {
	pool *Pool
	once atomic.Bool

	// Waited and QueueDepth feed interfaces.md H's t_permit_wait_ms and permit_queue_depth.
	// Both are null in the log when no permit was requested, which is why they live here rather
	// than being zero values on the request record.
	Waited     time.Duration
	QueueDepth int
}

// Release returns the permit. Safe to call more than once; the second call is a no-op rather than
// a panic, because a double release would silently RAISE the pool's capacity and let the envelope
// be exceeded with no error anywhere.
func (p *Permit) Release() {
	if p == nil || p.pool == nil || !p.once.CompareAndSwap(false, true) {
		return
	}
	<-p.pool.permits
}

// Acquire takes a permit, waiting only if there is queue budget left.
//
// Returns ErrShed when both are exhausted, or ctx.Err() if the caller goes away while queued.
// When the pool is disabled it always admits, so a caller never needs to branch on Enabled.
func (p *Pool) Acquire(ctx context.Context) (*Permit, error) {
	if !p.Enabled() {
		return &Permit{}, nil
	}
	start := time.Now()

	// Fast path: a free permit is taken without ever touching the queue, so an unloaded gateway
	// pays nothing for the machinery.
	select {
	case p.permits <- struct{}{}:
		return &Permit{pool: p}, nil
	default:
	}

	select {
	case p.queue <- struct{}{}:
	default:
		return nil, ErrShed
	}
	depth := int(p.depth.Add(1))
	defer func() {
		p.depth.Add(-1)
		<-p.queue
	}()

	select {
	case p.permits <- struct{}{}:
		return &Permit{pool: p, Waited: time.Since(start), QueueDepth: depth}, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

// InFlight and Queued are for the startup banner and the evaluation log, not for decisions.
func (p *Pool) InFlight() int { return len(p.permits) }
func (p *Pool) Queued() int   { return int(p.depth.Load()) }
