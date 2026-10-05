# Design review — httpapi-tests

**Reviewer:** `design-reviewer` (opus), 2026-10-04. The review was read-only: no model was loaded
and no code was run. **CONFIRMED** means checked against the code, or against the grpc-go v1.83.0
source in the module cache. **PLAUSIBLE** means reasoned only. The reviewer has no write tool, so
Claude saved its report here as returned, and added the **Resolutions** section at the end.

**Verdict: sound with changes.**

- **The harness is right.** It has one 8-method interface, the RAG service and the embedder faked
  at the wire, a real Logger, and U5 (a). The six outcomes each get a response assertion and a
  record assertion. Checked against the code, every mutation M1–M10 is caught by the test it
  names. M1 and M7 are caught by a deadline expiring, not by an assertion.
- **No blocker.** There are ten should-fix items. Most are fixture rules or ordering statements.
  They have to be in `design.md` before any code exists, because the tests are immutable once
  written. The two that matter most:
  - **S1:** a fixture must satisfy every reuse conjunct except the one under test. Otherwise
    Phase 2 has to rewrite the central test.
  - **S2:** three degradation tests can pass without the degradation ever happening, and one
    of them goes hollow silently under 1.3.
- **On the spec's findings:** F-A is broader than stated, F-D is worse on the client side, and
  F-F is mis-described. There are five new findings, F-G to F-K. F-G and F-K are the substantive
  ones.

## Findings on the design, most severe first

