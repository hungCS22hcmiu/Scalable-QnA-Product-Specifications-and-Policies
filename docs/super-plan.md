# Super Plan — execution to submission

**Status:** in force · **Created:** 2026-09-21 · **Revised:** 2026-10-04
**Companion to:** `contracts/requirements.md` (what must be true), `decisions.md` (why),
`Final_Proposal.md` §12 (drop order) and §13 (deliverables).

This file owns **execution**. It is derived from the critical path through the codebase as it
actually stands, not from the phase order that predated the code — see "Why the phases moved".

---

## What this document owns, and what it must never restate

Several documents used to describe what to do next at once. One plan with four sources is how a
plan drifts, so ownership is split explicitly:

| Owner | Owns |
| :--- | :--- |
| **`super-plan.md`** (this file) | **Execution.** The ordered items, what they discharge, what unblocks them, and what "done" means for each |
| `Final_Proposal.md` §12 | **Drop order under pressure.** Never restated here — many documents cite §12, and a second copy is exactly what would drift when schedule pressure arrives |
| `Final_Proposal.md` §13 | **Deliverables.** Never restated here |
| `contracts/requirements.md` | **What must be true.** Items cite `FR-xx` / `NFR-xx` / `RR-xx`; they do not re-argue them |
| `decisions.md` | **Why.** Items name what they rest on; they do not re-argue it |

**The week-based schedule this replaced was deleted on 2026-09-22.** Nothing in this file refers
to it. Two sections it carried — the **Risk Register** and the **Learning Path** — have no home
and were not recovered.

⚠️ **`contracts/requirements.md` is still empty**, so the *Discharges* column below cites the **contribution**
(C1 / C2 / C3) and the **scalability clause** (S1–S4) it serves — both of which *are* defined, in
`Final_Proposal.md` §5 and §3. Requirement IDs replace those citations when `requirements.md` is
filled; the column is not left blank in the meantime, because an item that discharges nothing
identifiable should not be in a plan at all.

---

## The spine — why safety and throughput are one problem here

`Final_Proposal.md` §3 fixes capacity as **λ_max = min( μ_gen / (1 − h) , μ_hit / h )**. `μ_gen` is
fixed by the envelope (one generation slot, ADR-003) and planned at ≈ 0.19 req/s, a projection from
the spike that Phase 7 re-measures. So **`h`, the hit rate, is the only free variable that raises
capacity** — and `h ≤ ρ` for any cache that serves no false hit, because `h > ρ` is reachable only
by being wrong.

Three consequences, and they are why the phases are ordered the way they are:

1. **The safety work *is* the throughput work.** A gate that refuses unsafe reuse is what licenses
   running a *lower* θ/τ at the same δ, which raises `h`, which raises λ_max. The support gate of
   the support gate is the highest-value unbuilt item for **both** halves of the objective — it is not a
   correctness tax paid against throughput.
2. **Admission control does not raise capacity; it protects it.** It is S2 (stability), not S1
   (capacity), and it is **already built**. It is sized to the one slot the model server actually
   serves (ADR-003, which resolved finding F1), and it protects **queueing delay and goodput, not
   memory**: memory is fixed when Ollama loads the runner.
3. **Tier-1 promotion is an unmeasured throughput lever already in the tree.** μ_hit is ~8000 req/s
   on Tier 1 against ~61 on Tier 2, so the **tier mix** moves μ_hit more than any Tier-2
   micro-optimisation can. `handler.go` began promoting Tier-2 hits into Tier 1 on 2026-09-10 and
   nothing has measured the effect.

One rule binds over all of it: **never tune to make a headline work.** Thresholds are swept, tuned
on validation, reported on held-out test. The deliverable is a **frontier**, never a tuned point.

---

## Item template

Every item is a row of this shape. An item that cannot fill the citation columns is not ready to
be planned — it needs a requirement, or an ADR, or both, first.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |

Two columns earn their place and are easy to skip:

- **"Unblocked when"** is what makes the order *derivable* rather than asserted. An item whose
  blocker is another item creates the sequence automatically; an item blocked by a human decision
  says so, by name, so it is visible that it is waiting on a person rather than on work.
  **Once an item's "Done when" test passes**, its own cell becomes `✅ Done <date>`, followed by
  its ADR, if any, and its trail. Every other row that lists it as a blocker marks it `✅` too
  (`7.1, 1.1 ✅`), so the column shows at a glance what is finished and what still blocks.
- **"Done when"** is a **binary test**. "Improved", "hardened" and "investigated" are not
  done-conditions. An item is not finished because its time is spent.

---

## Standing constraints on every item

These are not items. They hold across all of them, and an item that violates one is wrong
regardless of how well it is executed.

1. ~~**F1 sits above the order.** No admission-control number is citable until it resolves.~~
   **Resolved by ADR-003 (2026-10-04, item 1.1).** One slot is frozen, the gateway grants one permit,
   and `make env-check` verifies the live runner. Admission numbers are citable from here on, subject
   to the other constraints, and q is pre-registered per item 7.5.
2. **The platform is the thesis.** Research work never starves platform work.
3. **`dev-v0` is not citable in any result.** Only the frozen `v1`.
4. **Runs taken under yellow or red memory pressure are discarded and repeated.** A run taken
   outside green pressure measures the swap, not the system.
5. **A frozen value changes only through a numbered entry in `decisions.md`**, and that entry
   states what it invalidates. Nothing enforces this — it is the only trace such a change leaves.
6. **No measurement runs off an untested instrument.** Added 2026-09-21: `httpapi/` carried 856
   lines and zero tests while every number in the thesis passed through it. Phase 1 exists for this.

---

## Phases

Eight phases. Each ends on a binary exit test; the next does not open until it passes. Hour figures
are indicative against the ≈ 225 h remaining — `Final_Proposal.md` §12's drop order is the release
valve, not these numbers.

### Phase 1 — Instrument integrity

**Exit:** `httpapi` has tests covering every exit path of `Ask` · `make env-check` fails when the effective Ollama slot count differs from the frozen value · `texts` flows Python → Go with positional alignment asserted · no retired branch remains in the cascade · a judged answer is recoverable from `raw/` alone · the load generator's footprint is measured and the co-hosted-measurement decision is recorded as ADR-001.

*Nothing measured before this closes is evidence of anything.* ~25 h.

**Progress, 2026-10-07:** 6 of 6 exit clauses met: the `env-check` clause by item 1.1, the
`httpapi` clause by item 1.2, the no-retired-branch clause by item 1.3, the `texts` alignment
clause by item 1.4, the answer-recoverable-from-`raw/` clause by item 1.5, and the load-generator
footprint clause by item 1.6 (ADR-001). **Phase 1's exit criterion is met**, to be re-run by hand when the
phase is closed. Item 1.6 did **not** need green memory pressure: it was taken under the author's
2026-10-06 decision that this is development, not a benchmark, so its footprint is **indicative** (the
sysctl read 2 throughout, swap was in use), and ADR-001 says so.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 1.1 | **Resolve F1.** Ollama overrides `OLLAMA_NUM_PARALLEL` to `-np 1` for qwen3.5. Add a check that reads the **effective** slot count from the live runner (its argv `-np` and its own `/props` `total_slots`; ADR-003 records why not the server log) rather than the requested value, and write the ADR deciding what μ_gen ≈ 28.2 tok/s means if it was a one-slot number recorded as a four-slot aggregate | S1, S2 | memory envelope, admission control | ✅ **Done 2026-10-04** — ADR-003, trail `docs/work/2026-10-04-resolve-f1/` | `make env-check` fails when effective ≠ frozen, and an ADR records the consequence for μ_gen |
| 1.2 | **Tests for `httpapi/`.** The cascade, the miss path, coalescing-wraps-admission nesting, Tier-1 promotion, and the single-exit eval-record emit | C1, C3 | standing constraint 6 | ✅ **Done 2026-10-04** — no ADR (no frozen value or contract changed), trail `docs/work/2026-10-04-httpapi-tests/` | Every exit path of `Ask` — TIER1_HIT, TIER2_HIT, MISS, SHED, ABANDONED, GENERATION_FAILED — has a test asserting its response **and** its eval record |
| 1.3 | **Remove the retired cascade branch.** Delete the unfiltered cascade phase, `tau_high` / `REUSE_TAU_HIGH`, and `similarity_only_decision`. Correct the stale pinned default in `rule_test.go` (claims `1.0`; ships `math.Inf(1)`) | C1, C3 | retiring the unfiltered phase | ✅ **Done 2026-10-05** — ADR-004 (`interfaces.md` v0.10), trail `docs/work/2026-10-05-retire-unfiltered-phase/` | The cascade issues one scoped search; `grep -r tau_high` finds only history; §H no longer carries the retired field |
| 1.4 | **Carry chunk text across the seam.** `server.py` populates `texts`; `ragclient` receives it. Proto and both stubs are already done | C1 | `Retrieve` returns text | ✅ **Done 2026-10-05** — no ADR (no frozen value or contract changed), trail `docs/work/2026-10-05-carry-chunk-text/`. Re-run `make seam-check` after any retrieval or LlamaIndex change: `make verify` never runs the live path | An end-to-end test asserts `texts[i]` is the text of `chunk_ids[i]`, and a deliberately shifted array fails it |
| 1.5 | **Answer-text storage.** §H stores `answer_sha256`, never the text, and judging runs offline with the generator unloaded. Recovering text from a bounded LRU afterwards is unsound. Content-addressed `raw/answers/{answer_sha256}.txt` | C3 | needs a numbered decision — it changes §H, which is frozen | ✅ **Done 2026-10-06** — ADR-005 (`interfaces.md` v0.11), trail `docs/work/2026-10-06-answer-text-storage/` | A run's answers are reconstructable from `raw/` alone, with the cache flushed |
| 1.6 | **Characterise the load generator's footprint** and **record the co-hosted-measurement decision** as the first entry in `decisions.md` (see "Measuring without a second machine") | S1, S2 | measurement validity | ✅ **Done 2026-10-07** — ADR-001, trail `docs/work/2026-10-06-loadgen-footprint/` (k6 at 2, 8, 16, 32 req/s plus a mixed row: 1.0 → 4.8 % of one core, 28 MB peak footprint; indicative; the sweep's own grid is 7.1's, so these bracket it rather than measure it; the Done-when's wording is **not amended**) | k6's CPU and RSS at the sweep's actual rates are recorded, with the SUT's pressure zone alongside, and the ADR states what is citable co-hosted and what is not |

