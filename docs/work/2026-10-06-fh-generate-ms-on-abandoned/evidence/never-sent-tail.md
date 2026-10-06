# The "RPC never left" tail — plan step 5 (record-only)

**Status: exploratory, not citable.** Taken on 2026-10-06 on the M1 MacBook Pro with
`kern.memorystatus_vm_pressure_level` = **1** (yellow) and other applications open, so it is not a
green-pressure run. It reads a unit fixture (the 1.2 harness: a real gRPC server on loopback, fakes for
Redis, the embedder and the model), not the gateway under k6.

## What was measured

`TestClientLeftBeforeTheRPCStillRecordsAnAttempt` (T3): the client left after Tier 1 with a free permit,
so `Acquire`'s fast path admitted it and `Answer` was called with a dead context. The server saw 0 RPCs
(`answerCalls()==0`), yet `t_generate_ms` is non-null. The test logs the value; 30 runs each.
Reproduce: `cd gateway && go test [-race] -count=30 -run TestClientLeftBeforeTheRPCStillRecordsAnAttempt -v ./internal/httpapi/`

## Result (`t_generate_ms`, ms, sorted, 30 runs)

| Build | min | median | max | runs ≥ 1 ms |
| :--- | ---: | ---: | ---: | ---: |
| without `-race` | 0.001 | ≈ 0.001–0.002 | 0.012 | **0 of 30** |
| with `-race` | 0.012 | ≈ 0.014 | 0.031 | **0 of 30** |

Every value is **at least 30× below the 1 ms default** threshold (the worst, 31 µs under the race
detector, is 32× below).

## What it does and does not show

- **It shows** the never-sent value is microseconds here, and that the race detector's overhead
  (≈ 10×) does not carry it near 1 ms. The pre-registered threshold has headroom against two of the
  failure modes ADR-006 names (a slow build, scheduler jitter in a quiet process).
- **It does not show** the tail under what the threshold must survive in a real run: co-hosted CPU
  contention (k6 and the embedder on the same cores), GC pauses in a busy gateway, a cancel landing
  during a lazy gRPC connect, or a memory-pressure episode. **That is why the pre-registered check
  counts ABANDONED values in [1 ms, 100 ms] and calls the split unresolved if the count is not
  negligible.** The first `RUN_ID` is the real reading.
- **It says nothing about the other side of the split:** that an RPC which reached `rag.server`
  and was cancelled returns in more than 1 ms. That is a property of the real server and a real
  network round trip, not of this fixture.

## Race detector

`go test -count=1 -race ./internal/httpapi/`: **ok**, on the tree with the fix. T1-T6 are new, so this is
the first race run over them; the field copy itself is on the leader's goroutine (`coalesce.go:72`), so
no new sharing is introduced.