| # | Sev. | Finding | Check | Proposed resolution (author decides) |
| :---: | :---: | :--- | :---: | :--- |
| **S1** | should-fix | **Tier-2 fixtures are unspecified, and the obvious ones break under Phase 2 or under the θ conjunct.**<br>• Today a hit is served on similarity ∧ namespace. Containment is "computed but not consulted" (`handler.go:293-295`, `lane.go:286`).<br>• The claimed rule has four conjuncts, including `overlap ≥ θ` and `support` (`Final_Proposal.md:150`).<br>• Phase 2 puts the support gate on this exact path (`super-plan.md` 2.1–2.4), and 2.3's `CONTAINMENT` cause implies containment becomes a conjunct.<br>• §3 and §4 specify neither the overlap between the seeded entry's sources and the fake's `chunk_ids`, nor what `texts` contains. A TIER2_HIT fixture with generic `texts` (`"text 0"`), or with overlap < 0.6, passes today and flips to MISS later. That forces a change to an immutable test outside the two §5 declares.<br>• `TestBelowTau…` has the same gap. If its entry sits in another namespace, namespace explains the MISS as well as τ does. Once 1.3 moves the τ check into `DecideLane` (`lane.go:295`), the test would pass with τ never exercised | CONFIRMED against the code and the proposal; the Phase-2 effect is PLAUSIBLE | **A fixture rule in §3:** every Tier-2 fixture satisfies **every** conjunct except the one under test:<br>• `retrieve(q).chunk_ids ⊇ entry.source_chunk_ids` (overlap 1.0);<br>• the seeded answer is a verbatim substring of `texts[0]`, with no numerals, or with every numeral and its unit present in the text;<br>• SPEC lane, with `product_id` set;<br>• below τ: same namespace, sim ≤ τ − 0.05.<br>§5 names Phase 2 as "must not change these outcomes" |
| **S2** | should-fix | **The degradation tests can pass without degrading.**<br>• With an empty cache, `tryTier2` returns at `cascade.go:88-90`. That is before it reads `retrieved` (`:110`) and before the scoped search (`:132`). So `TestRetrieveFailure…`'s MISS is explained by the empty cache alone, and an error injected only on `NearestTier2InNamespace` never fires.<br>• An error injected only on `NearestTier2` does fire today. But 1.3 removes that call, and afterwards the test passes on an empty cache while asserting nothing, with no compile error and no failure | CONFIRMED | **Each degradation test seeds a would-be TIER2_HIT** (per S1), so the MISS can only be explained by the injected failure.<br>The search-failure test injects on **both** search methods and asserts, through a counter in the fake, that an injected error was actually returned at least once. That holds before and after 1.3 without naming either method.<br>The retrieval-failure test still leaves F-E's fields unasserted |
| **S3** | should-fix | **ABANDONED is deterministic only if B's `Ask` returns before A releases the permit.**<br>• The queued `select` (`pool.go:110-115`) picks uniformly among ready cases. If A releases first, B may take the permit, call `Answer` on a cancelled context, and be logged GENERATION_FAILED through F-A. That is a roughly 50 % flake that looks like F-A.<br>• B must also be a **different question**. With the same key, B becomes a follower blocked on `<-c.done` (`coalesce.go:47`), which ignores B's context, so `Queued()` never reaches 1.<br>• B's record cannot be matched by `request_id` as §3 proposes, because B's response is empty | CONFIRMED | §4 row:<br>1. B is a distinct question.<br>2. Wait for `Queued()==1`, then cancel B.<br>3. **Join B**, then assert.<br>4. Release A, then join A.<br>Multi-request tests match records by `query_raw` |
| **S4** | should-fix | **§8's cleanup order closes the Logger without joining the `Ask` goroutines the test spawned.**<br>• A `Log` that races `Close` panics with "send on closed channel" (`evallog.go:133-137` against `:155-158`).<br>• In production, net/http recovers a handler panic. Here `Ask` runs on a goroutine the test spawned, so the panic kills the whole test binary and hides the failure that triggered cleanup.<br>• §3's hooks wait only on a test channel, and grpc's `Server.Stop` does not wait for handlers (`server.go:1988-1990`, v1.83.0), so such a hook leaks. `impact.md` S9 required selecting on the stream context, and the design dropped that | CONFIRMED | **Cleanup order:** release the hooks → `Stop` the gRPC server → join every `Ask` goroutine under a deadline → close the embed server → `Close` the Logger.<br>Every hook selects on *release* ∨ `stream.Context().Done()` |
| **S5** | should-fix | **`TestTier1LookupErrorIs500` pins half of F-B's likely fix.** The handler's own rule is that a cache outage costs hit rate, not availability (`handler.go:236-238`, `cascade.go:70-73`). An F-B bugfix may degrade a Tier-1 error into the cascade rather than return 500. "Exactly one record" is the invariant; the 500 is a choice that belongs to F-B | CONFIRMED by reading | Assert exactly one record and `Counters.Requests == 1`. Either drop the 500 assertion, or name the test in `approvals.md` as F-B-sensitive |
| **S6** | should-fix | **The MISS test's epoch assertion invites a fixture that Phase 3 will legitimately reverse.**<br>• To tell "Tier-2 `dataset_epoch` = Answer's" apart from "= Retrieve's", the two RPCs would have to return different epochs.<br>• That is exactly the mid-flight edit the epoch guard must **discard** (`interfaces.md:388-390`, invariant 3).<br>• Which epoch Tier 2 stores is Phase 3's decision | CONFIRMED; the Phase-3 effect is PLAUSIBLE | Retrieve and Answer return the **same** non-zero epoch. Assert `dataset_epoch_at_retrieval` == Tier-2 `dataset_epoch` == that value |
| **S7** | should-fix | **Nothing reads back the partition the Tier-2 write path assigns.**<br>• `TestTier2Hit…` seeds a hand-chosen `Namespace` and `Lane`, and the MISS test's repeat is a Tier-1 hit. Nothing checks that what a MISS writes (`handler.go:409-410`, `:436-437`) can then be served to a paraphrase. A self-consistent seed passes even if the write path partitions wrongly, which would show up in a run as a silent false-miss rate.<br>• The MISS test also never asserts that both tiers store **Answer's** `source_chunk_ids`, the field both contributions key on (`interfaces.md:351`). With a fake that echoes Retrieve's IDs, it could not tell the two apart anyway | CONFIRMED | **Add a round-trip test:** a MISS on *q*, then a paraphrase *q′* (same product and retrieval, cos ≥ τ + 0.05) gives TIER2_HIT with the MISS's `entry_id`. Wait on the second `Put` for the promotion.<br>The fake `Answer` returns `source_chunk_ids` ≠ the IDs it was given (drop the last one, which obligation 3 allows), and the MISS test asserts that both tiers hold Answer's set.<br>New mutation **M12**: omit `Namespace` from the `PutTier2` entry. Stable under 1.3, and under Phase 2 given S1 |
| **S8** | should-fix | **Coalescing across `product_id` is untested.** `coalesceKey = t1Key` includes the product (`handler.go:366-370`). If it regressed to the normalized question alone, the same question about two products would share one generation: A's answer would be served for B, logged as an ordinary coalesced MISS. `impact.md` listed this, and the design dropped it | CONFIRMED | **M11** and one test: `admission.New(2,0)`; the same question under two `product_id`s, concurrently; wait for `InFlight()==2`. Expect two `Answer` calls and two `entry_id`s. Under the mutation, `InFlight` never reaches 2 and the deadline fails the test |
| **S9** | should-fix | **The join between response and record is not asserted on every served path.**<br>• `request_id` is §H's join key (`interfaces.md:428`), and `answer_sha256` is the judge's dedupe key (`:475`). Only SHED checks the first, and only TIER1_HIT the second.<br>• No test checks `run_id`, `config_id`, `mutation`, or `stratum` from `X-Thesis-Stratum` (`handler.go:571-576`). Stratum is the key for per-sub-stratum reporting, and its offline fallback is no longer exact under product-scoped keys (`evallog.go:68-72`).<br>• Tests with several requests lack `askOnce`'s check that the record count equals the number of `Ask` calls (`impact.md` S2) | CONFIRMED | In both helpers:<br>• on every 200, the record's `request_id` == the response's, and the record's `answer_sha256` == sha256 of the response's `answer`;<br>• every request sends `X-Thesis-Stratum`, and every record echoes it, along with the run identity and `product_id`;<br>• record count == number of `Ask` calls |
| **S10** | should-fix | **The design does not say where the immutability boundary runs between scaffolding and assertions.** `cacheStore` will grow: Phase 3 needs an epoch read and dependency writes on this path. Each new method forces an edit to `fakeStore` in a `_test.go` file. §2 covers the interface shrinking under 1.3, not growing | PLAUSIBLE (Phase 3 not designed) | Record the rule in `approvals.md`:<br>• `harness_test.go` (fakes, helpers) is scaffolding. It may gain behaviour for new seams, with a note in the task that adds them.<br>• The assertions in `ask_test.go` fall under the normal immutability rule.<br>The plan's split into two files already supports this |
| N1 | note | **The mutation table checks out.** Each of M1–M10 is caught by the named test as specified. M1 is caught because `Waiters(t1Key)` never reaches 3, and M7 because the wait for the promotion times out. Both depend on the deadline **failing** the test, as §8 says. The fakes should also be **strict**: unknown embed input → 500, and `TopK != 0` → error (`handler.go:30`). That makes the `search_query: ` prefix and the `top_k` plumbing checked behaviour at no extra cost | CONFIRMED | Add M11 (S8) and M12 (S7). Make the fakes strict |
| N2 | note | **Similarity margin.** The embed client narrows to float32 (`embed/client.go:98-101`), the fake computes cosine in float64, and Redis computes it in float32. `impact.md` S10's margin is missing from §3 | CONFIRMED | §3: no test similarity within 0.01 of τ |
| N3 | note | **The SHED test's `permit_queue_depth: 0` cannot discriminate.** At `pool(1,0)` the value is 0 whether it is set from `Queued()` or never set at all | CONFIRMED | Optional: use `pool(1,1)` with C queued, and assert that B's value is 1 |
| N4 | note | **A non-null `source_overlap` on TIER2_HIT asserts §A** (`interfaces.md:120`, `:133`: null only when the cascade did not run). It does not assert U6's counterfactual | — | Cite §A in §4, so that 1.3 reads nulling it as a contract change |
| N5 | note | **The follower's `t_generate_ms: null` is asserted without the decision `impact.md` S13 asked for.** Null is a defensible reading of §H's "null unless generation ran" (`interfaces.md:463`). But that reading is recorded nowhere, and it makes a follower's wait read as gateway overhead (`:488`) | — | Record the decision in §4, or assert only that the leader's value is non-null |
| N6 | note | **`impact.md` correction 5 is only half applied.** `approvals.md` names the two new tests, but not the existing `telemetry/evallog_test.go:69`. That test asserts the `similarity_only_decision` key is present, and 1.3 must change it | — | Name it there, or leave it explicitly to 1.3's spec |