**Found while closing 1.1, not yet items — each waits on the author's decision:**

- ✅ **`rag-server-reuseport`, resolved 2026-10-05** as a bugfix outside the exit line (trail
  `docs/work/2026-10-05-rag-server-reuseport/`). `rag/src/rag/server.py` bound with gRPC's default
  `SO_REUSEPORT`, so a second server silently shared port 50051 and a run could be answered by a
  stale instance (six were found on 2026-10-03). The server now binds with `SO_REUSEPORT` off, so a
  second bind on the same address raises. **Residual, recorded rather than fixed:** a wildcard and a
  specific address (`0.0.0.0:P` and `127.0.0.1:P`) can still coexist on macOS. That needs a
  non-default `RAG_GRPC_ADDR`.
- **Generation determinism (U8).** The Modelfile sets `temperature 1` and `generate.py` does not
  override it, so the same miss can produce different answers from run to run. It bears on judging
  (5.1) and on reproducibility. It needs an investigation before 1.5 or 5.1 is built on it.
- **For the advisor:** withdraw the proposal's `OLLAMA_NUM_PARALLEL` sweep (§6.2), which cannot run
  on this model and stack (ADR-003). This is a human decision, and it must be settled before Phase 7.

**Found while closing 1.2, not yet items — each waits on the author's decision** (full list F-A to
F-K in `docs/work/2026-10-04-httpapi-tests/spec.md`; order in that trail's `approvals.md`, item 3):

- **F-K: the served Tier-2 rule is similarity ∧ namespace, not the four claimed conjuncts.** *(Since item 2.3 it is three: the support gate is served, and θ is the missing one. With the gate off, item 2.4, it is two.)* θ
  reaches only the logged counterfactual and `ConfigID` selects nothing, so **6.1's θ sweep would
  move no served decision**. No ADR records the change. It needs an owner: an ADR that makes the
  namespace rule the claim, or an item (probably in Phase 2) that puts θ into the served decision.
  **Since 1.3 (ADR-004), configuration 3 has no code path either.** `REUSE_TAU_HIGH` was the only
  way to serve on similarity alone, and the gateway now refuses it. Configuration 3's served rule
  (global k=1 + τ over `cache.Store.NearestTier2`, kept for it), the static-cache arm and the
  3 ⋈ 4 join script have no item. *Decisions changed by provenance* has no derivation until they
  do, so the owner of F-K's configuration selection should own them before Phase 6.
- ✅ **F-A, resolved 2026-10-05** as a bugfix outside the exit line (trail
  `docs/work/2026-10-05-fa-abandonment-classification/`; no ADR, no contract change). Most client
  abandonments were logged `GENERATION_FAILED`: a cancellation that reaches a gRPC call surfaces as a
  gRPC status, not `context.Canceled`. The outcome switch in `httpapi/handler.go` now also files
  **`err != nil && ctx.Err() != nil`**, read from the request's own context, as `ABANDONED`. The
  precedence is `SHED` > this request's client gone ⇒ `ABANDONED` > `GENERATION_FAILED`, and a
  completed generation is always a `MISS`. **Read `ABANDONED` with the experiment record in that
  trail's `approvals.md`** (**except** its statements that `t_generate_ms` is null on abandoned
  requests, superseded by F-H below and by §H v0.12):
  - under a load generator it is a **censored latency observation**, at least the client timeout,
    and counts against S2. It is **never excluded as client behaviour**;
  - an upstream hang mostly lands in it (k6's and `httpx`'s timeouts are both 120 s), so
    `GENERATION_FAILED ≈ 0` does not show the upstream never hung, and `GENERATION_FAILED > 0` does
    not show an upstream fault while F-D stands;
  - it is at most k6's status-0 count, and only an **upper bound** on orphaned generations (F-L).
    F-H (below, resolved) **tightens** that bound without turning it into a count.
- **F-L (new, found by F-A's impact analysis): `rag.server` keeps generating after its RPC is
  cancelled.** Probed with a stubbed `generate` (no Ollama): the client cancelled at +0.20 s and the
  stub ran on to +1.50 s. Nothing in `server.py` checks `is_active` or `add_callback`, and
  `generate.py` blocks on `httpx` for up to 120 s. The gateway therefore releases its one permit
  while Ollama's one slot is still busy, so the next admitted request **queues inside Ollama**,
  which is what ADR-003 says admission exists to prevent. Its `t_generate_ms` absorbs the remainder
  and the admitted-latency bound (1 + q) · S breaks. The F-A review recommends **gating Phase 7
  (7.1, 7.5) on it, not item 1.6**: an orphan adds no memory (Ollama's footprint is fixed at load,
  ADR-003), so it cannot move 1.6's CPU/RSS number (PLAUSIBLE). It can be closed by measurement if
  abandonment during `Answer` is shown to be about zero, since k6's 120 s timeout sits far above
  (1 + q) · S. Otherwise the fix's shape is known: check `context.is_active()` before generating,
  and close a per-request streaming `httpx` response on cancel. **The author decides whether to fix
  it before 1.6.**
- ✅ **F-H, resolved 2026-10-06** as a bugfix outside the exit line (trail
  `docs/work/2026-10-06-fh-generate-ms-on-abandoned/`; **ADR-006**, `interfaces.md` **v0.12**, doc-only).
  `rec.GenerateMS` was copied only on the success path, so `t_generate_ms` was null on
  `GENERATION_FAILED` and `ABANDONED` although `Answer` had run. It is now copied right after
  `Generations.Do`, before the outcome switch. **Read it as §H v0.12 says:**
  - non-null **iff this request's own `Answer` was attempted**; null on followers, SHED, and a request
    that left or failed before it held a permit; **censored on ABANDONED** (F-L); a null on
    GENERATION_FAILED means a follower, a null on ABANDONED is ambiguous;
  - **select MISS service times with `cache == "MISS" ∧ t_generate_ms != null`**, never presence alone
    (until this fix presence meant exactly that; it no longer does); filter `!= null`, never `> 0`;
  - the "RPC never left" split uses a **pre-registered 1 ms default with a [1 ms, 100 ms] count check**.
    **The author confirms the number**; ADR-006 carries one `⟦PENDING⟧` for it. A first reading on a
    fixture: 1-12 µs without `-race`, 12-31 µs under it, 0 of 30 above 1 ms (exploratory, not citable).
- **F-J / Phase 2 design input: write-back runs on the client's context, as two separate writes**
  (`store.go:68`, `tier2.go:118`; F-A `review.md` N5). A client leaving between them leaves a Tier-1
  entry with no Tier-2 record carrying its `t1_key`, which is invariant 2's silent purge miss once C2
  exists. The window is one Redis round trip. Run write-back on `context.WithoutCancel(ctx)` with a
  timeout, as the Tier-1 promotion already does.
- **For item 1.6:**
  - report the **`ABANDONED` count**, and read it as above;
  - `t_generate_ms` now separates the **orphan-candidate subset** (ABANDONED with a value above the
    threshold); report the **count of ABANDONED values in [1 ms, 100 ms]** beside any split. The
    threshold and that check belong in P1's manifest, and the number is the author's;
  - **take the first `RUN_ID` after the F-H commit**: logs carry no gateway SHA until P1, and the
    `t_generate_ms` of ABANDONED and GENERATION_FAILED records is not comparable across it;
  - whether a k6 timeout closes the connection, so that `r.Context()` is cancelled, is proven only for
    Go's own client (test T7). The first run with a `RUN_ID` settles it;
  - **P1's manifest should record the gateway SHA**: nothing in §H identifies which side of the F-A
    commit a log came from, and the `ABANDONED` / `GENERATION_FAILED` split is not comparable across it.
  - **Settled when 1.6 closed (2026-10-07):** the footprint runs were taken at HEAD `17bf221`, after the F-H
    commit, and each `header.json` records the SHA and a `gateway`/`rag`-only dirty flag, which is a
    precedent for P1. `ABANDONED` was **not observed** (k6's `error_rate` was 0 in every kept row) but is
    **vacuous** for the all-hit rows and **not settled** for the mixed ones. **Whether a k6 timeout closes the
    connection is still not settled** (no k6 timeout occurred; its limit is 120 s). The ADR-006 1 ms
    threshold is still ⟦PENDING⟧. **F-L was not fixed before 1.6** (the author's decision) and **still gates
    Phase 7** (7.1, 7.5).
- **F-F: the eval log closes while shutdown is still draining.** Requests in flight at SIGTERM
  vanish from `requests.jsonl` with `Dropped()` at 0. It is avoided by stopping the load before
  SIGTERM, and the fix is cheap. Fix it before Phase 7. *The mechanism, sharpened by 1.5's review:*
  `ListenAndServe` returns `ErrServerClosed` the moment `Shutdown` is **called**, and `main` does not
  wait for `Shutdown` to return, so `Close` runs while handlers are still in flight for up to 10 s.
  The fix is a `done` channel that `main` waits on before `Close`. A `Log` racing `Close` panics
  inside `Ask`'s deferred emit and `net/http` swallows it (reproduced in 97 of 300 hot-producer
  iterations). 1.5 does not widen it: the skipped set is fixed by the CAS at the start of `Close`.

**Found while closing F-H, not yet items — each waits on the author's decision** (trail
`docs/work/2026-10-06-fh-generate-ms-on-abandoned/`, `review.md`, `impact.md` §6):

- **F-N: `t_permit_wait_ms` is null in three cases §H says it should not be.** Every **fast-path**
  request (`Acquire` returns a permit with `Waited == 0` and `msPtr(0)` is nil), a request that **queued
  and then left** (the closure returns before it is set), and when **admission is disabled**. §H says
  *"null unless a permit was requested"*. So `!= null` means "queued and was served", and a mean over it
  is biased high. Pre-existing; found by F-H's impact analysis; **not fixed**. F-A's record reads it
  correctly for its own purpose (only a request that queued has it non-null). Fixing it changes what the
  log means for admission, so it needs a contract note like F-H's.
- **F-O: `coalesced` is set only on a served MISS and is not in §H.** `rec.Coalesced = shared` runs after
  the outcome switch, and the field is a gateway extension (`omitempty`: absent on leaders, never
  `false`). A coalesced follower of a failed or cancelled leader carries no `coalesced`, so its record is
  told from a leader's only by a null `t_generate_ms` (GENERATION_FAILED) or a `t1_key` time-interval
  join. Moving it above the switch is one line but a **second measurement change**; deferred next to
  F-D, which decides what a follower should read.

**Found while closing 1.5, not yet items — each waits on the author's decision** (trail
`docs/work/2026-10-06-answer-text-storage/`, `approvals.md`, `review.md`):

- **F-M: `main` exits 0 when `ListenAndServe` fails for a reason other than shutdown** (a bind
  failure). It logs and falls through, the run reads as complete, and an empty `requests.jsonl` plus
  `answers/` burn the `RUN_ID`. A wrapper that treats exit 0 as "run finished" accepts an empty run.
  `getenvInt("CONFIG_ID")`'s `log.Fatalf` runs after `telemetry.Open` and burns the run id the same
  way (non-zero exit). CONFIRMED by 1.5's code review; pre-existing; not fixed. Cheap.
- **For 5.1:** `answer_sha256` alone **cannot key Tier-2 verdicts**. A reused answer is byte-identical
  across queries, so a true hit `(q1, A)` and a false hit `(q2, A)` collapse into one verdict and the
  false-hit rate is biased toward whichever came first. The key must be `(query, answer)`, and the
  delimiter in `sha256(query ‖ answer)` is unspecified. Row 5.1's wording ("deduped by
  `answer_sha256`") needs rewording; **not edited**, it is 5.1's design. §H v0.11 already says it.
  5.1 must also decide whether the judge needs the retrieved evidence text; it is **not stored**, and
  under `mutation: on` it is recoverable only if the mutation harness writes the applied update set
  with epochs into `raw/`.
- **For 5.4:** `raw/` is **gitignored** (decided 2026-10-06; ADR-005). A clean checkout carries no
  `raw/`, so "regenerate every figure from `raw/`" means *plus the raw archive*, and 5.4 designs how
  the archive is kept and restored. Git no longer enforces that a finished run is write-once, and a
  hash manifest of `raw/` is not planned (P1).
- **For Phase 3 / Phase 7, the author's call: Spotlight.** `/` is indexed, so each new
  `raw/answers/*.txt` is imported by `mds`/`mdworker` during the measured window (up to `0.25·K` files
  in the static-cache arm's first-sighting burst). Unmeasured. Exclude `experiments/results/` as a run
  precondition, or measure it? **Also:** the answer writer sustains ≈ 2,250 *first sightings*/s
  (≈ 440 µs each; repeats cost nothing). It can drop only in a Tier-1-heavy phase at thousands of
  req/s over a large `K`, in its first seconds. A Phase 7 run of that kind checks `Dropped()` and
  `AnswersMissing()` first (`docs/work/2026-10-06-answer-text-storage/evidence/drain-rate.md`).
- **Workflow:** `/verify`'s **proto-drift row checks nothing**. Both stub directories are gitignored,
  so `git diff --exit-code` on them is always clean (`.claude/commands/verify.md:17`, a file removed
  2026-10-27; no check replaced the row). It was reported clean on earlier closes. `git diff --exit-code contracts/` checks the `.proto` source, not that the
  stubs match it. **And:** `make test` and `make verify` do not run `-race`, so the new `missing` mutex
  has no CI guard (it was race-tested by hand).
- **Stale `v0.9` strings** (`CLAUDE.md:106`, `.claude/agents/contract-reviewer.md:11` — that file
  was removed 2026-10-27, `architecture.md:30`) await the author's OK to edit. **Candidate follow-up:** a verifier script for a
  finished run's `raw/` (every non-empty hash has a file whose bytes hash to its name; nothing
  unnamed), worth having before the first real run.

**Found while closing 1.4, not yet items — each waits on the author's decision** (trail
`docs/work/2026-10-05-carry-chunk-text/`, `approvals.md`):

- ✅ **`make dev` orphaned `rag.server`, resolved 2026-10-05** with `rag-server-reuseport`.
  Confirmed under `/bin/bash` 3.2: `$!` was the subshell, so the trap left the server bound to
  `:50051`. The fix has three parts:
  - `make dev` now `exec`s the server, so `$!` is the server itself;
  - it refuses to start if the port is already held;
  - it starts the gateway only once its own server PID is listening, replacing a `sleep 2` that a
    late bind failure slipped past.

  2.1's obligation on nil `Texts` stands regardless: the gateway's own connection is still the only
  check on the gateway's instance.
- **For 3.1:** the PQA builder must not emit text that redis-py's strict UTF-8 encoder rejects (a
  lone surrogate from a JSON `\ud800` escape); it would fail `make ingest` (PLAUSIBLE; 1.4
  `review.md` N5).

**Found while closing 1.6, not yet items — each waits on the author's decision** (trail
`docs/work/2026-10-06-loadgen-footprint/`, `approvals.md`, `evidence/`):

- **The memory-pressure sensor's encoding.** `make measure` (`Makefile:95`) and `CLAUDE.md` treat
  `kern.memorystatus_vm_pressure_level == 0` as green. The sysctl read **1 or 2 in every sample of the
  recorded runs and never 0**, while `memory_pressure` reported 37 – 47 % free at the start. If XNU returns
  1 / 2 / 4 (normal / warn / critical), the gate can never pass and Phase 7 is blocked, and `CLAUDE.md`'s
  "`0` = green" is wrong; if `0` is right, the machine was never green. **Unverified.** The cheap check is
  to read the sysctl while Activity Monitor's pressure graph is green. **Nothing was edited.**
- **What Phase 7 inherits from ADR-001:** every co-hosted p95 is reported with k6's concurrent CPU from the
  same run; μ_gen for `h*` is measured with a sequential client and **no** load generator (⟦PENDING: the
  author confirms for 7.5⟧); the interference method (a matched-burner test, or that no-generator
  measurement) is **7.1's to design**, because a "with and without k6" comparison is not runnable; and
  `mu_hit.js`'s verdict line (`mu_hit ~= X`) is **7.2's** to fix. **The sampler's own cost (2.3 – 2.75 % of a core at 1 Hz) is the same
  order as k6's below about 16 req/s**, so Phase 7 should state it, lower the frequency, or replace the
  `ps`/`sysctl` calls (`libproc` removes the exec cost but reports Mach ticks on Apple Silicon: a silent
  ~41.7× error).
- **`make footprint` deletes cache keys** (`t1:` `t2:` `lru:`, never `corpus:`) at the start of a run and before
  each mixed repetition, and **refuses to run while `dep:`/`entry:` exist** (C2's dependency region has one
  writer). The Makefile banner says so. **Beyond what decision 9 covered: the author's confirmation is
  pending** (`approvals.md`). Item 6.3's pre-populated static-cache arm must not meet it.
- **`ollama ps` is not a residency check.** The LLM runner's resident set was **13–19 MiB in 8 of the 12
  all-hit rows** while `ollama ps` listed the model as loaded (weights compressed or swapped out), and
  286–968 MiB in the mixed rows. A later run that needs a resident SUT should gate on the runner's RSS.
- **Stale "lower bound on `h*`" prose** (see the pointer under "Measuring without a second machine"):
  `CLAUDE.md:162-167`, `Final_Proposal.md` §7 `:345` and §9.4 `:460`, plus this file's Phase 7 exit line,
  item 7.2 and that section. A Phase 7 session that reads only `CLAUDE.md` would report `h*` from a co-hosted
  μ_gen as a conservative bound. `CLAUDE.md` and `Final_Proposal.md` wait for the author.
- **`interfaces.md:164`** ("the eval also records off-box end-to-end separately") records a **lost
  measurement**: co-hosted p95 is loopback latency and excludes the network. Not edited (a v0.13 bump);
  ADR-001 records it.
- **Workflow:** `make lint` prints "ruff SKIPPED" when `ruff` is not on `PATH` (it lands in
  `~/Library/Python/3.13/bin`), so a bare `make verify` can pass **without linting**. The two new 1.6 files
  had 19 ruff findings that it would not have shown. And `make check` still cannot fail (every grep ends
  `|| echo clean`). Neither is fixed.

### Phase 2 — The support gate

**Exit:** the gate refuses the measured warranty case and admits the measured paraphrase · every Tier-2 refusal carries a cause code · the gate is switchable per run (on or off) and both of its arms are recorded per request · the decisive-similarity regression still reproduces.

*The highest-value unbuilt item for both halves of the objective.* ~20 h.