## On the spec's findings, and new ones

| # | Sev. | Finding | Check | Proposed resolution |
| :---: | :---: | :--- | :---: | :--- |
| F-A | **broader than stated** | **Any cancellation that reaches a gRPC call ends as GENERATION_FAILED, not only one mid-`Answer`.**<br>• `Acquire`'s fast path takes a free permit without checking the context (`pool.go:93-97`). So when a client left during embed or retrieval, `Answer` is still called on its dead context.<br>• grpc turns `context.Canceled` into a status error at every entry point (`rpc_util.go:1129`, `:1139-1140`; `clientconn.go:768`).<br>• `status.Error.Is` matches only another `*status.Error` (`internal/status/status.go:222-227`).<br>• At one slot, most misses take the fast path, so "only while queued" is the narrow case | CONFIRMED | Widen F-A's text. The `/bugfix`'s failing test covers both a cancellation mid-`Answer` and one before the permit |
| F-D | **worse than stated** | **The client sees success.** The ABANDONED branch writes nothing (`handler.go:485-490`), so net/http sends an implicit `200` with an empty body. A load generator that checks only the status counts the follower as served, adding one to client-side goodput, while §H says ABANDONED | CONFIRMED | Add this to F-D's consequence. The k6 checks should require a non-empty `answer` |
| F-F | **mis-described** | Three corrections:<br>(i) The "send on closed channel" panic happens in a handler goroutine, which net/http recovers and logs. The gateway does not crash.<br>(ii) `main` returns right after `Close` (`main.go:260-265`), so the requests still in flight are **cut off**, not merely left unlogged.<br>(iii) If the harness stops the load generator before SIGTERM, nothing is in flight and nothing is lost. So "corrupt every load run silently" (`approvals.md` item 3) overstates it | CONFIRMED (code plus documented net/http behaviour) | Restate F-F. The fix is still cheap: close the log only after `Shutdown` returns |
| F-E | correct; reach overstated | **The trigger is narrower than "every run".** Reaching a MISS record needs a genuine `Retrieve` error. A client cancellation during `Retrieve` ends as GENERATION_FAILED through F-A, not as MISS. So it corrupts the runs in which the RAG service errors, not every run | CONFIRMED | Adjust `approvals.md` item 3. 1.3 probably removes it as a side effect, and 1.3's spec should say so |
| F-C | correct | **One nuance.** "Recoverable from `cache = MISS`" must also exclude `coalesced: true`, because followers request no permit (`handler.go:380-388` runs only for the leader) | CONFIRMED | Add the nuance |
| F-B | correct | — | CONFIRMED | See S5 |
| **F-G** | **new, should-fix** | **On a TIER2_HIT where the nearest entry overall is not the one served, `source_overlap` (in both the response and §H) and `overlap_decision` describe the nearest entry, not the served one.**<br>• `Decision` is computed on `nearest` (`cascade.go:116`), but `Candidate` becomes the scoped entry (`:152`, `:161`), and `handler.go:268-276` reads the overlap from `Decision`.<br>• The record therefore pairs one entry's `entry_id` and `entry_sources` with another entry's `source_overlap`, which is ≠ overlap(`retrieved_chunk_ids`, `entry_sources`).<br>• This happens whenever another namespace holds a closer entry, for example the same question cached for another product (B-cross).<br>• `NSDecision.Overlap` is computed for the served entry (`:160`) and never read.<br>• `impact.md` §7 caught `overlap_decision`, but not `source_overlap` | CONFIRMED | Add it to the spec's findings. No test may pin it; the one-entry fixture already avoids it. 1.3's spec should state that removing `nearest` fixes it |
| **F-H** | new, note | **GENERATION_FAILED drops `t_generate_ms`, although the generation ran.** The value is computed at `handler.go:394` but copied into the record only on success (`:501`), whereas `t_permit_wait_ms` is written inside the closure (`:387`). A failed generation's duration is exactly what separates a client timeout (F-A) from an immediate failure | CONFIRMED | A separate `/bugfix`. No test asserts `t_generate_ms` on that path |
| **F-I** | new, note | **The async promotion and the hit-count bump are unguarded writes, which is a Phase 3 hazard.**<br>• Both can land up to 2 s after the hit (`handler.go:47`, `:304-338`).<br>• If C2 purges the entry in that window, the promotion writes a Tier-1 copy of a purged answer under a key no Tier-2 record names. That copy cannot be purged, and is served by bare hash equality.<br>• `HINCRBY` recreates a stub `t2:` hash (`tier2.go:240-242`).<br>• Invariant 3's guard is specified only for the MISS write-back (`interfaces.md:389`) | PLAUSIBLE (C2 not built) | Record it as an input to Phase 3's design |
| **F-J** | new, note | **A failed write-back leaves no trace in §H.** `handler.go:420-445` logs only to stderr. The record says MISS, with an `entry_id` that was never stored and `writeback_discarded: false`. Under Redis trouble the hit rate falls, and nothing in the measurement channel shows why | CONFIRMED | Follow-up. `TestWritebackFailure…` must not assert `writeback_discarded` |
| **F-K** | new, **for the author** | **The live rule is not the claimed rule.**<br>• Served decisions use similarity ∧ namespace, and θ reaches only the counterfactual (`handler.go:293-295`, `lane.go:286`).<br>• `ConfigID` is logged but selects nothing (`handler.go:77`).<br>• `Final_Proposal.md:150` states four conjuncts, and `super-plan.md` 6.1 sweeps θ. A θ sweep over this code moves no served decision.<br>• No Phase 1–2 item says when θ joins the served decision | CONFIRMED by reading | Outside this task; the author decides which item owns it. It is the reason for S1 |