**Progress, 2026-10-14:** items 2.1, 2.2, 2.3 and 2.4 are done, and item 2.3's acceptance 10 (the real-answer sample) **ran on 2026-10-14** (trail `docs/work/2026-10-14-real-answer-sample/`, dev-v0, not citable): no stop rule fired, so **what is left to close Phase 2 is the author's reading of exit clause 1**. *(Item 2.4 also fixed the wording of exit clause 3: it said "both arms are independently switchable", which could be read as the lexical and numeric arms each switchable; it means the whole gate on or off, and that the gate's two arms are both recorded.)* Run clause by clause: (1) the gate refuses the warranty case and admits the paraphrase — **both arms do it on the pinned texts** (a fixture: real evidence, authored answer), the cascade now calls them, and **through `Ask` the namespace search refuses the measured warranty case before the gate runs, so that case is a MISS with cause `null`** (ADR-009); whether that meets the clause is the author's call; (2) **met**: every judged Tier-2 candidate logs one `refusal_cause` (`TestCauseOfflineReading`); (3) **met** (item 2.4, ADR-010): the gate is switchable per run (`SUPPORT_GATE=on|off`, unset = on), both of its arms are recorded per request (`support_lex`, `support_numeric_ok`; null on the off-arm), and every record names the arm (`support_gate`); `TestSupportGateOffServesWhatTheGateRefuses` shows the same refusing fixtures served with the gate off; (4) the decisive-similarity regression holds (`TestNoThetaSeparatesTheMeasuredPair`) and is re-run when the phase closes. **The real-answer sample** (`τ_s = 0.6` against answers the system really generated, with the numeric arm counted too) ran after the gate was wired, because memory pressure had been level 2 when 2.3 closed (questions frozen in `docs/work/2026-10-14-refusal-cause-code/sample-questions.md`, sha256 `93bc8f43…`; 27 answers, 32 scored rows). **Result, n = 27, dev-v0, temperature 1, pressure 1 to 2, not citable:** 0 of 5 real paraphrases refused (the second pre-registered null did **not** occur; 95 % Wilson upper bound 43 %, and 4 of 5 paraphrases retrieved the identical chunks as their question); 2 of 21 answers below `τ_s` (9.5 %) and 0 of 21 refused by the numeric arm; 5 of 6 negative pairs refused, but c1 and probably c2 are same-evidence pairs refused only because the answer scores low against its own evidence. **Two findings for the thesis:** about one answer in ten is refused although it was generated from the evidence it is checked against, and the lexical arm is sensitive to the model's habit of narrating its source ("the context"; mean `S_lex` 0.60 with the word, 0.85 without). **Nothing was tuned or edited.** Whether to revisit the `S_lex` definition belongs to item 6.1's pre-registration, not to this sample.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 2.1 | **Lexical arm.** `S_lex(a,C) = \|content-tokens(a) ∩ tokens(C)\| / \|content-tokens(a)\|`, stop-words and tokens under three characters removed. `τ_s` **pinned at 0.6**, never swept. ⚠️ **`RetrieveResult.Texts == nil` with `len(ChunkIDs) > 0` means the service sent no evidence text** (e.g. a stale pre-1.4 server): do not score it, do not refuse it as `SUPPORT`, and do not log it as the gate-off arm (`support_lex: null`) — each misattributes a stale server to the gate. Key on `len(ChunkIDs) > 0`, since an empty retrieval is nil too, and count the condition (1.4 trail, `review.md` S3) | C1 | the support gate | ✅ **Done 2026-10-12** — no ADR (no contract or pre-thesis frozen value changed; the new `S_lex` definition is a row in `decisions.md`'s frozen table), trail `docs/work/2026-10-10-support-gate-lexical-arm/`. The Done-when test is `TestSupportLexicalSeparatesTheMeasuredPair`: real dev-v0 evidence, but an **authored** cached answer (none was ever captured for the 2026-09-06 case), so it pins the formula, not a replayed measurement. **Wired by item 2.3** (it was unwired when this item closed). Re-run `make support-check` after any retrieval change: `make verify` never runs the live path | On the pair pinned in `lane_test.go` (0.9382 paraphrase, 0.9208 warranty, containment 0.80 each) the gate admits the first and refuses the second |
| 2.2 | **Numeric arm.** Every numeric literal and its unit in the cached answer must appear in the fresh evidence. **Fail-closed** | C1 | the support gate | ✅ **Done 2026-10-14** — no ADR (no contract or pre-thesis frozen value changed; the rules are a row in `decisions.md`'s frozen table), trail `docs/work/2026-10-14-numeric-arm/`. `SupportNumeric` in `reuse/support_numeric.go`; the Done-when tests are `TestNumericDoneWhen` and `TestNumericUnreadableBlocks`. On the pinned dev-v0 texts it admits the paraphrase evidence and refuses the warranty evidence, but only because 30 is absent there: other rows exercise the unit check, and each of 41 hand-made edits to the rules turns a test red (script in the trail; it proves those 35 are caught, not that every possible edit is). **Wired by item 2.3** (unwired when this item closed). The unit list is draft until the Phase 3 corpus freeze. 2.3 added the "not scored" value (`NOT_SCORED`) to §H and closed the zero-chunk hole in the cascade | A cached "30-day" answer is refused against evidence carrying only "14-day"; an unparseable number blocks rather than passes |
| 2.3 | **Refusal cause code** in §H: `SIMILARITY` \| `NAMESPACE` \| `CONTAINMENT` \| `SUPPORT` \| `NONE`, plus `support_lex` and `support_numeric_ok` | C1, C3 | the support gate | ✅ **Done-when passes 2026-10-14; acceptance 10 (the real-answer sample) has since RUN, 2026-10-14**, trail `docs/work/2026-10-14-real-answer-sample/` (nothing tuned) — **ADR-009**, `interfaces.md` **v0.13**, trail `docs/work/2026-10-14-refusal-cause-code/`. The cascade calls both arms through `reuse.Thresholds.Judge` and serves only on cause `NONE`; five keys join §H (`refusal_cause`, `support_lex`, `support_numeric_ok`, `candidate_entry_id`, `candidate_sources`); `NOT_SCORED` (a server that sent no evidence text) is refused and makes a run inadmissible (§H rule 10); a retrieval with no chunks makes no Tier-2 attempt. The Done-when tests are `TestCauseOfflineReading` and `TestJudgeAgreesWithDecideLane`; 31 hand mutants, all caught. **The measured warranty case is a MISS with cause `null` in configuration 4** (the namespace search refuses it before the gate), so it is not a `SUPPORT` example. **The real-answer sample has since run (2026-10-14, `docs/work/2026-10-14-real-answer-sample/`): see the Phase 2 progress paragraph** — no stop rule fired, nothing was tuned. Four keys changed meaning under the same name (`TIER2_HIT`, `entered_band`, `source_overlap` on a MISS, `t_search_ms` on zero chunks): a pre-2.3 log is not comparable | Every Tier-2 decision in the log carries exactly one cause; a support refusal is distinguishable from a namespace refusal offline. ⚠️ Since 1.3, configuration 4 enforces the namespace **by the search, not by a refusal** (ADR-004): "no in-namespace candidate" is a MISS with no candidate and **must not** be coded `NAMESPACE`, or a cold cache becomes namespace refusals |
| 2.4 | **Both arms switchable per run**, since configuration 4 is two arms rather than one | C1, C3 | the support gate, config × mutation grid | ✅ **Done 2026-10-14** — **ADR-010**, `interfaces.md` **v0.14**, trail `docs/work/2026-10-14-support-gate-switch/`. `SUPPORT_GATE=on\|off` (unset = on; anything else stops the gateway before it opens Redis or the log) chooses the arm for a process; `reuse.Gate` is the **first** parameter of `Judge`, its zero value is `GateOn`, and one `Handler` field feeds both the call and the new required record key `support_gate`; the off-arm writes cause `NONE` with null support fields, after the namespace and similarity checks. **The Done-when's wording is not amended:** there is no run manifest (P1), so "in the run manifest" is met by the gateway's variable and the per-record key, and P1's manifest must record `SUPPORT_GATE` from the records. Rule 11 and invariant I9 cover the cache a run starts on. The Done-when tests are `TestSupportGateOffServesWhatTheGateRefuses` and `TestJudgeAgreesWithDecideLaneGateOff`; 18 new tests, 47 hand mutants all caught (the 31 of 2.3 and 16 new). **A configuration-4 run is now identified by `(config_id, mutation, support_gate)`**; `CLAUDE.md` and `Final_Proposal.md` still say `(config_id, mutation)` and wait for the author. **Not 2.4's:** the real-answer sample (2.3) has since run (`docs/work/2026-10-14-real-answer-sample/`); what is left to close Phase 2 is the author's reading of exit clause 1 | `support_gate` in the run manifest selects the arm, and the off-arm writes `null` for both support fields |

### Phase 3 — Corpus and workload

**Exit:** G2…G5 pass, G1 is recorded as ADR-014's finding with its counts, and `make gate-corpus` prints the snapshot digest under a recorded failure · `K`, the derived capacity and every frozen corpus statistic are recorded in `data-card.md` · the validation/test splits are frozen with the dataset.

*Four jobs, not a download. Longest lead, and it can fail its own gate and need rework.* ~45 h.

**Progress, 2026-10-23: item 3.6 is done and Phase 3 is closed, with G1 recorded as FAILED (ADR-014, ADR-015).** `v1` is frozen: 164 corpus files and 3 workload files, snapshot digest `a5708fefa62c…`, 539 chunks, `K` 622 / 652, capacity 156 / 163 (`data/v1-freeze.json`; `data-card.md` §7 is filled). G1 is 21 pairs inside a split against a floor of 50. It is **recorded as a corpus finding that bounds C1's applicability** (`Final_Proposal.md:497`), not a pass: the gate reports `passed: false`, the record lists `known_failures`, and the **Exit line above was amended** to say so, at the author's instruction to close the phase (the wording ADR-014 proposed). Two fresh-ingest gate runs agree with each other and with the first run, and the retrieval exports are byte-identical; all memory readings were 1 (green; the old "0 = green" was wrong and `GREEN_LEVEL = 1` is in the code). Trails: `docs/work/2026-10-22-corpus-freeze/` (tooling, first run), `2026-10-22-g1-finding/` (ADR-014, the allowance), `2026-10-23-corpus-freeze-run/` (the freeze, ADR-015). **Carried:** a restore path for `data/v1/` (Phase 4); P1 (`CACHE_CAPACITY` from the run file's `K`, the stale `K` comment at `gateway/cmd/gateway/main.go:267-268`, a call to `corpus-verify` at run start); three `TODO(W8)` markers that are not 3.6's (the paraphrase set and the update set). **Open for the author:** ADR-014's "How C1 is read" paragraph and its supervisor line; whether a `v2` follows (with the supervisor, before Phase 4); `CLAUDE.md:44` and `README.md:227`, which still say `0 = green`.

**Progress, 2026-10-22 (later): item 3.6 was run and stopped, and is still open.** The freeze tooling is built, tested and committed (trail `docs/work/2026-10-22-corpus-freeze/`). The first gate run on the ingested `v1` **failed G1: 21 pairs inside a split (13 validation, 8 test), 50 needed** (stop rule S1). G2 – G5, `W` and `S` pass. Nothing is frozen: no snapshot digest, no `data/v1-freeze.json`, 13 `TODO(W8)` markers open, Redis holds `dev-v0`. **Phase 3 exit is not met.** The name-swap probes sit at cosine 0.66 – 0.80, below the 0.85 floor, and the policy-condition pairs share chunks (J mostly 0.2 – 0.5). By S1 the next step is the author's: reopen 3.3 or 3.4 under its own approvals (changing the G1 statistic is its own ADR). All 53 memory readings were 1, which is the normal level on macOS's scale (not yellow: the repo's "0 = green" is wrong; see the correction in the trail's `approvals.md`), so the figures stand. Counts: `evidence/gate-failure.md` in the trail.

**Progress, 2026-10-22:** item 3.4 is done (**ADR-013**, trail `docs/work/2026-10-21-workload-generator/`): the workload is **1,274 queries** in three gitignored files, with the tracked `data/workload-manifest.json`, `interfaces.md` v0.15 and `data-card.md` v0.7. **Phase 3 exit is not met:** 3.6 is open (the freeze, G1 and G2 on the ingested index, `K` for each file and every §7 statistic); 13 `TODO(W8)` markers are open in `data-card.md`, and the §7 ones are 3.6's. 3.6 is next.

**Carried out of 3.4 (ADR-013; `design.md` §11 has the detail).**
- **To 3.6:** the digest over the three files; `K` and `round(0.25 × K)` for each file; G1 and G2 per split on the ingested `v1`, scoped, with unscoped beside; per-stratum and per-`probe_kind` counts and the trap fraction for each split; for each probe, the scoped-retrieval Jaccard and whether its evidence spans share a chunk.
- **To 5.1 and 5.2:** the judge is not Claude, and the ~100 human-verified pairs are not Claude-marked; a rubric for an answer that names the wrong product and for a same-polarity "Yes."
- **To 6.1 and 6.3:** the analysis rules A1 – A4 in the task's `rules.md`; report the trap fraction beside the reachable fraction (`evidence/partner-cosine.md`); the frontier leaves out Tier-1 repeats, or is computed on the static arm.
- **To 7.2:** `mu_hit.js` tier-2 mode reads a `paraphrase` field from the first 20 records; its probe file is 7.2's to build from this workload.
- **To P1:** the run names its run file and sets `CACHE_CAPACITY = round(0.25 × K)` of that file; the comment at `gateway/cmd/gateway/main.go:267-268` still gives the old meaning of `K`.
- **Open for the author:** the 30-row read can still be marked by the author (the sheet is `data/v1-draft/workload/author-read.csv`); if 3 or more rows break their rule, the stop rule applies.

**Progress, 2026-10-21:** items 3.3 and 3.5 are done (**ADR-012**, trail `docs/work/2026-10-20-policy-documents/`): 12 policy documents, 48 chunks, G5 in the gate. **Phase 3 exit is not met** (run on 2026-10-21: `make gate-corpus` stops, no workload yet); 3.4 and 3.6 are open; 17 `TODO(W8)` markers are open in `data-card.md`. 3.4 is next. **Carried into 3.4 and 3.6:** ADR-012's Consequences.

**Progress, 2026-10-20:** items 3.1 and 3.2 are done. 3.2 drew **152 products** (38 per department; TVs 13 +
headphones 25 after the pre-registered fallback step 1) and a **4,706-question pool** by one rule committed
before any run (**ADR-011**, trail `docs/work/2026-10-19-pqa-thick-tail-selection/`). The probe's own pools
reproduce exactly, and the selection is byte-identical across runs. **R2, the answerability rule, is a
pre-filter, not a label:** precision 35 % in a blind audit (a **model** audit, at the author's request) and 21 %
against ePQA, with a 97.5 % negative predictive value. **Phase 3 exit is not met:** no policy documents (3.3), no
workload (3.4), no G5 (3.5), no freeze (3.6); 19 `TODO(W8)` markers are open in `data-card.md`. 3.3 is next.

**Carried into 3.4 from 3.2 (ADR-011):** read the drafts only through `select_pqa.iter_selection`; **label again
every R2-answerable question that becomes a workload query** (a recorded model label, never Qwen or the Phase 5
judge), and **a sample of the R2-unanswerable ones** (NPV 97.5 % in the model audit but 93.5 % against ePQA, recall 4 / 12); expect about **410** (≈ 285 – 560) truly answerable of the 1,180, an input to `K`; the pool field is `r2_answerable`, a tag, not a label; spec questions the record cannot answer are a
**separate stratum**, never in the headline; never label strata with the probe's tokenizer ("Windows 7" and
"Windows 8" share a token set); only 127 policy questions are in the pool, "return key" is mis-tagged as policy,
and there is no shipping tag; `data/workload-v1.json`, the gate's default path, is **not gitignored** and will hold
PQA question text. The selected products split into 2 – 5 chunks each against 1 – 2 for the probe's pool: a C1
limitation, recorded in `data-card.md` §1.

**Progress, 2026-10-15:** item 3.1 is done. The builder checks the six source files by sha256, parses them against
the real field names, and stops on a bad parse; it writes `data/v1-draft/pqa/*.jsonl` and the manifest
`data/pqa-manifest.json` (hashes and counts only). Real run: 1,212,029 questions over 71,794 products, 4 skipped.
**Phase 3 exit is not met** (run on 2026-10-15: `make gate-corpus` fails, no corpus and no workload; 22 `TODO(W8)`
markers are still open in `data-card.md`). Items 3.2 – 3.6 were open (3.2 closed 2026-10-20, above).

**Found while closing 3.1, not yet items — each waits on the author's decision** (trail
`docs/work/2026-10-15-pqa-build-script/`, `review.md`, `evidence/live-run.md`):

- ✅ *Done by 3.2 (ADR-011).* **For 3.2:** read the interim only through `iter_interim`, and record the sha256 of `data/pqa-manifest.json` it
  consumed (`make pqa-verify` prints it). Write drafts to a fresh `data/v1-draft/products/` and refuse to run while
  `data/v1-draft/product-*.json` exist (open question 4, option A). The interim's `leaf` is metadata: it must not become
  `category` or reach embedded text. 3.2 owns the interim schema and rebuilds the manifest when it changes it.
- ✅ *Decided by 3.2: excluded, through 3.1's new `fields_conflict` flag.* **What the real data showed 3.2 has to decide on:** 78 asins (0.11 %) have product fields that differ between records
  (the builder keeps the first parsed record). No asin is in two leaves and no `question_id` repeats.
- **The 175 wrong-dataset files are not on this disk.** The builder looks for `data/v1-draft/product-*.json` on every build
  and found none. The guard stays; the danger it covers is not present today.
- **For 3.6:** the skip rules, "first parsed record wins" and surrogate replacement shape the question pool that `K` comes
  from. Write them into `data-card.md`; after the freeze a change needs a new `dataset_version`.
- **Stale prose, waiting for the author:** `docs/data-card.md:48` still says the builder downloads with resume (it does not;
  `make pqa-fetch` uses `curl -C -`); `CLAUDE.md` "Commands that work today" does not list `make pqa-fetch` / `pqa-build` /
  `pqa-verify`. The resume path of `pqa-fetch` has never run against the real host (the files were already on disk).
- **Workflow:** `docs/0. progress 16-10.md` is modified in the working tree by the author and is not part of 3.1; keep it out
  of the 3.1 commit. Ten older files in `experiments/` are not `ruff format` clean (pre-existing, untouched), and the
  `format-lint` hook formats a Python file on every Edit/Write.


| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 3.1 | **PQA build script**, replacing `fetch_corpus_v1.py`. ⚠️ **Write it against the bytes, not the readme** — the dataset's own documentation names fields the data does not use, and a builder written from it returns empty records **silently** | C1, C3 | Amazon-PQA | ✅ **Done 2026-10-15** — no ADR (no contract or frozen value changed; ADR-002 is used as written), trail `docs/work/2026-10-15-pqa-build-script/`. `experiments/scripts/build_pqa.py`, `make pqa-fetch` / `pqa-build` / `pqa-verify`. The Done-when's wording is **not amended**. The Done-when tests are `test_build_stops_on_readme_field_names_and_writes_nothing` (zero parse: exit 2, nothing written) and the manifest allow-list test (hashes and counts, no PQA text). On the six real files all four stops pass and two builds give one manifest hash. 103 tests, 75 hand mutants all caught. The manifest `data/pqa-manifest.json` was committed in `33a1a9d`; 3.2 replaced it with `741d52e3…` (`MANIFEST_VERSION` 2, the `fields_conflict` flag) | The script asserts a non-zero parse rate and refuses to write on zero; it emits a **hash manifest**, never the raw corpus |
| 3.2 | **Select into the thick tail.** Questions-per-product is skewed within a category and varies ~4× between categories; a uniform draw returns mostly single-question products, from which no stratum A or C pair can be built | C1 | Amazon-PQA | ✅ **Done 2026-10-20** — **ADR-011**, trail `docs/work/2026-10-19-pqa-thick-tail-selection/`. `experiments/scripts/select_pqa.py` and `answerability_check.py`; `make pqa-select`, `pqa-select-verify`, `pqa-audit-sheet`, `pqa-audit-score`, `epqa-fetch`, `pqa-answerability`. **The Done-when passes:** the rule, the 152-product funnel and the realised questions-per-product distribution are in `data-card.md` §1 and §3. The rule was committed (`ea63e5d`) before any live run and before ePQA was fetched; the probe pins (12 numbers) reproduce; the 152 records' digest is `d373c4b0…` on every run (the selection manifest's own hash also covers the selector file, so it is not the anchor). Fallback step 1 applied by the author (TVs 13 + headphones 25). R2's precision 35 % (a model audit, not human, by the author's choice) makes it a pre-filter; 3.4 re-labels. 75 new tests (58 selector, 11 answerability, 6 builder); `/ai-review` found 10 issues, all fixed (`review.md`) | The selection rule is recorded in `data-card.md`, and the realised questions-per-product distribution is reported with it |
| 3.3 | **Author the policy documents.** Per-category return *and* warranty windows that genuinely differ, ≥3 chunks each, and ⚠️ **opposing conditions in separate documents, not separate chunks** — a chunk-level split is invisible to the namespace, which is document-granular by design, and leaves all four conjuncts blind at once | C1, C2 | `v1` corpus model, condition-splitting, opposing conditions in distinct documents | ✅ **Done 2026-10-21** — **ADR-012**, trail `docs/work/2026-10-20-policy-documents/`. **12 documents** in the tracked `data/policies-v1/` (the laptops region split dropped by the pre-registered fallback), written to rules committed before any text (`c9a93f6`) and approved by the author. **The Done-when passes:** `make policy-check` gives 4 chunks per document and G5 0 of 12 (4 families split). W5 waived for the phones warranty pair (`/ai-review` F3); returns and warranty only, on a sampled audit (`evidence/policy-scope.md`); `/ai-review` 9 findings, all resolved | Every policy document yields ≥3 chunks and **no two opposing conditions share a `doc_id`**. Note this raises the count above 8: one category's return policy split into *opened* / *unopened* is two documents |
| 3.4 | **Workload generator.** Strata A / B-within / B-cross / C / D, Zipf popularity, and the validation/test split partitioned **by seed-question cluster**, never by pair, which would leak paraphrases | C1, C3 | `v1` corpus model, B-within / B-cross split | ✅ **Done 2026-10-22** — **ADR-013**, trail `docs/work/2026-10-21-workload-generator/`. `build_workload.py` builds **1,274 queries** (validation 622, test 652) from a model layer that Claude wrote under rules committed before any sheet (`98c4689`). Two builds give one manifest sha256 (`7ee717a8…`); `make workload-verify` and the structural gate (G3, G4, G5, the workload shape, the split files) pass. Strata A 761 · B-within 272 · C 150 · D 69 · B-cross 22; 94 unanswerable; 136 minimal-pair twins (56 and 80). **The Done-when passes:** the split is by unit, a union of whole clusters, so no cluster spans both splits. **`K` is per run file** (`interfaces.md` v0.15): 622 for validation and 652 for test, capacity 156 and 163, recorded at 3.6 (the whole file, 1,274 and 318, is the gate's input, not a run file). **Thin:** B-cross has 22 records, none within reach of τ ≥ 0.85; only 182 of 284 traps can fire (0.143 of records, against the trap fraction 0.2229); natural B-within traps are 10 of 272. **The 30-row read was done by Claude at the author's instruction, not by the author**, so it is not an independent check | Every query carries exactly one stratum and one split assignment; no seed cluster spans both splits |
| 3.5 | **G5 in `corpus_gate.py`.** `data-card.md` §7 requires five criteria; the code implements four. Structural, stage 1, beside G3 and G4 | C1 | condition-splitting, opposing conditions in distinct documents | ✅ **Done 2026-10-21, with 3.3** — ADR-012, trail `docs/work/2026-10-20-policy-documents/`. `check_g5` runs in stage 1 and fails any policy document naming a condition it does not declare. **The Done-when passes:** `test_g5_names_both_values_when_a_document_holds_both` and `test_the_gate_runs_g5_in_stage_1_and_stops_on_it`. Lexical, so the author's read is G5's other half | The gate fails a corpus where two opposing conditions share a `doc_id`, and names both |
| 3.6 | **Gate, freeze, hash.** Record `K` for each run file; derive `cache_capacity = round(0.25 × K)` | C1, C3, S1 | capacity ratio, `data-card.md` §7 ✅ **Done 2026-10-23** — ADR-014, ADR-015, trails `docs/work/2026-10-22-corpus-freeze/`, `docs/work/2026-10-22-g1-finding/`, `docs/work/2026-10-23-corpus-freeze-run/`. **G1 recorded as FAILED (21 of 50), not passed.** | The digest prints, every `TODO(W8)` in `data-card.md` §7 is filled, and no experiment runs against an unfrozen corpus |

### Phase 4 — Invalidation (C2)

**Exit:** editing a policy purges exactly its dependents from **both** tiers · an in-flight generation during an edit is discarded with `writeback_discarded: true` in the log · completeness and precision are reproducible from one script.

*Closed 2026-10-29. Built: C2's dependency map and blind purge (4.1), the epoch guard (4.2), tracking of every Tier-1 key (4.3), and the edit path with the update set (4.4).* ~30 h.

**Carried in from item 2.3 (ADR-009):** while the support gate is on it can hide a missed purge (the numeric arm refuses a stale "30 days" entry whose purge was missed), so the completeness check must run on the **gate-off arm** (item 2.4, done: `SUPPORT_GATE=off`) or read `dep:*` and `entry:*` state directly. **Carried in from item 2.4 (ADR-010):** a measured run starts on a cache it wrote itself (§H rule 11, checked by invariant I9). The flush tool refuses whenever `dep:` or `entry:` exist, and deleting `t2:` alone would leave dependency sets pointing at nothing, so **this phase defines the reset** that rule 11 needs.

**Carried in from item 3.6 (ADR-015):** the freeze recorded the lane-band counts and took no decision on them (`docs/work/2026-10-22-corpus-freeze/evidence/probe-checks.md`, U10; `v1` validation split). The closed default band reads 428 of 431 product-only queries as SPEC and 156 of 158 policy queries as POLICY. It reads only 27 of 33 stratum-D queries (a product *and* a policy) as POLICY, and 6 as SPEC. None is MIXED. The candidate band [0.20, 0.60) makes 24 queries MIXED: 12 are D, 9 are policy and 3 are product-only. **Why before 4.1:** the author asked on 2026-10-26 that it be settled first, and every Tier-2 entry carries the `lane` and `namespace` the rule wrote, which this phase's purge and reset run over. Item 4.0 owns it, and ADR-016 settled it on 2026-10-27.

**Progress, 2026-10-29 (later): item 4.4 is done and Phase 4 is closed.** The exit line was run on 2026-10-29 against `docs/work/2026-10-29-update-set/evidence/live3/` (`v1`, not citable, pressure 1–2):
- **A policy edit purges exactly its dependents from both tiers.** Each of the 10 policy edits had 4–11 dependents, and every one is gone from `t1:` and `t2:`. Exactness is 0.
- **An edit during a generation is discarded.** The 30 → 14 day edit landed mid-generation. The record lists the edited chunk and says `writeback_discarded: true`, with no key written.
- **One script reproduces the numbers.** `make update-set-score` gives byte-identical output (completeness 1, precision 0.695).

Also from 4.4: `dev-v0` is retired (the author, 2026-10-29), so Redis holds `v1` and `rag.config` defaults to it.

**Found while closing 4.4, not yet items:**
- **Ollama 0.33.2's llama-server prompt cache grows to 8 GB.** No `--cache-ram` is passed; 89 prompts took about 5.9 GB in a live run, and 116 of 130 prompts reused nothing. This breaks "memory is fixed when the runner loads", and `make env-check` does not see it. It needs a /bugfix (likely `LLAMA_ARG_CACHE_RAM=0`) and a decision record **before any Phase 7 measurement**. Qwen's vision encoder (`--mmproj`) is also loaded and never used. ✅ **Resolved 2026-10-29** — ADR-017, `interfaces.md` v0.22, trail `docs/work/2026-10-29-ollama-prompt-cache/`.
  - **The fix:** the prompt cache and the context checkpoints are off. `make ollama-env` sets them, and must run after every reboot. `make env-check` fails while either is on.
  - **The measurement:** over 300 distinct prompts the runner's footprint rose 1 MB (`v1`, not citable).
  - **The vision encoder** stays: 855 MB, fixed at load.
- **Found while closing that bugfix: the runner's batch size is not fixed** (trail design §4 F3). Ollama gives the runner `-b 512` or `-b 1024`, the cause is not known, and `env-check` neither pins nor records it. It changes prefill speed and compute memory. Decide before any Phase 7 measurement.
- **`make demo-reset` runs `FLUSHALL` and re-ingests `dev-v0`**, so one run wipes `v1` from Redis. `make demo` still assumes `dev-v0`. **Guarded 2026-10-29:** `demo-reset` now refuses, before it changes anything, while Redis holds any corpus chunk whose `dataset_version` is not `dev-v0`. Tested live: with `v1` in Redis it refused, and Redis was left untouched. `seam-check` and `support-check` run on `v1` since 2026-10-29 (trail `docs/work/2026-10-29-dev-v0-live-checks/`); moving `make demo` to `v1` is still open (Phase 8).
- **An unknown `product_id` is rejected nowhere** (found 2026-10-29, trail `docs/work/2026-10-29-dev-v0-live-checks/`). A scoped retrieval for an ID that is not in Redis returns nothing, or policy chunks only, and no layer raises an error (`server.py`, `retrieve.py`, `/ask`). `interfaces.md` §B v0.8 does not say what should happen. Every `v1` workload `product_id` exists in Redis today (622 and 652 queries, 115 products each, checked 2026-10-29). Suggestion: a pre-run check in the Phase 7 harness.
- **No item owns RQ3's swept TTL baseline** (`Final_Proposal.md` RQ3).

**Progress, 2026-10-29:** the /bugfix on the Redis index lifecycle is done (no ADR, `interfaces.md` v0.20, trail `docs/work/2026-10-29-redis-index-lifecycle/`). The Go Redis tests run on their own server on port 6390 and can no longer drop `idx:corpus` or `idx:cache`; the gateway serves only a complete `idx:cache`; a Tier-2 search error makes a run inadmissible (run rule 12). 4.4 is the last open item, and the exit is still not met, for the three reasons below (checked again on 2026-10-29).

**Progress, 2026-10-28:** items 4.0 (ADR-016), 4.5, 4.1, 4.2 and 4.3 are done; 4.4 is the last open item. The exit is not met: nothing carries a real edit into the gateway (`Invalidate` has no caller outside tests; 4.4). `writeback_discarded: true` is in a real gateway log, but the edit there was an epoch advance, not a policy edit (4.4). No completeness / precision script exists (4.4). A /bugfix on the Redis index lifecycle (Go tests share one server with the live indexes; a possible `idx:cache` start-up race) is next, before 4.4.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 4.0 | **Decide the MIXED lane before C2 is built.** The lane band is closed by default (`LANE_SIGMA` = `LANE_SIGMA_HI` = 0.20). So a question about a product *and* a policy is read as POLICY, and its `product_id` is not in the cache key (`reuse/lane.go`). ADR-015 recorded the `v1` counts and acted on none. Choose one: **(a)** pin one band, chosen on the validation split only, and run MIXED as an on/off arm like the support gate, not swept; **(b)** keep the band closed and report stratum D (69 of 1,274 queries) as a limitation, with its counts. Neither choice removes the failure: a band on the policy fraction cannot tell D from policy (8 of 33 D queries sit at 0.8, as do 99 of 158 policy queries), and 6 of 33 D queries retrieve no policy chunk at all | C1 | ADR-015's carried counts, `reuse/lane.go`, the unequal-tuning threat (`Final_Proposal.md` §9.4) | 3.6 ✅ · ✅ **Done 2026-10-27** — **ADR-016**, no trail (a decision, not a task). Option (a): the band is pinned at [0.20, 0.60), MIXED is an on/off arm, and configuration 4 runs three arms. The frontier sweeps two parameters (τ, θ), one served while F-K is open. Item 4.5 adds the arm field to the record | A numbered ADR in `decisions.md`, dated, **before** 4.1 starts and before any run, says which of (a) or (b) the study uses; pins σ_lo and σ_hi if (a); says how many parameters the frontier sweeps after it; and says what it invalidates. The test split is not read to choose |
| 4.1 | **Dependency map.** `dep:{chunk_id} → SET(entry_id)` in the `noeviction` region, in-process copy-on-write index, single writer goroutine, purge hitting both tiers via `t1_key` | C2, S4 | inherited decision, invalidation under load, `interfaces.md` §E | 3.6 ✅, 4.0 ✅, 4.5 ✅ · ✅ **Done 2026-10-28** — no new ADR (`interfaces.md` v0.17), trail `docs/work/2026-10-27-dependency-map/`. `deps/` built: one writer, `dep:*` + `entry:*`, tombstones on both hit paths, Tier-1 compare-and-delete. Shown by tests through the Go call `Invalidate` on test chunk IDs; no live edit reaches the gateway yet (4.4) | A policy edit purges its dependents from `t1:` and `t2:` and leaves unaffected entries alone |
| 4.2 | **Epoch-guarded write-back**, and make it set `writeback_discarded` — the field is logged today and **never assigned** | C2, C3 | `interfaces.md` §E, evaluation log | 4.1 ✅ · ✅ **Done 2026-10-28** — no new ADR (carries out ADR-008; `interfaces.md` v0.18), trail `docs/work/2026-10-28-epoch-guard/`. The epoch is one integer in the file `DATASET_EPOCH_FILE`; `rag.server` stamps it read-first, the gateway discards a write-back on any mismatch, and the deps writer purges a registration that arrives after an advance (`LateDiscards`). Shown by tests and by a live run (`make epoch-race-check`, yellow pressure, not citable) where an epoch advance stood in for the edit | Forcing the race produces `writeback_discarded: true`; the stale answer never reaches the cache |
| 4.3 | ⚠️ **Fix the promoted-`t1_key` bug before it detonates.** Tier-1 promotion mints a second, untracked `t1_key` per entry — harmless *only* while capacity is unbounded and C2 is unbuilt. Phase 3 bounds capacity and this phase ships C2; **both preconditions expire here** | C2, S3 | needs a decision: track multiple `t1_key`s, or drop promoted keys on purge | 4.1 ✅ · ✅ **Done 2026-10-28** — no new ADR (`interfaces.md` v0.19), trail `docs/work/2026-10-28-promoted-t1-keys/`. Decided: **track** every Tier-1 key in a cache-owned set `lru:t1keys:{entry_id}`; trim and purge share one compare-then-delete script; a promotion is written only while `t2:` exists. Also fixed: a Tier-1-only entry's orphan on eviction, and (from the build's RCA) the RAG read path searching a half-built index (`rag/store.py`). Shown by tests | A purge removes every Tier-1 pointer at the entry, promoted ones included; an eviction leaves no orphan |
| 4.4 | **Update set**, ~20 edits, balanced `substantive` / `cosmetic`, so over-invalidation is measured rather than assumed. **Also owns how an edit reaches the gateway** (item 4.1 built only the Go call `Invalidate`; nothing else calls it). **Its design must test the edit order** (new text, then advance the epoch, then invalidate), because a wrong order lets a stale write-back pass with no trace (item 4.2, design §3 failure mode 10). *Proposed 2026-10-28, decided in 4.4's design:* the edit script writes the new chunk text, then advances the epoch (4.2), then calls a gateway HTTP endpoint (e.g. `POST /invalidate`). The call is synchronous and its reply lists the purged `entry_id`s, so a failed call stops the run instead of leaving a missed purge. Not chosen: Redis pub/sub or keyspace notifications (a message nobody is listening for is lost with no error, and completeness drops silently); a file watcher on `data/` (a changed file does not name the changed chunk) | C2 | `v1` corpus model | 3.6 ✅ · ✅ **Done 2026-10-29** — no new ADR (`interfaces.md` v0.21), trail `docs/work/2026-10-29-update-set/`. 20 labelled edits on `v1` (10 `substantive`, 10 `cosmetic`, the author's review 2026-10-29); the edit path `rag.edit` (new text, then the epoch, then `POST /invalidate`, which replies after the purge); `make cache-reset` for rule 11. Three live runs on `v1` (not citable): completeness 1, exactness 0, precision 0.68–0.70; `make update-set-score` is byte-reproducible. `dev-v0` retired by the author the same day | Completeness and precision computed from one script against the labelled set |
| 4.5 | **Name the MIXED arm in every record** (ADR-016). Add a field to the evaluation record (`interfaces.md` §H) that says which lane band the request ran with, as ADR-010 did for `support_gate`, and fix the two comments ADR-016 lists as stale (`reuse/lane.go:94`; `cmd/gateway/main.go`, "the operating point belongs to the sweep"). **Taken first, before 4.1**, because 4.2 edits the same record. The lane code itself is built and tested (`reuse/lane.go`); only the record is missing | C1, C3 | ADR-016, ADR-010, `interfaces.md` §H | 4.0 ✅ · ✅ **Done 2026-10-27** — ADR-016, trail `docs/work/2026-10-27-mixed-arm-field/`. `mixed_lane` on every record (`interfaces.md` v0.16, I10–I12); `bandFromEnv` refuses any other band at start. Shown by tests in two halves (env → band, band → record); no live gateway run | Every record names the lane band it ran with, so a reader tells the MIXED-on arm from the off arm without the run's environment; a run with `LANE_SIGMA_HI=0.60` and a run with the default band log different values |