## U5: the reviewer's answer

**Take (a). It is sufficient, and (b) is not.**
- Under `g.mu`, a follower increments `waiting` **and** captures `c` (`coalesce.go:43-47`). From
  that point it is committed to `c`.
- A receive on a closed `done` channel returns at once. So there is no lost-wakeup window, however
  late the follower reaches `<-c.done`.
- `Waiters(t1Key) == 3` therefore guarantees three `shared = true` results.
- It also fails loudly if the coalesce key ever changes, because `Waiters` on `t1Key` then stays at
  0.
- Keep it off the request path, because it takes `g.mu`.

## New unknowns

- **U8:** is the Phase 2 gate on or off in a zero-value `Handler`? This is settled at 2.4, and S1
  makes it moot for these tests.
- **U2 stands:** run `-race`. Nothing in `Ask` reads as racy:
  - the `timings` fields written concurrently are distinct, and both goroutines are joined at
    `handler.go:255`;
  - the shared slices are only ever read.

## Checked and found sound

- **Real Redis is correctly ruled out.** The `idx:cache`, `t2:` and `t1:` names are constants
  (`tier2.go:23`, `:29`; `key.go:22`), so a test cannot avoid the dev cache without a source
  change.
- **The interface's eight methods match the call sites exactly.**
- **Faking at the wire is what exposes F-A.** The probe confirms that `NewClient` works on
  127.0.0.1.