### Phase 5 — Judging, δ, and the figure pipeline

**Exit:** judge-to-human and reference-anchored-against-reference-free agreement are both recorded · δ is finalised against the measured noise floor · `make figures` regenerates every figure from `raw/` on a clean checkout plus the raw archive (`raw/` is gitignored, ADR-005).

*The judge harness and the figure generators do not exist; `experiments/README.md` claims both do.* ~25 h.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 5.1 | **Judge harness** — does not exist. Frozen prompt, judge model ≠ generator, offline batch with the generator unloaded, verdicts deduped by `answer_sha256`, reading Phase 1's answer store | C1, C3 | scope reduction | ✅ 1.5, ✅ 3.6 | Judge model id and prompt version are frozen and recorded **before** any frontier is computed, and per-configuration cost is measured before scaling to five |
| 5.2 | **Labelling ablation** on ~100 pairs under both schemes; agreement reported **by containment bucket** | C1 | validity is method | 5.1 | Both agreement numbers recorded; circularity bounded or quantified |
| 5.3 | **Finalise δ** against the measured judge error | C1 | false-hit budget | 5.2 | δ is fixed and clearly exceeds the noise floor, or the gap is reported as the reason it cannot be |
| 5.4 | **Figure generators** — do not exist. `make figures` invokes an absent script with no guard | C3 | `raw/` is write-once | 5.1 | `make figures` regenerates every figure from write-once `raw/` on a clean checkout **plus the raw archive** (`raw/` is gitignored since 2026-10-06: it holds PQA-derived text and the remote is public, ADR-005), and never the reverse |
| 5.5 | **Cap the request size on `/ask`.** The gateway decodes the body with no limit today (`httpapi/handler.go`), so one very large request can take a lot of gateway memory. Decided 2026-10-27: this is the only input guard built; a per-client rate limit and a filter for meaningless questions are not (see 8.2). Optional: if it is not built, 8.2 reports it as a limitation | S2 | `interfaces.md` §A | Phase 4 exit | A body over the limit is refused with a 4xx on the same path as a malformed request, before any record exists, so no new outcome enters the evaluation record; the limit is written in `interfaces.md` §A and is above the longest question in the frozen `v1` workload, checked against the files |

### Phase 6 — Headline B, the frontier

**Exit:** Headline B exists on the held-out split with both isolation controls · the B-within against B-cross split is reported · RQ2a is reported beside it with its own interval.

~30 h.

**Carried in from item 2.4 (ADR-010):** a configuration-4 run is `(config_id, mutation, support_gate)`, and every reader of `support_gate` also filters `config_id ∈ {4, 5}`. Hit rate, tier mix, band share and *false hits by cause* are reported **per arm**. *Decisions changed by provenance* is the **3 ⋈ 4-off** join (provenance alone); 3 ⋈ 4-on mixes in the support gate. A per-request join between 4-off and 4-on is valid only on the static-cache arm (6.3). The second pre-registered null is read from the gap between the arms' hit rates, with the share of `SUPPORT` refusals whose `candidate_entry_id` repeats (the `k=1` effect of ADR-009) reported beside it. A measured run starts on a cache it wrote itself (§H rule 11, invariant I9).

**Carried in from item 4.0 (ADR-016):** a configuration-4 run is also identified by its MIXED arm, read from the field item 4.5 adds. Configuration 4 runs three arms (gate off and MIXED off, gate on and MIXED off, gate on and MIXED on), so the gate's share and the MIXED lane's share are read one step at a time. Configuration 5 runs gate on and MIXED on. Stratum D is reported per arm.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 6.1 | ⚠️ **Pre-register the sweep before running it.** `Final_Proposal.md` §9.4 books this debt in its own words: θ's range is *"not stated anywhere"*, τ's granularity is unstated, the lane-band bounds are unspecified, and *"the best fixed threshold"* has **no written selection objective** | C1, C3 | `Final_Proposal.md` §9.4 books the debt but names no home for it — see P1 in `decisions.md`. The lane-band bounds are pinned by ADR-016 (item 4.0): [0.20, 0.60), run as an on/off arm, not swept | 5.3 | All four are pinned in `decisions.md`, dated, **before** a single sweep point runs |
| 6.2 | **Five configurations at `mutation: off`**, with configuration 4 as **three arms** (ADR-016): gate off and MIXED off, gate on and MIXED off, gate on and MIXED on. Sweep on validation, report on held-out test, Wilson intervals | C1 | config × mutation grid, the support gate, ADR-016 | 6.1 | Every point carries its interval; no threshold was chosen on the test split |
| 6.3 | **Isolation controls.** Static-cache ablation — **non-negotiable** since retiring the inline counterfactual made decisions-changed-by-provenance a cross-configuration join valid only on that arm — and stratified reporting | C1 | validity is method, retiring the unfiltered phase, B-within / B-cross split | 6.2 | Both frontiers reported; disagreement between them reported as a finding rather than reconciled |
| 6.4 | **RQ2a — the residual.** Same-evidence, opposite-condition pairs surviving every gate, on the B-within stratum built to contain them. Reported **beside** the headline, never inside it | C1 | the support gate, condition-splitting | 6.2 | RQ2a has its own Wilson interval and is stated as the boundary of the claim |