- **The deferred emit cannot race `Close` once `Ask` has returned.** The emit runs inside `Ask`
  (`handler.go:165-178`), and the detached goroutines do not log.
- **U3 is resolved.** The only `go` statements outside the embed/retrieve pair, which is joined,
  are in the TIER2_HIT branch (`handler.go:304`, `:327`).
- **U7 is resolved.** `fn` returns a non-nil value on every nil-error return (`:458-465`), and a
  panic becomes an error for the followers (`coalesce.go:64-68`).
- **SHED at `pool(1,0)` is deterministic.** The queue channel is unbuffered, so the send inside
  `select`/`default` never succeeds (`pool.go:99-103`).
- **These choices are correct:**
  - decoding into `map[string]any`, and never asserting the full key set;
  - never naming `TauHigh`;
  - `codes.Internal` for GENERATION_FAILED;
  - the recording `ResponseWriter`.
- **No cut scope comes back, the hit path does not change, and nothing measured changes.** This
  agrees with `impact.md`.
- **No smaller design stays deterministic.**

---

## Resolutions (Claude, 2026-10-04; applied in `design.md` rev 2 unless marked for the author)

**One correction to the review's phase numbers.** S6, S10 and F-I say "Phase 3" for the epoch
guard and C2. In `super-plan.md` both are **Phase 4** (items 4.1 and 4.2), and Phase 3 is the
corpus. Read "Phase 4" in each place.

Two load-bearing claims were re-checked against the code before anything was applied:
- **F-A's fast path:** `pool.go:93-97` takes a free permit without consulting `ctx`.
- **F-K:** `DecideNamespace` is `similarity >= Tau && match` (`lane.go:292-296`), and its own
  comment says *"There is deliberately no containment term"*. `decisions.md` records no such
  decision.

| # | Resolution |
| :---: | :--- |
| S1 | **Adopted** as the fixture rule in design §3. §5 now names Phase 2 as "must not change these outcomes" |
| S2 | **Adopted.** Every degradation test seeds a would-be TIER2_HIT. The search-failure test injects on both search methods and asserts the fake's `injectedReturned > 0` |
| S3 | **Adopted** in §4's ABANDONED row. Tests with several requests match records by `query_raw` |
| S4 | **Adopted** in §8. Every hook selects on release ∨ `stream.Context().Done()` |
| S5 | **Adopted:** the 500 assertion is dropped. The test asserts exactly one record and `Counters.Requests == 1`, and is renamed `TestTier1LookupErrorStillEmitsOneRecord` |
| S6 | **Adopted:** Retrieve and Answer return the same non-zero epoch |
| S7 | **Adopted:** a round-trip test is added, and `Answer` returns a source set different from the IDs it was given. M12 added |
| S8 | **Adopted:** a cross-product coalescing test is added. M11 added |
| S9 | **Adopted** in both helpers |
| S10 | **For the author** (`approvals.md`, open item 4). It changes how the immutability rule applies, so a person has to confirm it |
| N1 | **Adopted:** the fakes are strict |
| N2 | **Adopted:** no test similarity lies within 0.05 of τ, wider than the 0.01 proposed |
| N3 | **Adopted:** SHED runs at `pool(1,1)` with C queued, and asserts that B's `permit_queue_depth` is 1 |
| N4 | **Adopted:** §4 cites §A for a non-null `source_overlap` on TIER2_HIT |
| N5 | **Adopted, second option:** only the leader's `t_generate_ms` is asserted (non-null). A follower's value is left unasserted |
| N6 | **Adopted:** `approvals.md`, open item 2, names `evallog_test.go:69` as an existing test that belongs to 1.3 |
| F-A, F-C to F-F | **Adopted:** `spec.md`'s findings table is restated |
| F-G to F-J | **Adopted:** added to `spec.md`'s findings, each out of scope with no test pinning it |
| F-K | **For the author** (`approvals.md`, open item 5). It sits above this task, and decides which item puts θ into the served decision, if any |
| U8 | Recorded in design §6 |

---

# Implementation review (`/ai-review`, 2026-10-04)