### Phase 7 — Headline A, capacity (co-hosted)

**Exit:** Headline A exists with every contributing run in green pressure · `h*` is computed from both measured service rates and shown to lie outside the reachable range **at the lower bound** · every figure regenerates from `raw/` · every co-hosted number carries its interference measurement.

> **Read with ADR-001:** "at the lower bound" holds for the μ_hit leg only; μ_gen for `h*` is measured with no load generator, and every co-hosted p95 carries k6's concurrent CPU.

*Run under the co-hosted régime described below. Nothing here is scheduled as if a second machine will appear.* ~30 h.

**Carried in from item 2.4 (ADR-010):** compare μ_hit with the gate on against off **on a probe set the gate admits**, so both arms serve the same hits. The arms otherwise differ in hit mix and in the background writes each hit triggers (`BumpHitCount` and the Tier-1 promotion), so an unmatched comparison is not the gate's cost alone. The gate itself costs about 30 µs per judged candidate (a benchmark, not a measurement of the system). Every run starts on a cache it wrote itself (§H rule 11).

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 7.1 | **Redundancy × load sweep**, co-hosted. Three Zipf skews, cache-on against cache-off, ≥3 repetitions per point, pressure sampled at ≥1 Hz | S1, S2 | measurement validity as amended, capacity ratio | 1.6 ✅, 6.2 | Curves exist at every point and the **hit-rate spread across the three skews is non-zero** — a flat spread means capacity was mis-derived, not that the cache does not work |
| 7.2 | **μ_hit in both modes, reported as a lower bound.** Tier-1 and Tier-2 are different ceilings and the tier mix is itself a function of redundancy, so the second term of λ_max is evaluated **per sweep point**, never once from an average. `nomic-embed-text` also serves one slot (resolve-f1, U7), so the embedding round-trip may be what bounds Tier-2 μ_hit | S1 | capacity ratio, `interfaces.md` §F | 7.1 | Both figures recorded with the co-hosting bias direction stated; `h*` at the lower bound compared against the reachable range of `h` |
| 7.3 | **Measure the Tier-1 promotion effect on tier mix** — a built, unmeasured throughput lever, and the cheapest remaining way to raise μ_hit | S1 | — needs no new decision; the code shipped 2026-09-10 | 7.1 | The tier mix with promotion on and off is reported at matched workload |
| 7.4 | **Invalidation under load**, fast-path p99 and reader stall while purges fire | C2, S4 | invalidation under load | 4.2 ✅, 7.1 | The read fast path does not stall behind an invalidation, or the stall is measured and reported |
| 7.5 | **Saturation analysis and freeze.** Shed rate and permit-queue depth at saturation; goodput never counts sheds. State which μ_gen is reported: the permit also covers the Answer RPC and write-back, so a gateway-measured μ_gen ≤ Ollama's (resolve-f1, N7) | S1, S2 | admission control, `Final_Proposal.md` §3, ADR-003 | 7.1, 1.1 ✅ | Headline A exists; measured λ_max plotted against the model; the queue budget q was pre-registered before the first saturation run and is recorded per run (ADR-003); all results frozen and every figure regenerable |