Two reviewers ran in parallel on the implemented diff: `handler.go`, `coalesce.go`,
`harness_test.go` and `ask_test.go`.
- **`contract-reviewer`** asked whether the tests hold the seam to §A, §B, §D and §H.
- **`design-reviewer`**, the opus agent that reviewed the design, asked whether the implementation
  is the design it approved.

The `design-reviewer` ran 17 probe mutations of its own and restored the source after each.

**Verdicts:**
- **`contract-reviewer`:** no contradiction with §A or §H, no test pins F-A to F-K, and the source
  change is type-only. Four test weaknesses.
- **`design-reviewer`:** sound, no blocker.
  - S3–S10 and N1–N6 landed in code. S1 landed for every hit fixture, and S2 landed in part.
  - M1–M14 are each caught for the right reason.
  - Cleanup and the joins are correct under a mid-test `t.Fatalf`.
  - Three should-fix items and two notes.

Every assertion below was changed **inside this task, before `/done`**. The immutability rule of
`approvals.md` item 4 takes effect at `/done`, so no RCA was owed.

## Findings, most severe first

| # | Sev. | Finding | Check | Source |
| :---: | :---: | :--- | :---: | :--- |
| I-1 | should-fix | **The measured values on the hit path were asserted by presence only.**<br>• On TIER2_HIT, `similarity` and `source_overlap` were only non-null.<br>• `entry_sources`, `retrieved_chunk_ids` and `dataset_epoch_at_retrieval` were unasserted on any hit, and `entry_sources` on the miss too.<br>• The promoted Tier-1 copy's `answer` and `sources`, and the repeat's, were never checked.<br>**Failure:** each of these leaves the suite green, and each is a wrong number:<br>• similarity logged as 1 − cosine;<br>• overlap logged as 1 − overlap;<br>• `entry_sources` set to the retrieved IDs, which makes offline containment read 1.0 on every hit;<br>• retrieval provenance dropped on a hit;<br>• a promotion with `sources: null` | CONFIRMED (probes P4–P8, P11–P14) | both |
| I-2 | should-fix | **The namespace refusal did not isolate the namespace conjunct** (S1). The seeded headphones entry also failed containment and support against kettle's retrieval.<br>**Failure:** put θ into the served decision (F-K's likely resolution) and delete the namespace term, and all 17 tests passed | CONFIRMED (probe P15c) | design |
| I-3 | should-fix | **The bounded-capacity path was never exercised.** Every harness ran at `Capacity` 0, and the fake recorded neither Touch's entry nor Trim's capacity.<br>**Failure:** `TrimToCapacity(ctx, 0)` makes every bounded run silently unbounded, which inflates `h` and so λ_max. The same goes for a Touch of the wrong ID, or a missing one. `cache/capacity_test.go` skips without Redis and never sees this call site | CONFIRMED (P3, P9, P10) | design |
| I-4 | should-fix | **Retrieve and Answer reported the same epoch**, so reading §H's `dataset_epoch_at_retrieval` from the wrong side passed.<br>**Failure:** the epoch reaching the record is Answer's. Under Phase 4 that would defeat the epoch guard (invariant 3) silently | CONFIRMED | contract |
| I-5 | should-fix | **`TestWritebackFailure…` asserted a non-empty `entry_id`.** F-J says that is an entry never stored. The test would block F-J's fix if the fix nulls it | PLAUSIBLE | contract |
| I-6 | note | **Two cascade branches never ran:**<br>• the scoped-search error (`cascade.go:134-137`), because the test failed both searches and the first returned early;<br>• DecideLane refusing a scoped candidate (`:153-155`).<br>**Failure:**<br>• serving the global nearest when the scoped search errors (P2);<br>• judging τ on the global nearest instead of the served candidate (P1), a B-cross false hit | CONFIRMED (coverage, P1, P2) | design |
| I-7 | note | **The coalescing tests identified the leader by the absence of `coalesced`,** which pins `omitempty` on an extension field.<br>**Failure:** the §H-sync follow-up promotes it as a plain bool, and both tests fail for the wrong reason | CONFIRMED | design |

**Accepted with no change (notes):**
- **The fake's `BumpHitCount` does nothing for an absent entry,** where the real `HINCRBY` creates
  a stub (F-I). So nothing here can observe F-I, which belongs to Phase 4's design.
- **Eviction is not modelled:** the fake evicts nothing, and invariant 2 (`t1_key` on eviction) is
  `cache/`'s to test. This suite checks only that `t1_key` is written, and that Trim receives the
  configured capacity.
- **The request_id check in `checkEveryRecord` is tautological,** because records are matched by
  request_id. The real check is the matching step's `Fatalf`. Kept as a cheap restatement.

## Resolutions (Claude, 2026-10-04)

| # | Resolution | Proved by |
| :---: | :--- | :--- |
| I-1 | **Fixed.** `TestTier2Hit…` asserts:<br>• `similarity` within 1e-3 of `hitCos` and `source_overlap` = 1, in the response and the record. With one seeded entry, F-G cannot arise, and the values hold under 1.3 and under F-K;<br>• `entry_sources`, `retrieved_chunk_ids` and `dataset_epoch_at_retrieval` on the record;<br>• the promotion's `answer` and `sources`, and the repeat's `answer`, `sources` and `entry_sources`.<br>`TestMissGenerates…` and `TestMissThenParaphrase…` assert `entry_sources`, and the miss's repeat its provenance | M15–M20, each CAUGHT |
| I-2 | **Fixed.** The new `hitFixture` builds the full fixture, and the test changes only `Namespace` (to headphones). The entry keeps kettle's sources and an answer from kettle's chunk 0, `kettle.otherAnswer`, so serving it would show in the response. `checkFixtures` checks `otherAnswer` too | M27 (θ in the served decision, namespace term deleted): CAUGHT by this test |
| I-3 | **Fixed here,** not deferred: it is cheap, and a deferred gap would have had to close before any bounded run.<br>• The fake records Touch's entry_id and Trim's capacity.<br>• The new `TestBoundedCacheTouchesTheServedEntryAndTrimsToCapacity` runs at `Capacity` 2. It asserts that TIER1_HIT, TIER2_HIT and MISS each touch the served entry, in order, and that Trim receives `[2]` | M22 (trim to 0), M23 (no touch on MISS), M24 (touch the request_id): each CAUGHT |
| I-4 | **Fixed for the §H field.** `fakeRAG` can report a separate Answer epoch. The new `TestRecordCarriesTheRetrievalEpoch` has Answer report a later epoch, and asserts the record carries Retrieve's.<br>**Not asserted, deliberately:** which epoch the Tier-2 record stores, and whether the write-back survives. Both are the Phase 4 epoch guard's to decide. Today the stored epoch is Answer's (`handler.go`, the `PutTier2` call), and that seam stays untested until 4.1. Every other test keeps the two epochs equal (S6) | M21 (record's epoch from Answer): CAUGHT |
| I-5 | **Fixed.** The `entry_id` check is removed. The comment names F-J for both `entry_id` and `writeback_discarded` | — |
| I-6 | **Fixed.**<br>• `TestTier2SearchFailure…` now has two subtests, both searches and the scoped search only. The second is the one search left after 1.3.<br>• The new `TestAnotherNamespaceAboveTauDoesNotLiftAnEntryBelowTau` seeds another namespace's entry at `hitCos` and an in-namespace entry at τ − 0.10 carrying `otherAnswer`. It asserts only the MISS outcome, so it holds after 1.3 | M25 (scoped error serves nearest), M26 (τ on the global nearest): each CAUGHT |
| I-7 | **Fixed.** A record counts as the leader when `coalesced` is absent **or** false (`notTrue`, and the `.(bool)` check) | — |

**After the fixes:**
- 20 tests pass under `-race`, plus 5 subtests. There were no failures in `-race -count=50`, nor in
  `-count=200 -shuffle=on`.
- `make verify` passes.
- M1–M27, X1 and X2, 29 mutations in all, are **all CAUGHT** (`evidence/mutations.txt`), and the
  source is restored.
- No finding remains open.