### Phase 8 — Write-up and defence

**Exit:** a submission-ready thesis and a rehearsed defence.

~40 h.

| # | Item | Discharges | Rests on | Unblocked when | Done when |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 8.1 | Chapter skeleton, background and related work, architecture chapter | — | — | 6.4 | 50 % draft |
| 8.2 | Evaluation chapter built around the two headline figures, with the limitations stated rather than defended — including everything measured co-hosted, that the backend serves **one generation stream** (ADR-003), and that no authentication, per-client rate limit or filter for meaningless questions is built (decided 2026-10-27: a per-client limit would throttle the single-client load generator, and the filter needs a classifier, the scope the bypass classifier's removal closed) | — | ADR-003 | 7.5 | Full draft to advisor, **and** the admission-control text frames the pool as queueing and shedding at one slot, never as a memory bound (ADR-003 — the reframing the W5 spike's no-go branch required) |
| 8.3 | Revision, slides, rehearsal. **Buffer** | — | — | 8.2 | Submission-ready and rehearsed |

---

## Measuring without a second machine

> **Amended by ADR-001 (2026-10-07), which recorded the decision this section asked for.** The lower-bound
> argument below holds **for the μ_hit leg only**. `h*` also falls as μ_gen rises, so a μ_gen measured
> co-hosted is anti-conservative; item 7.5 measures it with a sequential client and **no** load generator
> (⟦PENDING: the author confirms⟧). Co-hosted p95 is **not a bound**, and the 1.6 footprint is CPU share, **not
> an interference measurement**. Read every "lower bound on `h*`" in this file (Phase 7's exit, item 7.2, this
> section), in `CLAUDE.md` (`:162-167`) and in `Final_Proposal.md` (§7 `:345`, §9.4 `:460`) through ADR-001's
> per-quantity table. Those other files are unedited.

Confirmed with the author on **2026-09-21: no second machine exists and none is dated.** The
original validity rule required off-box load generation, and the risk register's own mitigation is
*"measure and report generator interference."* This is that, made concrete. **It needs its own
entry in `decisions.md`** — the alternative is a silent deviation from a frozen decision, which is
the failure mode this repo exists to prevent.

**Two cases, and they must not be lumped together.** The 2026-09-06 run that drove memory pressure
to *urgent* was the **Tier-1 μ_hit probe at 400 rps**, saturating an ~8000 req/s path. The main
capacity sweep is a different regime: μ_gen ≈ 0.19 req/s caps λ_max at ≈ 16 req/s even at the best
reachable hit rate, so the sweep offers ≲ 16 req/s and a generator at that rate costs little.
Whether "little" is small enough is **item 1.6's measurement**, not an assumption.

**Why the headline claim survives co-hosting.** S1's claim is an *inequality*, not a value: that
`h* = μ_hit / (μ_gen + μ_hit)` lies **outside** the range of `h` the workload reaches (≈ 0.988), so
the system is generation-bound throughout its operating range. `h*` is monotone increasing in μ_hit,
and **co-hosting depresses μ_hit** — the generator starves the embedding server that bounds the
Tier-2 hit path. A co-hosted measurement is therefore a *lower* bound on μ_hit and so a *lower*
bound on `h*`. At the already-measured co-hosted 61 req/s, `h* ≥ 0.9969 > 0.988` and the finding
stands; an off-box run could only raise μ_hit and strengthen it. **A bound is sufficient for the
claim being made** — and that is stated in the ADR rather than left for an examiner to find.

What is **not** rescued, and is reported as a limitation rather than argued around:

- Any figure presented as a **ceiling** rather than a bound — the Tier-1 μ_hit number in particular.
- Latency percentiles at high offered rate, where generator and system under test contend for the
  same cores. Either report the generator's concurrent CPU alongside p95, or restrict p95 claims to
  the rates where item 1.6's footprint measurement shows headroom.
- **Two different margins must not be conflated.** *"μ_gen ≪ μ_hit by two to three orders of
  magnitude"* is about `μ_gen` against `μ_hit` and is **correct** (0.19 against 61 is ~320×). The
  margin over the capacity-ratio falsification trigger is a **different** comparison and is only **3.8×**
  (61 against ~16 req/s). Keep them apart wherever both appear: the first licenses `h* > 0.99`,
  the second is the one a co-hosted lower bound has to clear, and it clears it with far less room.
  `22-load-conversion.md` already states the 3.8× figure; the proposal's own wording
  (*"observable only if μ_hit ≤ ~16 req/s"*) is accurate and needs no change.

---

## Why the phases moved

The schedule this replaced was written before the code existed. The codebase has since run ahead of
it in some places and stayed empty in others, so the old boundaries no longer describe the work.

| | Old plan | Here | Because |
| :--- | :--- | :--- | :--- |
| Systems hardening | Phase 5, a build phase | **Not a phase** | `admission/`, `coalesce/` and `telemetry/` are built and tested. It becomes verification inside Phase 7 |
| Support gate | absent | **Phase 2** | Decided after the old plan was written, and it is the highest-value unbuilt item for both halves of the objective |
| Instrument integrity | absent | **Phase 1** | `httpapi/` had 856 lines and zero tests; F1 had no ADR and no detector |
| Corpus | one row | **Phase 3** | Four jobs, and the source changed to Amazon-PQA after the old plan was written |
| Judge, workload generator, figures | assumed to exist | named as **unbuilt** | None of the three exists; `make figures` invokes an absent script |
| Invalidation (C2) | Phase 2 | **Phase 4** | Unchanged in substance, but it now carries the promoted-`t1_key` fix, which its own preconditions expire on |

---

*Cross-references: `Final_Proposal.md` §3 (scalability clauses), §5 (contributions), §9 (evaluation
design), §12 (drop order — authoritative), §13 (deliverables — authoritative) · `data-card.md` §7
(corpus gate — authoritative) · `contracts/interfaces.md` §E, §H · `decisions.md` (inherited state,
and every decision taken from 2026-09-22 on).*
